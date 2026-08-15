"""Analyzer de documentação.

O ponto central é a distinção entre **arquivo ausente** e **seção ausente** —
os dois pedem ações diferentes e são reportados separadamente.
"""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.engine.analyzers.documentation import MIN_README_CHARS, DocumentationAnalyzer
from app.engine.findings import FindingCategory
from app.engine.rules.documentation import analyze_readme, classify_doc_file, extract_headings
from app.engine.rules.documentation_rules import (
    DOCUMENTATION_RULES,
    register_documentation_rules,
)
from app.engine.rules.registry import RuleRegistry
from app.engine.scanner import scan_repository
from app.models.enums import Severity

README_COMPLETO = """
# Projeto Exemplo

Uma ferramenta para analisar repositórios.

## Instalação

```bash
pip install exemplo
```

## Uso

```bash
exemplo analisar ./repo
```

## Configuração

Defina a variável `EXEMPLO_TOKEN` no ambiente.
"""


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def analyzer() -> DocumentationAnalyzer:
    return DocumentationAnalyzer()


def build_repo(root: Path, arquivos: dict[str, str]) -> Path:
    for caminho, conteudo in arquivos.items():
        destino = root / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")
    return root


def run(analyzer: DocumentationAnalyzer, root: Path):
    return analyzer.analyze(root, scan_repository(root))


def rule_ids(resultado) -> set[str]:
    return {f.rule_id for f in resultado.findings}


# --- leitura de markdown ----------------------------------------------------


def test_extracts_atx_headings():
    assert extract_headings("# Um\n## Dois\n### Três\n") == ["Um", "Dois", "Três"]


def test_extracts_setext_headings():
    assert "Título" in extract_headings("Título\n======\n")


def test_ignores_non_heading_hash():
    """`#` dentro de bloco de código não é cabeçalho de seção."""
    titulos = extract_headings("Texto com # no meio da frase\n")
    assert titulos == []


@pytest.mark.parametrize(
    ("conteudo", "tema"),
    [
        ("## Instalação\ncomo instalar", "installation"),
        ("## Installation\nhow to install", "installation"),
        ("## Como usar\n", "usage"),
        ("## Usage\n", "usage"),
        ("## Configuração\n", "configuration"),
        ("## Environment variables\n", "configuration"),
        ("## API Reference\n", "api"),
        ("## Arquitetura\n", "architecture"),
    ],
)
def test_recognizes_sections_in_both_languages(conteudo: str, tema: str):
    assert tema in analyze_readme(conteudo).covered


def test_detects_code_examples():
    assert analyze_readme("```bash\nls\n```").has_code_examples
    assert not analyze_readme("Apenas prosa, sem exemplo.").has_code_examples


def test_badges_do_not_count_as_content():
    """README que é só uma fileira de distintivos não documenta nada."""
    badges = "# Projeto\n" + "![build](https://img.shields.io/x)" * 20
    assert analyze_readme(badges).content_length < 100


@pytest.mark.parametrize(
    ("arquivo", "papel"),
    [
        ("README.md", "readme"),
        ("readme.md", "readme"),
        ("LICENSE", "license"),
        ("LICENCE", "license"),
        ("CONTRIBUTING.md", "contributing"),
        ("CHANGELOG.md", "changelog"),
        ("SECURITY.md", "security"),
        ("app.py", None),
    ],
)
def test_classifies_doc_files(arquivo: str, papel: str | None):
    assert classify_doc_file(arquivo) == papel


# --- catálogo ---------------------------------------------------------------


def test_catalog_is_well_formed():
    for regra in DOCUMENTATION_RULES:
        assert regra.category is FindingCategory.DOCUMENTATION
        assert regra.description and regra.recommendation


def test_documentation_is_never_critical():
    """Documentação ausente é dívida, não vulnerabilidade — inflar competiria
    com achados de segurança no score."""
    for regra in DOCUMENTATION_RULES:
        assert regra.severity in (Severity.LOW, Severity.MEDIUM)


def test_catalog_registers_without_duplicates():
    reg = RuleRegistry()
    register_documentation_rules(reg)
    assert len(reg) == len(DOCUMENTATION_RULES)


# --- arquivo ausente vs seção ausente ---------------------------------------


def test_missing_readme_is_reported(analyzer, tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    assert "DOC-001" in rule_ids(run(analyzer, tmp_path))


def test_missing_section_is_a_different_finding(analyzer, tmp_path):
    """README existe mas não explica instalação: problema distinto de não ter README."""
    build_repo(tmp_path, {"README.md": "# Projeto\n\n" + "Descrição longa. " * 40})
    achados = rule_ids(run(analyzer, tmp_path))

    assert "DOC-001" not in achados  # o arquivo existe
    assert "DOC-003" in achados  # mas falta a seção


def test_missing_license_and_contributing(analyzer, tmp_path):
    build_repo(tmp_path, {"README.md": README_COMPLETO})
    achados = rule_ids(run(analyzer, tmp_path))

    assert "DOC-007" in achados
    assert "DOC-008" in achados


def test_complete_documentation_is_clean(analyzer, tmp_path):
    build_repo(
        tmp_path,
        {
            "README.md": README_COMPLETO,
            "LICENSE": "MIT",
            "CONTRIBUTING.md": "# Como contribuir\n",
        },
    )
    assert run(analyzer, tmp_path).findings == []


# --- README fraco -----------------------------------------------------------


def test_short_readme_is_reported(analyzer, tmp_path):
    build_repo(tmp_path, {"README.md": "# Projeto\n"})
    assert "DOC-002" in rule_ids(run(analyzer, tmp_path))


def test_short_readme_does_not_pile_up_section_findings(analyzer, tmp_path):
    """README quase vazio: cobrar cada seção seria repetir o mesmo problema."""
    build_repo(tmp_path, {"README.md": "# Projeto\n"})
    achados = rule_ids(run(analyzer, tmp_path))

    assert "DOC-002" in achados
    assert {"DOC-003", "DOC-004", "DOC-005", "DOC-006"} & achados == set()


def test_readme_without_code_examples(analyzer, tmp_path):
    conteudo = "# Projeto\n\n## Instalação\nBaixe e instale.\n\n## Uso\nExecute.\n\n"
    conteudo += "## Configuração\nDefina variáveis.\n\n" + "Texto adicional. " * 30
    build_repo(tmp_path, {"README.md": conteudo, "LICENSE": "MIT", "CONTRIBUTING.md": "x"})

    assert "DOC-006" in rule_ids(run(analyzer, tmp_path))


# --- localização ------------------------------------------------------------


def test_readme_outside_root_does_not_count(analyzer, tmp_path):
    """Um README dentro de `exemplos/` não é o README do projeto."""
    build_repo(tmp_path, {"exemplos/README.md": README_COMPLETO})
    assert "DOC-001" in rule_ids(run(analyzer, tmp_path))


@pytest.mark.parametrize("nome", ["README.md", "README.rst", "README", "readme.md"])
def test_readme_variants_are_recognized(analyzer, tmp_path, nome: str):
    build_repo(tmp_path, {nome: README_COMPLETO})
    assert "DOC-001" not in rule_ids(run(analyzer, tmp_path))


# --- robustez ---------------------------------------------------------------


def test_empty_repository(analyzer, tmp_path):
    achados = rule_ids(run(analyzer, tmp_path))
    assert {"DOC-001", "DOC-007", "DOC-008"} <= achados


def test_findings_carry_metadata(analyzer, tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    (achado,) = [f for f in run(analyzer, tmp_path).findings if f.rule_id == "DOC-001"]

    assert achado.category is FindingCategory.DOCUMENTATION
    assert achado.analyzer == "documentation"
    assert achado.recommendation
    assert achado.id.startswith("finding-")


def test_is_deterministic(analyzer, tmp_path):
    build_repo(tmp_path, {"README.md": "# Curto\n"})
    assert [f.id for f in run(analyzer, tmp_path).findings] == [
        f.id for f in run(analyzer, tmp_path).findings
    ]


def test_no_network_or_rendering(analyzer, tmp_path, monkeypatch):
    """Links do markdown não são seguidos."""
    import socket

    def explode(*args, **kwargs):  # pragma: no cover - só falha se for chamado
        raise AssertionError("o analyzer nao pode acessar a rede")

    monkeypatch.setattr(socket.socket, "connect", explode)
    monkeypatch.setattr(socket, "create_connection", explode)

    build_repo(tmp_path, {"README.md": "# X\n[link](https://exemplo.com)\n"})
    assert run(analyzer, tmp_path).findings


def test_analyzes_this_project(analyzer):
    """Este repositório tem README, LICENSE e CONTRIBUTING de verdade."""
    raiz = Path(__file__).parent.parent.parent
    resultado = analyzer.analyze(raiz, scan_repository(raiz))

    achados = {f.rule_id for f in resultado.findings}
    assert "DOC-001" not in achados
    assert "DOC-007" not in achados
    assert "DOC-008" not in achados


def test_min_readme_threshold_is_documented():
    assert MIN_README_CHARS > 0


def test_concise_but_complete_readme_is_not_flagged_as_empty(analyzer, tmp_path):
    """Comprimento sozinho é sinal fraco: um README curto que explica instalação
    e uso está completo, só é conciso."""
    build_repo(
        tmp_path,
        {
            "README.md": README_COMPLETO,
            "LICENSE": "MIT",
            "CONTRIBUTING.md": "x",
        },
    )
    assert len(README_COMPLETO) < MIN_README_CHARS  # é mesmo curto
    assert "DOC-002" not in rule_ids(run(analyzer, tmp_path))
