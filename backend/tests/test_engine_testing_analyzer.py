"""Analyzer de testes.

A garantia central: os testes do repositório analisado **nunca são executados**.
Alguns fixtures contêm testes que falhariam ruidosamente se rodassem.
"""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.engine.analyzers.testing import MIN_TEST_RATIO, TestingAnalyzer
from app.engine.findings import FindingCategory
from app.engine.rules.registry import RuleRegistry
from app.engine.rules.testing import detect_frameworks, is_source_file, is_test_file
from app.engine.rules.testing_rules import TESTING_RULES, register_testing_rules
from app.engine.scanner import scan_repository


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def analyzer() -> TestingAnalyzer:
    return TestingAnalyzer()


def build_repo(root: Path, arquivos: dict[str, str]) -> Path:
    for caminho, conteudo in arquivos.items():
        destino = root / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")
    return root


def run(analyzer: TestingAnalyzer, root: Path):
    return analyzer.analyze(root, scan_repository(root))


def rule_ids(resultado) -> set[str]:
    return {f.rule_id for f in resultado.findings}


# --- reconhecimento de arquivo ----------------------------------------------


@pytest.mark.parametrize(
    "caminho",
    [
        "test_auth.py",
        "auth_test.py",
        "tests/test_x.py",
        "src/Button.test.tsx",
        "src/utils.spec.ts",
        "src/AuthTest.java",
        "handler_test.go",
        "spec/model_spec.rb",
        "tests/helpers.py",  # dentro de diretório de teste
        "__tests__/setup.ts",
    ],
)
def test_recognizes_test_files(caminho: str):
    assert is_test_file(caminho)


@pytest.mark.parametrize(
    "caminho",
    ["app.py", "src/index.ts", "latest_news.py", "contest.js", "src/protest/model.py"],
)
def test_does_not_confuse_source_with_test(caminho: str):
    """`latest_news.py` e `contest.js` contêm 'test' mas não são testes."""
    assert not is_test_file(caminho)


@pytest.mark.parametrize(
    ("caminho", "eh_fonte"),
    [("app.py", True), ("index.tsx", True), ("main.go", True), ("README.md", False)],
)
def test_source_file_classification(caminho: str, eh_fonte: bool):
    assert is_source_file(caminho) is eh_fonte


# --- reconhecimento de framework --------------------------------------------


@pytest.mark.parametrize(
    ("conteudo", "framework"),
    [
        ("import pytest\n", "pytest"),
        ("from pytest import fixture\n", "pytest"),
        ("import unittest\n", "unittest"),
        ("import { describe } from 'vitest'\n", "vitest"),
        ("jest.mock('./api')\n", "jest"),
        ("import '@testing-library/react'\n", "testing-library"),
        ("import org.junit.Test;\n", "junit"),
        ("func TestSoma(t *testing.T) {}\n", "go-testing"),
        ("RSpec.describe Model do\n", "rspec"),
        ("#[test]\nfn soma() {}\n", "cargo-test"),
    ],
)
def test_detects_frameworks(conteudo: str, framework: str):
    assert framework in detect_frameworks(conteudo)


def test_no_framework_in_plain_code():
    assert detect_frameworks("def soma(a, b):\n    return a + b\n") == set()


# --- catálogo ---------------------------------------------------------------


def test_catalog_is_well_formed():
    for regra in TESTING_RULES:
        assert regra.category is FindingCategory.TESTING
        assert regra.description and regra.recommendation


def test_catalog_registers_without_duplicates():
    reg = RuleRegistry()
    register_testing_rules(reg)
    assert len(reg) == len(TESTING_RULES)


# --- analyzer ---------------------------------------------------------------


def test_reports_absence_of_tests(analyzer, tmp_path):
    build_repo(tmp_path, {"app.py": "def f():\n    return 1\n"})
    assert "TST-001" in rule_ids(run(analyzer, tmp_path))


def test_absence_of_tests_does_not_pile_up_findings(analyzer, tmp_path):
    """Sem nenhum teste, cobrar organização e cobertura seria repetir o mesmo problema."""
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    achados = rule_ids(run(analyzer, tmp_path))

    assert achados == {"TST-001"}


def test_reports_low_ratio(analyzer, tmp_path):
    arquivos = {f"src/modulo{i}.py": "x = 1\n" for i in range(30)}
    arquivos["tests/test_um.py"] = "import pytest\n\n\ndef test_x():\n    assert True\n"
    arquivos[".coveragerc"] = "[run]\n"
    build_repo(tmp_path, arquivos)

    assert "TST-002" in rule_ids(run(analyzer, tmp_path))


def test_healthy_ratio_is_clean(analyzer, tmp_path):
    arquivos = {f"src/modulo{i}.py": "x = 1\n" for i in range(4)}
    for i in range(4):
        arquivos[f"tests/test_modulo{i}.py"] = "import pytest\n\n\ndef test_x():\n    assert True\n"
    arquivos[".coveragerc"] = "[run]\n"
    build_repo(tmp_path, arquivos)

    assert "TST-002" not in rule_ids(run(analyzer, tmp_path))


def test_reports_unknown_framework(analyzer, tmp_path):
    build_repo(
        tmp_path,
        {"tests/test_x.py": "def test_soma():\n    assert 1 + 1 == 2\n", "app.py": "x = 1\n"},
    )
    assert "TST-003" in rule_ids(run(analyzer, tmp_path))


def test_known_framework_is_clean(analyzer, tmp_path):
    build_repo(
        tmp_path,
        {
            "tests/test_x.py": "import pytest\n\n\ndef test_soma():\n    assert True\n",
            "app.py": "x = 1\n",
        },
    )
    assert "TST-003" not in rule_ids(run(analyzer, tmp_path))


def test_reports_tests_without_dedicated_directory(analyzer, tmp_path):
    build_repo(
        tmp_path,
        {"test_app.py": "import pytest\n\n\ndef test_x():\n    assert True\n", "app.py": "x = 1\n"},
    )
    assert "TST-004" in rule_ids(run(analyzer, tmp_path))


def test_reports_missing_coverage_config(analyzer, tmp_path):
    build_repo(
        tmp_path,
        {
            "tests/test_x.py": "import pytest\n\n\ndef test_x():\n    assert True\n",
            "app.py": "x = 1\n",
        },
    )
    assert "TST-005" in rule_ids(run(analyzer, tmp_path))


def test_coverage_config_is_recognized(analyzer, tmp_path):
    build_repo(
        tmp_path,
        {
            "tests/test_x.py": "import pytest\n\n\ndef test_x():\n    assert True\n",
            "app.py": "x = 1\n",
            ".coveragerc": "[run]\nsource = app\n",
        },
    )
    assert "TST-005" not in rule_ids(run(analyzer, tmp_path))


# --- garantia central -------------------------------------------------------


def test_never_executes_the_repository_tests(analyzer, tmp_path, monkeypatch):
    """O fixture contém um teste que falharia ruidosamente se fosse executado."""
    import os
    import subprocess

    def explode(*args, **kwargs):  # pragma: no cover - só falha se for chamado
        raise AssertionError("a suite do repositorio analisado nao pode ser executada")

    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(subprocess, "Popen", explode)
    monkeypatch.setattr(os, "system", explode)

    marcador = tmp_path / "suite-executada.txt"
    build_repo(
        tmp_path,
        {
            "tests/test_destrutivo.py": (
                "import pytest\n"
                "from pathlib import Path\n\n\n"
                f"Path({str(marcador)!r}).write_text('rodou')\n"
                "raise SystemExit('esta suite nao pode rodar')\n"
            ),
            "app.py": "x = 1\n",
        },
    )

    resultado = run(analyzer, tmp_path)
    assert not marcador.exists()
    assert resultado.files_analyzed == 1


def test_never_reports_a_coverage_percentage():
    """Medir cobertura exigiria executar a suíte. Nenhuma regra pode prometer um
    número que o motor não tem como conhecer."""
    for regra in TESTING_RULES:
        assert "%" not in regra.description
        assert "%" not in regra.name


def test_ratio_is_not_coverage(analyzer, tmp_path):
    """`test_ratio` é proporção de arquivos, não cobertura de linhas — o achado
    correspondente descreve volume, não percentual verificado."""
    from app.engine.rules.testing import TestingReport

    relatorio = TestingReport(test_files=["a"], source_files=["b", "c", "d", "e"])
    assert relatorio.test_ratio == 0.25
    assert not hasattr(relatorio, "coverage_percent")


# --- robustez ---------------------------------------------------------------


def test_empty_repository(analyzer, tmp_path):
    assert "TST-001" in rule_ids(run(analyzer, tmp_path))


def test_findings_carry_metadata(analyzer, tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    (achado,) = run(analyzer, tmp_path).findings

    assert achado.category is FindingCategory.TESTING
    assert achado.analyzer == "testing"
    assert achado.recommendation


def test_is_deterministic(analyzer, tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n", "test_app.py": "def test_x(): pass\n"})
    assert [f.id for f in run(analyzer, tmp_path).findings] == [
        f.id for f in run(analyzer, tmp_path).findings
    ]


def test_analyzes_this_project(analyzer):
    """Este backend tem tests/ com pytest e .coveragerc no CI."""
    raiz = Path(__file__).parent.parent
    resultado = analyzer.analyze(raiz, scan_repository(raiz))

    achados = {f.rule_id for f in resultado.findings}
    assert "TST-001" not in achados
    assert "TST-003" not in achados
    assert "TST-004" not in achados
    assert resultado.files_analyzed > 10


def test_min_ratio_is_documented():
    assert 0 < MIN_TEST_RATIO < 1
