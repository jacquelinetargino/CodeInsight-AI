"""Analyzers de arquitetura e configuração.

Arquitetura é heurística: não existe estrutura universalmente correta. Os testes
cobrem tanto a detecção quanto os falsos positivos que a heurística precisa
evitar — projeto pequeno sem camadas, arquivo curto, raiz enxuta.
"""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.engine.analyzers.architecture import (
    MAX_FILES_PER_DIRECTORY,
    MIN_FILES_FOR_LAYERING,
    ArchitectureAnalyzer,
)
from app.engine.analyzers.configuration import ConfigurationAnalyzer
from app.engine.findings import FindingCategory
from app.engine.rules.architecture import HUGE_FILE_LINES, LARGE_FILE_LINES, path_depth
from app.engine.rules.architecture_rules import (
    ARCHITECTURE_RULES,
    register_architecture_rules,
)
from app.engine.rules.configuration import (
    analyze_compose,
    analyze_dockerfile,
    analyze_workflow,
    missing_gitignore_entries,
)
from app.engine.rules.configuration_rules import (
    CONFIGURATION_RULES,
    register_configuration_rules,
)
from app.engine.rules.registry import RuleRegistry
from app.engine.scanner import scan_repository

GITIGNORE_COMPLETO = ".env\n*.pem\nnode_modules/\n__pycache__/\ndist/\n"

DOCKERFILE_SEGURO = """
FROM python:3.12-slim
RUN useradd --create-home app
USER app
HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1
CMD ["python", "app.py"]
"""


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def arq() -> ArchitectureAnalyzer:
    return ArchitectureAnalyzer()


@pytest.fixture
def cfg() -> ConfigurationAnalyzer:
    return ConfigurationAnalyzer()


def build_repo(root: Path, arquivos: dict[str, str]) -> Path:
    for caminho, conteudo in arquivos.items():
        destino = root / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")
    return root


def run(analyzer, root: Path):
    return analyzer.analyze(root, scan_repository(root))


def rule_ids(resultado) -> set[str]:
    return {f.rule_id for f in resultado.findings}


# ============================================================================
# ARQUITETURA
# ============================================================================


@pytest.mark.parametrize(
    ("caminho", "profundidade"),
    [("app.py", 0), ("src/app.py", 1), ("a/b/c/d.py", 3)],
)
def test_path_depth(caminho: str, profundidade: int):
    assert path_depth(caminho) == profundidade


def test_catalog_architecture_is_well_formed():
    for regra in ARCHITECTURE_RULES:
        assert regra.category is FindingCategory.ARCHITECTURE
        assert regra.description and regra.recommendation
        # Heurística estrutural nunca é certeza.
        assert regra.confidence <= 0.8


def test_architecture_catalog_registers():
    reg = RuleRegistry()
    register_architecture_rules(reg)
    assert len(reg) == len(ARCHITECTURE_RULES)


def test_detects_large_file(arq, tmp_path):
    build_repo(tmp_path, {"src/grande.py": "x = 1\n" * (LARGE_FILE_LINES + 20)})
    assert "ARC-001" in rule_ids(run(arq, tmp_path))


def test_detects_huge_file_with_higher_severity(arq, tmp_path):
    build_repo(tmp_path, {"src/enorme.py": "x = 1\n" * (HUGE_FILE_LINES + 20)})
    achados = rule_ids(run(arq, tmp_path))

    assert "ARC-002" in achados
    # Um arquivo não pode gerar os dois achados: seria o mesmo problema duas vezes.
    assert "ARC-001" not in achados


def test_small_file_is_clean(arq, tmp_path):
    build_repo(tmp_path, {"src/pequeno.py": "x = 1\n"})
    assert "ARC-001" not in rule_ids(run(arq, tmp_path))


def test_detects_deep_nesting(arq, tmp_path):
    build_repo(tmp_path, {"a/b/c/d/e/f/g/h/fundo.py": "x = 1\n"})
    assert "ARC-003" in rule_ids(run(arq, tmp_path))


def test_shallow_structure_is_clean(arq, tmp_path):
    build_repo(tmp_path, {"src/app/models/user.py": "x = 1\n"})
    assert "ARC-003" not in rule_ids(run(arq, tmp_path))


def test_detects_cluttered_root(arq, tmp_path):
    build_repo(tmp_path, {f"arquivo{i}.py": "x = 1\n" for i in range(40)})
    assert "ARC-004" in rule_ids(run(arq, tmp_path))


def test_small_project_is_not_charged_for_layering(arq, tmp_path):
    """Projeto pequeno não precisa de camadas — cobrar seria ruído."""
    build_repo(tmp_path, {"a.py": "x = 1\n", "b.py": "x = 1\n"})
    assert "ARC-005" not in rule_ids(run(arq, tmp_path))


def test_detects_missing_layering_in_larger_project(arq, tmp_path):
    arquivos = {f"modulo{i}/arquivo.py": "x = 1\n" for i in range(MIN_FILES_FOR_LAYERING + 5)}
    build_repo(tmp_path, arquivos)
    assert "ARC-005" in rule_ids(run(arq, tmp_path))


def test_layered_project_is_clean(arq, tmp_path):
    arquivos = {f"src/services/servico{i}.py": "x = 1\n" for i in range(MIN_FILES_FOR_LAYERING + 5)}
    build_repo(tmp_path, arquivos)
    assert "ARC-005" not in rule_ids(run(arq, tmp_path))


def test_detects_overcrowded_directory(arq, tmp_path):
    arquivos = {f"src/arquivo{i}.py": "x = 1\n" for i in range(MAX_FILES_PER_DIRECTORY + 10)}
    build_repo(tmp_path, arquivos)
    assert "ARC-006" in rule_ids(run(arq, tmp_path))


def test_binary_files_do_not_count_lines(arq, tmp_path):
    (tmp_path / "imagem.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00" + b"x" * 100_000)
    assert rule_ids(run(arq, tmp_path)) == set()


def test_empty_repository_architecture(arq, tmp_path):
    assert run(arq, tmp_path).findings == []


# ============================================================================
# CONFIGURAÇÃO — Dockerfile
# ============================================================================


def test_dockerfile_root_detection():
    assert analyze_dockerfile("FROM python:3.12\nCMD ['x']\n").runs_as_root
    assert not analyze_dockerfile("FROM python:3.12\nUSER app\n").runs_as_root


def test_dockerfile_explicit_root_is_detected():
    assert analyze_dockerfile("FROM python:3.12\nUSER root\n").runs_as_root


def test_last_user_wins():
    """`USER root` para instalar e `USER app` no fim é o padrão correto."""
    conteudo = "FROM python:3.12\nUSER root\nRUN apt-get install -y curl\nUSER app\n"
    assert not analyze_dockerfile(conteudo).runs_as_root


@pytest.mark.parametrize(
    ("imagem", "flutuante"),
    [
        ("python:latest", True),
        ("python", True),
        ("python:3.12-slim", False),
        ("python@sha256:abc123", False),
    ],
)
def test_floating_tag_detection(imagem: str, flutuante: bool):
    assert analyze_dockerfile(f"FROM {imagem}\n").uses_floating_tag is flutuante


def test_embedded_secret_detection():
    relatorio = analyze_dockerfile("FROM x\nENV DB_PASSWORD=senhaSuperSecreta\n")
    assert relatorio.embedded_secrets


def test_env_from_variable_is_not_a_secret():
    """`ENV SENHA=${VAR}` é injeção em runtime, não valor fixo."""
    assert not analyze_dockerfile("FROM x\nENV DB_PASSWORD=${DB_PASSWORD}\n").embedded_secrets


def test_secret_value_is_never_in_the_finding(cfg, tmp_path):
    """A evidência traz o nome da variável, nunca o valor."""
    segredo = "senhaSuperSecretaQueNaoPodeVazar"
    build_repo(tmp_path, {"Dockerfile": f"FROM x\nENV DB_PASSWORD={segredo}\n"})

    for achado in run(cfg, tmp_path).findings:
        assert segredo not in (achado.evidence or "")
        assert segredo not in achado.description


def test_detects_remote_add():
    assert analyze_dockerfile("FROM x\nADD https://exemplo.com/x.sh /tmp/\n").remote_add


def test_secure_dockerfile_is_clean(cfg, tmp_path):
    build_repo(tmp_path, {"Dockerfile": DOCKERFILE_SEGURO, ".gitignore": GITIGNORE_COMPLETO})
    achados = rule_ids(run(cfg, tmp_path))

    assert achados == set()


def test_dockerfile_findings(cfg, tmp_path):
    build_repo(
        tmp_path,
        {"Dockerfile": "FROM python:latest\nCMD ['x']\n", ".gitignore": GITIGNORE_COMPLETO},
    )
    achados = rule_ids(run(cfg, tmp_path))

    assert {"CFG-001", "CFG-002", "CFG-011"} <= achados


# ============================================================================
# CONFIGURAÇÃO — compose, CI, gitignore
# ============================================================================


def test_detects_privileged_container():
    assert analyze_compose("services:\n  db:\n    privileged: true\n").privileged_lines


def test_detects_host_network():
    assert analyze_compose("services:\n  x:\n    network_mode: host\n").host_network_lines


def test_normal_compose_is_clean():
    conteudo = "services:\n  db:\n    image: postgres:16\n    ports:\n      - '5432:5432'\n"
    relatorio = analyze_compose(conteudo)
    assert not relatorio.privileged_lines
    assert not relatorio.host_network_lines


def test_detects_unpinned_action():
    assert analyze_workflow("      - uses: actions/checkout@v4\n").unpinned_actions


def test_sha_pinned_action_is_clean():
    sha = "a" * 40
    assert not analyze_workflow(f"      - uses: actions/checkout@{sha}\n").unpinned_actions


def test_detects_curl_pipe_shell():
    assert analyze_workflow("        run: curl -sSL https://x.sh | bash\n").curl_pipe_shell


def test_gitignore_missing_entries():
    faltando = missing_gitignore_entries("dist/\n")
    assert ".env" in faltando
    assert "credenciais" in faltando


def test_complete_gitignore_is_clean():
    assert missing_gitignore_entries(GITIGNORE_COMPLETO) == []


def test_missing_gitignore_file(cfg, tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    assert "CFG-009" in rule_ids(run(cfg, tmp_path))


def test_incomplete_gitignore(cfg, tmp_path):
    build_repo(tmp_path, {".gitignore": "dist/\n"})
    achados = rule_ids(run(cfg, tmp_path))

    assert "CFG-010" in achados
    assert "CFG-009" not in achados  # o arquivo existe


def test_catalog_configuration_is_well_formed():
    for regra in CONFIGURATION_RULES:
        assert regra.category is FindingCategory.CONFIGURATION
        assert regra.description and regra.recommendation


def test_configuration_catalog_registers():
    reg = RuleRegistry()
    register_configuration_rules(reg)
    assert len(reg) == len(CONFIGURATION_RULES)


# ============================================================================
# SEGURANÇA E DETERMINISMO
# ============================================================================


def test_no_image_is_built_and_no_container_runs(cfg, tmp_path, monkeypatch):
    import os
    import subprocess

    def explode(*args, **kwargs):  # pragma: no cover - só falha se for chamado
        raise AssertionError("nenhuma imagem pode ser construida nem container executado")

    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(subprocess, "Popen", explode)
    monkeypatch.setattr(os, "system", explode)

    build_repo(
        tmp_path,
        {
            "Dockerfile": "FROM alpine\nRUN rm -rf /\n",
            "docker-compose.yml": "services:\n  x:\n    privileged: true\n",
            ".gitignore": GITIGNORE_COMPLETO,
        },
    )
    assert run(cfg, tmp_path).findings


def test_both_analyzers_are_deterministic(arq, cfg, tmp_path):
    build_repo(
        tmp_path,
        {
            "src/grande.py": "x = 1\n" * (LARGE_FILE_LINES + 5),
            "Dockerfile": "FROM python:latest\n",
        },
    )
    assert [f.id for f in run(arq, tmp_path).findings] == [
        f.id for f in run(arq, tmp_path).findings
    ]
    assert [f.id for f in run(cfg, tmp_path).findings] == [
        f.id for f in run(cfg, tmp_path).findings
    ]


def test_findings_carry_metadata(cfg, tmp_path):
    build_repo(tmp_path, {"Dockerfile": "FROM python:latest\n", ".gitignore": GITIGNORE_COMPLETO})
    achado = next(f for f in run(cfg, tmp_path).findings if f.rule_id == "CFG-001")

    assert achado.category is FindingCategory.CONFIGURATION
    assert achado.analyzer == "configuration"
    assert achado.file_path == "Dockerfile"
    assert achado.recommendation


def test_analyzes_this_project(arq, cfg):
    """Este repositório tem Dockerfile, compose, workflows e .gitignore reais."""
    raiz = Path(__file__).parent.parent.parent
    scan = scan_repository(raiz)

    resultado_arq = arq.analyze(raiz, scan)
    resultado_cfg = cfg.analyze(raiz, scan)

    assert resultado_cfg.files_analyzed >= 3
    for achado in resultado_arq.findings + resultado_cfg.findings:
        assert achado.rule_id.startswith(("ARC-", "CFG-"))
        assert achado.recommendation
