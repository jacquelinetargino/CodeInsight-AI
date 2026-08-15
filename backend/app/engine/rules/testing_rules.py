"""Catálogo de regras de testes (TST-*).

Nenhuma regra aqui mede cobertura: cobertura exige executar a suíte, e o motor
não executa código do repositório analisado. O que se avalia é a **presença e a
organização** da infraestrutura de teste — sinais observáveis sem rodar nada.
"""

from app.engine.findings import FindingCategory
from app.engine.rules.registry import Rule, RuleRegistry

_T = FindingCategory.TESTING


def _rule(
    rule_id: str, name: str, severity: str, description: str, recommendation: str, confidence: float
) -> Rule:
    return Rule(
        rule_id=rule_id,
        name=name,
        category=_T,
        severity=severity,  # type: ignore[arg-type]
        description=description,
        recommendation=recommendation,
        confidence=confidence,
    )


TESTING_RULES: list[Rule] = [
    _rule(
        "TST-001",
        "Nenhum teste automatizado encontrado",
        "high",
        "Não foi encontrado nenhum arquivo de teste. Sem testes, qualquer alteração pode "
        "quebrar comportamento existente sem que ninguém perceba.",
        "Comece cobrindo os caminhos críticos — autenticação, cálculos e regras de negócio.",
        0.9,
    ),
    _rule(
        "TST-002",
        "Proporção baixa de testes",
        "medium",
        "Existem testes, mas em número pequeno em relação ao código-fonte. Isso indica "
        "cobertura desigual, com partes do sistema sem verificação.",
        "Priorize testar os módulos com mais lógica de decisão.",
        0.6,
    ),
    _rule(
        "TST-003",
        "Framework de teste não identificado",
        "low",
        "Há arquivos que parecem de teste, mas nenhum framework conhecido foi reconhecido "
        "no conteúdo.",
        "Use um framework estabelecido do ecossistema — pytest, Jest, Vitest, JUnit.",
        0.5,
    ),
    _rule(
        "TST-004",
        "Testes sem organização em diretório próprio",
        "low",
        "Os arquivos de teste estão espalhados junto ao código, sem um diretório dedicado.",
        "Concentre os testes em `tests/` ou `__tests__/`, ou adote a convenção do ecossistema.",
        0.5,
    ),
    _rule(
        "TST-005",
        "Sem configuração de cobertura",
        "low",
        "O projeto tem testes mas nenhuma configuração de cobertura. Sem medir, não se sabe "
        "o que ficou de fora.",
        "Configure a medição de cobertura e acompanhe-a no CI.",
        0.7,
    ),
]


def register_testing_rules(registry: RuleRegistry) -> None:
    registry.register_all(TESTING_RULES)
