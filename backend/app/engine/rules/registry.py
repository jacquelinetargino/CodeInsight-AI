"""Registro de regras: catálogo declarativo e criação de achados a partir dele.

Uma regra descreve o que o motor procura; o analyzer só informa onde encontrou.
Manter severidade, categoria e recomendação na regra — e não espalhadas pelos
analyzers — garante que o mesmo problema seja reportado da mesma forma
independentemente de quem o detectou.
"""

from pydantic import BaseModel, Field

from app.engine.findings import Finding, FindingCategory, build_finding_id
from app.models.enums import Severity


class DuplicateRuleError(Exception):
    """Dois registros com o mesmo `rule_id`. Quase sempre é copiar-e-colar numa
    regra nova, e passar batido faria uma sobrescrever a outra em silêncio."""


class UnknownRuleError(Exception):
    pass


class Rule(BaseModel):
    """Definição de uma regra. `confidence` é o padrão do que a regra produz:
    detecções textuais valem menos que as baseadas em AST, e isso fica explícito
    aqui em vez de ser decidido caso a caso no analyzer."""

    rule_id: str = Field(description="Identificador estável, ex.: SEC-001")
    name: str
    category: FindingCategory
    severity: Severity
    description: str
    recommendation: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    enabled: bool = True

    def build_finding(
        self,
        *,
        analyzer: str,
        file_path: str | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        evidence: str | None = None,
        title: str | None = None,
        description: str | None = None,
        confidence: float | None = None,
        severity: Severity | None = None,
    ) -> Finding:
        """Cria um achado herdando categoria, severidade e recomendação da regra.

        `title`, `description`, `confidence` e `severity` aceitam sobrescrita
        porque um analyzer às vezes tem contexto para ser mais específico — por
        exemplo, rebaixar a confiança quando a detecção veio de heurística e não
        de AST, ou rebaixar a severidade de um certificado que está numa pasta
        de fixtures de teste.
        """
        final_title = title or self.name
        return Finding(
            id=build_finding_id(
                rule_id=self.rule_id,
                file_path=file_path,
                line_start=line_start,
                title=final_title,
            ),
            rule_id=self.rule_id,
            category=self.category,
            severity=severity or self.severity,
            title=final_title,
            description=description or self.description,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            evidence=evidence,
            recommendation=self.recommendation,
            confidence=self.confidence if confidence is None else confidence,
            analyzer=analyzer,
        )


class RuleRegistry:
    """Coleção de regras indexada por id.

    Instanciável para que os testes montem catálogos isolados sem contaminar o
    registro global usado pela aplicação.
    """

    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def register(self, rule: Rule) -> Rule:
        if rule.rule_id in self._rules:
            raise DuplicateRuleError(
                f"A regra {rule.rule_id!r} já está registrada. Use um id novo — "
                "sobrescrever silenciosamente esconderia uma das duas."
            )
        self._rules[rule.rule_id] = rule
        return rule

    def register_all(self, rules: list[Rule]) -> None:
        for rule in rules:
            self.register(rule)

    def get(self, rule_id: str) -> Rule:
        try:
            return self._rules[rule_id]
        except KeyError as exc:
            raise UnknownRuleError(f"Regra desconhecida: {rule_id!r}") from exc

    def all(self) -> list[Rule]:
        """Todas as regras, habilitadas ou não, ordenadas por id — a ordem
        estável importa para documentação e para diffs de catálogo."""
        return [self._rules[key] for key in sorted(self._rules)]

    def enabled(self) -> list[Rule]:
        return [rule for rule in self.all() if rule.enabled]

    def by_category(self, category: FindingCategory) -> list[Rule]:
        return [rule for rule in self.enabled() if rule.category == category]

    def __len__(self) -> int:
        return len(self._rules)

    def __contains__(self, rule_id: object) -> bool:
        return rule_id in self._rules


# Registro global preenchido pelos módulos de regra dos PRs seguintes.
registry = RuleRegistry()
