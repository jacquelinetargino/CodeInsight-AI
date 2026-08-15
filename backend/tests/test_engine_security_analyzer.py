"""Analyzer de segurança: tradução de detecções em achados classificados.

Os "repositórios" aqui são diretórios temporários montados no teste. Nenhum
código deles é executado — o analyzer só lê.
"""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.engine.analyzers.security import SecurityAnalyzer
from app.engine.findings import FindingCategory
from app.engine.rules.registry import RuleRegistry
from app.engine.rules.security_rules import SECURITY_RULES, register_security_rules
from app.engine.scanner import scan_repository
from app.models.enums import Severity


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def analyzer() -> SecurityAnalyzer:
    return SecurityAnalyzer()


def build_repo(root: Path, arquivos: dict[str, str]) -> Path:
    for caminho, conteudo in arquivos.items():
        destino = root / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")
    return root


def run(analyzer: SecurityAnalyzer, root: Path):
    return analyzer.analyze(root, scan_repository(root))


def rule_ids(resultado) -> set[str]:
    return {f.rule_id for f in resultado.findings}


# --- catálogo ---------------------------------------------------------------


def test_catalog_covers_the_specified_rules():
    ids = {r.rule_id for r in SECURITY_RULES}
    assert {f"SEC-{n:03d}" for n in range(1, 11)} <= ids


def test_all_rules_are_security_and_well_formed():
    for regra in SECURITY_RULES:
        assert regra.category is FindingCategory.SECURITY
        assert regra.description and regra.recommendation
        assert 0.0 < regra.confidence <= 1.0


def test_catalog_registers_without_duplicates():
    reg = RuleRegistry()
    register_security_rules(reg)
    assert len(reg) == len(SECURITY_RULES)


def test_credential_leaks_are_critical_or_high():
    """Credencial exposta não é achado cosmético."""
    por_id = {r.rule_id: r for r in SECURITY_RULES}
    for rule_id in ("SEC-002", "SEC-003", "SEC-005"):
        assert por_id[rule_id].severity is Severity.CRITICAL


# --- credenciais ------------------------------------------------------------


def test_detects_api_key_as_sec001(analyzer, tmp_path):
    build_repo(tmp_path, {"config.py": 'KEY = "AKIAQQQQQQQQQQQQQQQQ"\n'})
    resultado = run(analyzer, tmp_path)

    assert "SEC-001" in rule_ids(resultado)
    (achado,) = [f for f in resultado.findings if f.rule_id == "SEC-001"]
    assert achado.file_path == "config.py"
    assert achado.line_start == 1
    assert achado.analyzer == "security"


def test_detects_private_key_as_sec003(analyzer, tmp_path):
    build_repo(tmp_path, {"deploy/id_rsa": "-----BEGIN RSA PRIVATE KEY-----\nMIIE\n"})
    assert "SEC-003" in rule_ids(run(analyzer, tmp_path))


def test_detects_jwt_as_sec004(analyzer, tmp_path):
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop"
    build_repo(tmp_path, {"auth.py": f'TOKEN = "{jwt}"\n'})
    assert "SEC-004" in rule_ids(run(analyzer, tmp_path))


def test_detects_database_credential_as_sec002(analyzer, tmp_path):
    build_repo(tmp_path, {"db.py": 'URL = "postgresql://app:s3nh4Real@host/db"\n'})
    assert "SEC-002" in rule_ids(run(analyzer, tmp_path))


def test_secret_evidence_is_masked_in_the_finding(analyzer, tmp_path):
    """A garantia do PR 06 tem de sobreviver à travessia até o achado."""
    segredo = "gsk_" + "z" * 30
    build_repo(tmp_path, {"config.py": f'KEY = "{segredo}"\n'})

    resultado = run(analyzer, tmp_path)
    achados = [f for f in resultado.findings if f.rule_id == "SEC-001"]

    assert achados
    for achado in achados:
        assert segredo not in (achado.evidence or "")
        assert segredo not in achado.description
        assert segredo not in achado.title


# --- .env versionado --------------------------------------------------------


def test_detects_tracked_env_file(analyzer, tmp_path):
    build_repo(tmp_path, {".env": "SECRET=abc\n"})
    assert "SEC-005" in rule_ids(run(analyzer, tmp_path))


def test_env_example_is_not_reported(analyzer, tmp_path):
    """`.env.example` é a prática recomendada, não o problema."""
    build_repo(tmp_path, {".env.example": "SECRET=\n"})
    assert "SEC-005" not in rule_ids(run(analyzer, tmp_path))


# --- código Python ----------------------------------------------------------


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("eval(entrada)\n", "SEC-006"),
        ("exec(codigo)\n", "SEC-007"),
        ('cursor.execute(f"SELECT * FROM users WHERE id = {uid}")\n', "SEC-008"),
        ("import subprocess\nsubprocess.run(cmd, shell=True)\n", "SEC-009"),
        ("import os\nos.system(cmd)\n", "SEC-009"),
        ("import hashlib\nhashlib.md5(senha)\n", "SEC-010"),
        ("import pickle\npickle.loads(dados)\n", "SEC-011"),
        ("import yaml\nyaml.load(txt)\n", "SEC-012"),
    ],
)
def test_maps_ast_issues_to_rules(analyzer, tmp_path, codigo: str, esperado: str):
    build_repo(tmp_path, {"app.py": codigo})
    assert esperado in rule_ids(run(analyzer, tmp_path))


def test_quality_issues_are_not_reported_as_security(analyzer, tmp_path):
    """Função longa é problema de qualidade; o analyzer de segurança ignora."""
    corpo = "\n".join(f"    x{i} = {i}" for i in range(80))
    build_repo(tmp_path, {"app.py": f"def grande():\n{corpo}\n"})

    resultado = run(analyzer, tmp_path)
    assert resultado.findings == []


def test_clean_repository_produces_no_findings(analyzer, tmp_path):
    build_repo(
        tmp_path,
        {
            "app.py": (
                "import json\n\n\n"
                "def carregar(texto: str) -> dict:\n"
                "    return json.loads(texto)\n"
            ),
            "README.md": "# Projeto limpo\n",
        },
    )
    resultado = run(analyzer, tmp_path)

    assert resultado.findings == []
    assert resultado.files_analyzed == 2


# --- robustez ---------------------------------------------------------------


def test_syntax_error_becomes_a_note_not_a_finding(analyzer, tmp_path):
    """Arquivo ilegível é limitação da análise, não vulnerabilidade — e precisa
    ficar visível para o score não tratar 'ilegível' como 'limpo'."""
    build_repo(tmp_path, {"legado.py": "print 'python 2'\n"})
    resultado = run(analyzer, tmp_path)

    assert resultado.findings == []
    assert any("legado.py" in nota for nota in resultado.notes)


def test_binary_files_are_skipped(analyzer, tmp_path):
    (tmp_path / "imagem.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00dados")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")

    resultado = run(analyzer, tmp_path)
    assert resultado.files_analyzed == 1


def test_empty_repository(analyzer, tmp_path):
    resultado = run(analyzer, tmp_path)
    assert resultado.findings == []
    assert resultado.files_analyzed == 0


def test_analyzer_never_executes_repository_code(analyzer, tmp_path, monkeypatch):
    import os
    import subprocess

    def explode(*args, **kwargs):  # pragma: no cover - só falha se for chamado
        raise AssertionError("o analyzer nao pode executar nada do repositorio")

    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(subprocess, "Popen", explode)
    monkeypatch.setattr(os, "system", explode)

    marcador = tmp_path / "efeito-colateral.txt"
    build_repo(
        tmp_path,
        {
            "setup.py": f"from pathlib import Path\nPath({str(marcador)!r}).write_text('x')\n",
            "Makefile": "all:\n\techo invadido\n",
        },
    )

    resultado = run(analyzer, tmp_path)
    assert not marcador.exists()
    assert resultado.files_analyzed >= 1


# --- confiança e determinismo -----------------------------------------------


def test_generic_assignment_has_lower_confidence_than_specific_pattern(analyzer, tmp_path):
    """Prefixo proprietário quase não erra; `password = "..."` erra bastante."""
    build_repo(
        tmp_path,
        {
            "a.py": 'KEY = "AKIAQQQQQQQQQQQQQQQQ"\n',
            "b.py": 'password = "umaSenhaQualquer123"\n',
        },
    )
    resultado = run(analyzer, tmp_path)
    por_arquivo = {f.file_path: f for f in resultado.findings}

    assert por_arquivo["a.py"].confidence > por_arquivo["b.py"].confidence


def test_findings_are_deterministic(analyzer, tmp_path):
    build_repo(tmp_path, {"app.py": 'eval(x)\nKEY = "AKIAQQQQQQQQQQQQQQQQ"\n'})

    primeiro = [f.id for f in run(analyzer, tmp_path).findings]
    segundo = [f.id for f in run(analyzer, tmp_path).findings]

    assert primeiro == segundo


def test_findings_carry_full_metadata(analyzer, tmp_path):
    build_repo(tmp_path, {"app.py": "eval(entrada)\n"})
    (achado,) = run(analyzer, tmp_path).findings

    assert achado.rule_id == "SEC-006"
    assert achado.category is FindingCategory.SECURITY
    assert achado.severity is Severity.HIGH
    assert achado.recommendation
    assert achado.evidence
    assert achado.id.startswith("finding-")
    assert 0.0 < achado.confidence <= 1.0


def test_serializes_to_legacy_jsonb(analyzer, tmp_path):
    """O achado precisa caber no formato que o banco já usa."""
    from app.schemas.analysis import Finding as ApiFinding

    build_repo(tmp_path, {"app.py": "eval(entrada)\n"})
    (achado,) = run(analyzer, tmp_path).findings

    api = ApiFinding.model_validate(achado.to_legacy_dict())
    assert api.file_path == "app.py"
    assert api.severity is Severity.HIGH


def test_analyzes_this_project_without_crashing(analyzer):
    """Código real, não só fixtures."""
    raiz = Path(__file__).parent.parent / "app"
    resultado = analyzer.analyze(raiz, scan_repository(raiz))

    assert resultado.files_analyzed > 30
    for achado in resultado.findings:
        assert achado.file_path
        assert achado.rule_id.startswith("SEC-")


# --- JavaScript/TypeScript --------------------------------------------------


@pytest.mark.parametrize(
    ("arquivo", "codigo", "esperado"),
    [
        ("app.js", "const r = eval(x);\n", "SEC-006"),
        ("app.js", "const f = new Function('x');\n", "SEC-007"),
        ("view.tsx", "el.innerHTML = dados;\n", "SEC-013"),
        ("view.tsx", "<div dangerouslySetInnerHTML={{__html: h}} />\n", "SEC-013"),
        ("token.ts", "const t = Math.random().toString(36); // token\n", "SEC-014"),
        ("auth.ts", 'localStorage.setItem("authToken", t);\n', "SEC-015"),
        ("api.ts", 'fetch("http://api.exemplo.com");\n', "SEC-016"),
        ("run.js", "child_process.exec(cmd);\n", "SEC-009"),
    ],
)
def test_maps_javascript_issues_to_rules(analyzer, tmp_path, arquivo, codigo, esperado):
    build_repo(tmp_path, {arquivo: codigo})
    assert esperado in rule_ids(run(analyzer, tmp_path))


def test_javascript_findings_have_lower_confidence_than_python(analyzer, tmp_path):
    """Detecção textual não merece a mesma certeza que a AST."""
    build_repo(tmp_path, {"a.py": "eval(x)\n", "b.js": "eval(x);\n"})
    por_arquivo = {f.file_path: f for f in run(analyzer, tmp_path).findings}

    assert por_arquivo["b.js"].confidence < por_arquivo["a.py"].confidence


def test_javascript_quality_issues_are_not_security(analyzer, tmp_path):
    build_repo(tmp_path, {"app.js": "var x = 1;\nconsole.log(x);\nif (a == b) {}\n"})
    assert run(analyzer, tmp_path).findings == []
