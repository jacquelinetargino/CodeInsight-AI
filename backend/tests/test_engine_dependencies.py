"""Leitura de manifestos e analyzer de dependências.

Nenhum gerenciador de pacote é executado: os manifestos são lidos como dado.
"""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.engine.analyzers.dependency import DependencyAnalyzer
from app.engine.findings import FindingCategory
from app.engine.rules.dependencies import (
    Dependency,
    parse_build_gradle,
    parse_cargo_toml,
    parse_go_mod,
    parse_manifest,
    parse_package_json,
    parse_pom_xml,
    parse_pyproject,
    parse_requirements,
)
from app.engine.rules.dependency_rules import DEPENDENCY_RULES, register_dependency_rules
from app.engine.rules.registry import RuleRegistry
from app.engine.scanner import scan_repository


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def analyzer() -> DependencyAnalyzer:
    return DependencyAnalyzer()


def build_repo(root: Path, arquivos: dict[str, str]) -> Path:
    for caminho, conteudo in arquivos.items():
        destino = root / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")
    return root


def run(analyzer: DependencyAnalyzer, root: Path):
    return analyzer.analyze(root, scan_repository(root))


def rule_ids(resultado) -> set[str]:
    return {f.rule_id for f in resultado.findings}


# --- requirements.txt -------------------------------------------------------


def test_parses_requirements():
    conteudo = "fastapi==0.115.6\nrequests>=2.0\n# comentario\n\n-r outro.txt\nnumpy\n"
    deps = {d.name: d for d in parse_requirements(conteudo).dependencies}

    assert set(deps) == {"fastapi", "requests", "numpy"}
    assert deps["fastapi"].is_pinned
    assert not deps["requests"].is_pinned
    assert deps["numpy"].spec == ""


def test_requirements_ignores_flags_and_comments():
    conteudo = "--index-url https://exemplo\n-e .\n# nada\n"
    assert parse_requirements(conteudo).dependencies == []


def test_requirements_records_line_numbers():
    (dep,) = parse_requirements("\n\nfastapi==1.0\n").dependencies
    assert dep.line == 3


def test_requirements_handles_extras_and_markers():
    conteudo = 'uvicorn[standard]==0.32.1\nfoo==1.0 ; python_version < "3.13"\n'
    deps = {d.name: d for d in parse_requirements(conteudo).dependencies}
    assert deps["uvicorn"].is_pinned
    assert deps["foo"].is_pinned


# --- pyproject.toml ---------------------------------------------------------


def test_parses_pyproject():
    conteudo = """
    [project]
    name = "x"
    dependencies = ["fastapi==0.115.6", "httpx>=0.28"]

    [project.optional-dependencies]
    dev = ["pytest==8.3.4"]
    """
    nomes = {d.name for d in parse_pyproject(conteudo).dependencies}
    assert nomes == {"fastapi", "httpx", "pytest"}


def test_invalid_toml_reports_error():
    relatorio = parse_pyproject("isto [ nao ] = e toml valido {{{")
    assert relatorio.parse_error is not None
    assert relatorio.dependencies == []


# --- package.json -----------------------------------------------------------


def test_parses_package_json():
    conteudo = """
    {
      "dependencies": {"react": "18.2.0", "lodash": "^4.17.0"},
      "devDependencies": {"vite": "~5.0.0"}
    }
    """
    deps = {d.name: d for d in parse_package_json(conteudo).dependencies}

    assert set(deps) == {"react", "lodash", "vite"}
    assert deps["react"].is_pinned
    assert not deps["lodash"].is_pinned
    assert not deps["vite"].is_pinned


def test_invalid_json_reports_error():
    relatorio = parse_package_json("{ isto nao e json")
    assert relatorio.parse_error is not None


def test_package_json_that_is_not_an_object():
    assert parse_package_json("[1, 2, 3]").parse_error is not None


# --- outros ecossistemas ----------------------------------------------------


def test_parses_go_mod():
    conteudo = """
    module exemplo

    require (
        github.com/gin-gonic/gin v1.9.1
        golang.org/x/text v0.14.0
    )

    require github.com/pkg/errors v0.9.1
    """
    deps = {d.name: d for d in parse_go_mod(conteudo).dependencies}
    assert "github.com/gin-gonic/gin" in deps
    assert "github.com/pkg/errors" in deps
    assert deps["github.com/gin-gonic/gin"].is_pinned


def test_parses_cargo_toml():
    conteudo = """
    [dependencies]
    serde = "1.0.195"
    tokio = { version = "1.35" }

    [dev-dependencies]
    criterion = "0.5"
    """
    deps = {d.name: d for d in parse_cargo_toml(conteudo).dependencies}
    assert set(deps) == {"serde", "tokio", "criterion"}
    assert deps["serde"].is_pinned


def test_parses_pom_xml_without_xml_parser():
    """`pom.xml` é lido por regex de propósito: parser de XML sobre entrada não
    confiável abre porta para expansão de entidades."""
    conteudo = """
    <project>
      <dependencies>
        <dependency>
          <groupId>org.springframework</groupId>
          <artifactId>spring-core</artifactId>
          <version>6.1.2</version>
        </dependency>
      </dependencies>
    </project>
    """
    (dep,) = parse_pom_xml(conteudo).dependencies
    assert dep.name == "spring-core"
    assert dep.spec == "6.1.2"


def test_billion_laughs_does_not_expand():
    """Entrada hostil clássica de XML: sem parser, não há expansão."""
    conteudo = (
        '<!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
        "<project><dependencies><dependency>"
        "<artifactId>&lol2;</artifactId><version>1.0</version>"
        "</dependency></dependencies></project>"
    )
    relatorio = parse_pom_xml(conteudo)
    assert len(relatorio.dependencies) == 1
    assert relatorio.dependencies[0].name == "&lol2;"  # tratado como texto


def test_parses_build_gradle():
    conteudo = """
    dependencies {
        implementation 'com.google.guava:guava:32.1.3-jre'
        testImplementation "junit:junit:4.13.2"
    }
    """
    deps = {d.name for d in parse_build_gradle(conteudo).dependencies}
    assert deps == {"guava", "junit"}


def test_parse_manifest_dispatches_and_ignores_unknown():
    assert parse_manifest("requirements.txt", "fastapi==1.0\n") is not None
    assert parse_manifest("qualquer.txt", "conteudo") is None


# --- classificação de versão ------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "fixada"),
    [
        ("==1.2.3", True),
        ("1.2.3", True),
        ("v1.2.3", True),
        ("1.2.3-beta.1", True),
        (">=1.0", False),
        ("^4.17.0", False),
        ("~5.0.0", False),
        ("*", False),
        ("latest", False),
        ("", False),
    ],
)
def test_pinned_classification(spec: str, fixada: bool):
    dep = Dependency(name="x", spec=spec, manifest="m", ecosystem="e")
    assert dep.is_pinned is fixada


@pytest.mark.parametrize(
    "spec",
    ["git+https://github.com/org/repo", "git@github.com:org/repo.git", "github.com/org/repo"],
)
def test_git_source_detection(spec: str):
    assert Dependency(name="x", spec=spec, manifest="m", ecosystem="e").has_git_source


def test_insecure_source_detection():
    dep = Dependency(name="x", spec="http://exemplo.com/pkg.tgz", manifest="m", ecosystem="e")
    assert dep.has_insecure_source


# --- catálogo ---------------------------------------------------------------


def test_catalog_is_well_formed():
    for regra in DEPENDENCY_RULES:
        assert regra.category is FindingCategory.DEPENDENCIES
        assert regra.description and regra.recommendation
        assert 0.0 < regra.confidence <= 1.0


def test_catalog_registers_without_duplicates():
    reg = RuleRegistry()
    register_dependency_rules(reg)
    assert len(reg) == len(DEPENDENCY_RULES)


# --- analyzer ---------------------------------------------------------------


def test_reports_unpinned_dependency(analyzer, tmp_path):
    build_repo(tmp_path, {"requirements.txt": "numpy\n"})
    assert "DEP-001" in rule_ids(run(analyzer, tmp_path))


def test_reports_open_range(analyzer, tmp_path):
    build_repo(tmp_path, {"requirements.txt": "requests>=2.0\n"})
    assert "DEP-002" in rule_ids(run(analyzer, tmp_path))


def test_reports_git_dependency(analyzer, tmp_path):
    build_repo(
        tmp_path,
        {"package.json": '{"dependencies": {"lib": "git+https://github.com/org/lib"}}'},
    )
    assert "DEP-003" in rule_ids(run(analyzer, tmp_path))


def test_reports_insecure_download(analyzer, tmp_path):
    build_repo(tmp_path, {"package.json": '{"dependencies": {"lib": "http://x.com/lib.tgz"}}'})
    assert "DEP-004" in rule_ids(run(analyzer, tmp_path))


def test_reports_missing_lock_file(analyzer, tmp_path):
    build_repo(tmp_path, {"package.json": '{"dependencies": {"react": "18.2.0"}}'})
    assert "DEP-005" in rule_ids(run(analyzer, tmp_path))


def test_lock_file_present_is_clean(analyzer, tmp_path):
    build_repo(
        tmp_path,
        {
            "package.json": '{"dependencies": {"react": "18.2.0"}}',
            "package-lock.json": "{}",
        },
    )
    assert "DEP-005" not in rule_ids(run(analyzer, tmp_path))


def test_manifest_without_dependencies_needs_no_lock(analyzer, tmp_path):
    """Lock só faz falta quando há dependência para travar."""
    build_repo(tmp_path, {"package.json": '{"name": "vazio"}'})
    assert "DEP-005" not in rule_ids(run(analyzer, tmp_path))


def test_pinned_dependencies_are_clean(analyzer, tmp_path):
    build_repo(
        tmp_path,
        {
            "package.json": '{"dependencies": {"react": "18.2.0"}}',
            "package-lock.json": "{}",
        },
    )
    assert run(analyzer, tmp_path).findings == []


def test_malformed_manifest_becomes_a_note(analyzer, tmp_path):
    build_repo(tmp_path, {"package.json": "{ quebrado"})
    resultado = run(analyzer, tmp_path)

    assert resultado.findings == []
    assert any("package.json" in nota for nota in resultado.notes)


def test_repository_without_manifests(analyzer, tmp_path):
    build_repo(tmp_path, {"app.py": "x = 1\n"})
    resultado = run(analyzer, tmp_path)

    assert resultado.findings == []
    assert resultado.files_analyzed == 0


def test_findings_carry_metadata(analyzer, tmp_path):
    build_repo(tmp_path, {"requirements.txt": "numpy\n"})
    (achado,) = [f for f in run(analyzer, tmp_path).findings if f.rule_id == "DEP-001"]

    assert achado.category is FindingCategory.DEPENDENCIES
    assert achado.analyzer == "dependency"
    assert achado.file_path == "requirements.txt"
    assert achado.line_start == 1
    assert "numpy" in achado.title
    assert achado.recommendation


def test_no_package_manager_is_executed(analyzer, tmp_path, monkeypatch):
    import os
    import subprocess

    def explode(*args, **kwargs):  # pragma: no cover - só falha se for chamado
        raise AssertionError("nenhum gerenciador de pacote pode ser executado")

    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(subprocess, "Popen", explode)
    monkeypatch.setattr(os, "system", explode)

    build_repo(tmp_path, {"requirements.txt": "numpy\n", "package.json": '{"dependencies":{}}'})
    assert run(analyzer, tmp_path).files_analyzed == 2


def test_is_deterministic(analyzer, tmp_path):
    build_repo(tmp_path, {"requirements.txt": "numpy\nrequests>=2.0\n"})
    assert [f.id for f in run(analyzer, tmp_path).findings] == [
        f.id for f in run(analyzer, tmp_path).findings
    ]


def test_analyzes_this_projects_manifests(analyzer):
    """Manifestos reais deste repositório."""
    raiz = Path(__file__).parent.parent
    resultado = analyzer.analyze(raiz, scan_repository(raiz))

    assert resultado.files_analyzed >= 2  # requirements.txt e pyproject.toml
    for achado in resultado.findings:
        assert achado.rule_id.startswith("DEP-")
