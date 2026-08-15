"""Finding e catálogo de regras, com foco na compatibilidade com o JSONB já
persistido — análises antigas não podem quebrar."""

import pytest
from pydantic import ValidationError

from app.engine.findings import (
    MAX_EVIDENCE_CHARS,
    Finding,
    FindingCategory,
    build_finding_id,
)
from app.engine.rules.registry import (
    DuplicateRuleError,
    Rule,
    RuleRegistry,
    UnknownRuleError,
)
from app.models.enums import Severity
from app.schemas.analysis import Finding as ApiFinding


def make_rule(**overrides) -> Rule:
    base = {
        "rule_id": "SEC-001",
        "name": "Possível chave de API hardcoded",
        "category": FindingCategory.SECURITY,
        "severity": Severity.HIGH,
        "description": "Uma possível chave de API foi detectada no código.",
        "recommendation": "Mova a credencial para uma variável de ambiente.",
        "confidence": 0.9,
    }
    return Rule(**{**base, **overrides})


# --- identificador ----------------------------------------------------------


def test_finding_id_is_deterministic():
    args = {"rule_id": "SEC-001", "file_path": "config.py", "line_start": 15, "title": "Chave"}
    assert build_finding_id(**args) == build_finding_id(**args)


@pytest.mark.parametrize(
    "mudanca",
    [
        {"rule_id": "SEC-002"},
        {"file_path": "outro.py"},
        {"line_start": 16},
        {"title": "Outro título"},
    ],
)
def test_finding_id_changes_with_each_component(mudanca: dict):
    base = {"rule_id": "SEC-001", "file_path": "config.py", "line_start": 15, "title": "Chave"}
    assert build_finding_id(**base) != build_finding_id(**{**base, **mudanca})


def test_finding_id_handles_missing_location():
    """Achado sem arquivo/linha (ex.: falta um README) ainda precisa de id."""
    gerado = build_finding_id(
        rule_id="DOC-001", file_path=None, line_start=None, title="Sem README"
    )
    assert gerado.startswith("finding-")


# --- construção a partir da regra -------------------------------------------


def test_rule_builds_finding_inheriting_metadata():
    achado = make_rule().build_finding(
        analyzer="security", file_path="config.py", line_start=15, evidence="API_KEY=sk-****"
    )

    assert achado.rule_id == "SEC-001"
    assert achado.category == FindingCategory.SECURITY
    assert achado.severity == Severity.HIGH
    assert achado.recommendation == "Mova a credencial para uma variável de ambiente."
    assert achado.confidence == 0.9
    assert achado.analyzer == "security"


def test_rule_allows_overriding_title_and_confidence():
    """Um analyzer pode rebaixar a confiança quando a detecção é heurística."""
    achado = make_rule().build_finding(
        analyzer="quality", title="Detecção heurística", confidence=0.4
    )
    assert achado.title == "Detecção heurística"
    assert achado.confidence == 0.4


@pytest.mark.parametrize("valor", [-0.1, 1.1])
def test_confidence_must_be_between_zero_and_one(valor: float):
    with pytest.raises(ValidationError):
        make_rule().build_finding(analyzer="x", confidence=valor)


# --- evidência --------------------------------------------------------------


def test_long_evidence_is_truncated():
    """Evidência é um trecho para o humano, não o arquivo inteiro."""
    achado = make_rule().build_finding(analyzer="security", evidence="x" * 5000)
    assert achado.evidence is not None
    assert len(achado.evidence) == MAX_EVIDENCE_CHARS + 1  # +1 pela reticência
    assert achado.evidence.endswith("…")


def test_short_evidence_is_preserved():
    achado = make_rule().build_finding(analyzer="security", evidence="API_KEY=sk-********")
    assert achado.evidence == "API_KEY=sk-********"


# --- serialização e compatibilidade -----------------------------------------


def test_legacy_dict_is_a_superset_of_the_old_format():
    """Campos antigos preservados com os nomes antigos; novos adicionados."""
    achado = make_rule().build_finding(
        analyzer="security", file_path="config.py", line_start=15, line_end=15, evidence="ev"
    )
    dados = achado.to_legacy_dict()

    # formato histórico
    assert dados["title"] == achado.title
    assert dados["description"] == achado.description
    assert dados["suggestion"] == achado.recommendation
    assert dados["severity"] == "high"
    assert dados["file_path"] == "config.py"
    assert dados["line"] == 15

    # campos novos
    assert dados["rule_id"] == "SEC-001"
    assert dados["category"] == "security"
    assert dados["confidence"] == 0.9
    assert dados["analyzer"] == "security"
    assert dados["evidence"] == "ev"
    assert dados["line_end"] == 15


def test_api_schema_still_validates_new_findings():
    """O schema atual da API precisa continuar aceitando o JSONB novo — é o que
    garante que nenhuma análise nova quebre a listagem existente."""
    dados = (
        make_rule()
        .build_finding(analyzer="security", file_path="config.py", line_start=15)
        .to_legacy_dict()
    )

    api = ApiFinding.model_validate(dados)

    assert api.title == "Possível chave de API hardcoded"
    assert api.severity == Severity.HIGH
    assert api.file_path == "config.py"
    assert api.line == 15


def test_reads_old_findings_without_new_fields():
    """Análises já persistidas têm só os seis campos originais."""
    antigo = {
        "title": "Senha em texto plano",
        "description": "Credencial hardcoded",
        "suggestion": "Use variável de ambiente",
        "severity": "critical",
        "file_path": "settings.py",
        "line": 42,
    }

    achado = Finding.from_legacy_dict(antigo)

    assert achado.title == "Senha em texto plano"
    assert achado.severity == Severity.CRITICAL
    assert achado.line_start == 42
    assert achado.recommendation == "Use variável de ambiente"
    # Sem regra rastreável, o achado vale menos e diz de onde veio.
    assert achado.rule_id == "LEGACY"
    assert achado.analyzer == "legacy"
    assert achado.confidence == 0.5
    assert achado.id.startswith("finding-")


def test_roundtrip_preserves_all_fields():
    original = make_rule().build_finding(
        analyzer="security",
        file_path="config.py",
        line_start=15,
        line_end=18,
        evidence="API_KEY=sk-********",
    )

    reconstruido = Finding.from_legacy_dict(original.to_legacy_dict())

    assert reconstruido.model_dump() == original.model_dump()


def test_minimal_legacy_dict_does_not_crash():
    """Dado corrompido ou incompleto no JSONB não pode derrubar a leitura."""
    achado = Finding.from_legacy_dict({})
    assert achado.title == "Achado sem título"
    assert achado.category == FindingCategory.QUALITY


# --- registro ---------------------------------------------------------------


def test_register_and_get():
    reg = RuleRegistry()
    regra = reg.register(make_rule())
    assert reg.get("SEC-001") is regra
    assert "SEC-001" in reg
    assert len(reg) == 1


def test_duplicate_rule_id_is_rejected():
    """Sobrescrever em silêncio esconderia uma das duas regras."""
    reg = RuleRegistry()
    reg.register(make_rule())
    with pytest.raises(DuplicateRuleError, match="SEC-001"):
        reg.register(make_rule(name="Outra regra com o mesmo id"))


def test_unknown_rule_raises():
    with pytest.raises(UnknownRuleError, match="SEC-999"):
        RuleRegistry().get("SEC-999")


def test_all_is_sorted_by_id():
    reg = RuleRegistry()
    reg.register_all(
        [
            make_rule(rule_id="SEC-003"),
            make_rule(rule_id="SEC-001"),
            make_rule(rule_id="SEC-002"),
        ]
    )
    assert [r.rule_id for r in reg.all()] == ["SEC-001", "SEC-002", "SEC-003"]


def test_disabled_rules_are_excluded_from_enabled_and_category():
    reg = RuleRegistry()
    reg.register(make_rule(rule_id="SEC-001"))
    reg.register(make_rule(rule_id="SEC-002", enabled=False))

    assert [r.rule_id for r in reg.enabled()] == ["SEC-001"]
    assert [r.rule_id for r in reg.by_category(FindingCategory.SECURITY)] == ["SEC-001"]
    # `all()` continua mostrando as desabilitadas — o catálogo é auditável.
    assert len(reg.all()) == 2


def test_by_category_filters():
    reg = RuleRegistry()
    reg.register(make_rule(rule_id="SEC-001", category=FindingCategory.SECURITY))
    reg.register(make_rule(rule_id="DOC-001", category=FindingCategory.DOCUMENTATION))

    assert [r.rule_id for r in reg.by_category(FindingCategory.DOCUMENTATION)] == ["DOC-001"]
    assert reg.by_category(FindingCategory.TESTING) == []


def test_global_registry_starts_empty_and_is_isolated_from_instances():
    """Os módulos de regra dos PRs seguintes preenchem o registro global; testes
    devem usar instâncias próprias para não contaminá-lo."""
    from app.engine.rules import registry as global_registry

    local = RuleRegistry()
    local.register(make_rule())
    assert "SEC-001" not in global_registry


def test_engine_categories_cover_the_eight_analyzers():
    assert {c.value for c in FindingCategory} == {
        "security",
        "quality",
        "architecture",
        "dependencies",
        "documentation",
        "testing",
        "git",
        "configuration",
    }
