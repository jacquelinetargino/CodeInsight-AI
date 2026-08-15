"""Catálogo de regras de dependências (DEP-*).

Nenhuma destas afirma que existe vulnerabilidade — para isso seria preciso
consultar uma base externa, e o motor não faz rede durante a análise. O que elas
apontam é **risco de cadeia de suprimentos e de reprodutibilidade**: build que
muda sozinho, código vindo de fonte não auditável, transporte sem criptografia.
"""

from app.engine.findings import FindingCategory
from app.engine.rules.registry import Rule, RuleRegistry

_D = FindingCategory.DEPENDENCIES


def _rule(
    rule_id: str, name: str, severity: str, description: str, recommendation: str, confidence: float
) -> Rule:
    return Rule(
        rule_id=rule_id,
        name=name,
        category=_D,
        severity=severity,  # type: ignore[arg-type]
        description=description,
        recommendation=recommendation,
        confidence=confidence,
    )


DEPENDENCY_RULES: list[Rule] = [
    _rule(
        "DEP-001",
        "Dependência sem versão",
        "medium",
        "A dependência é declarada sem nenhuma restrição de versão. Cada instalação pode "
        "trazer uma versão diferente, incluindo uma que quebre o projeto ou que tenha "
        "sido comprometida.",
        "Declare a versão. Em Python use `==`; em npm, a versão exata sem `^` ou `~`.",
        0.9,
    ),
    _rule(
        "DEP-002",
        "Faixa de versão aberta",
        "low",
        "A restrição aceita versões futuras que ainda não existem e não foram revisadas. "
        "O build deixa de ser reprodutível.",
        "Fixe a versão e use um arquivo de lock, atualizando de forma deliberada.",
        0.8,
    ),
    _rule(
        "DEP-003",
        "Dependência vinda de repositório git",
        "medium",
        "A dependência aponta para um repositório git em vez do registro oficial. O "
        "conteúdo pode mudar sem aviso, e a referência pode desaparecer.",
        "Prefira a versão publicada no registro. Se o git for inevitável, fixe um commit "
        "específico em vez de um branch.",
        0.85,
    ),
    _rule(
        "DEP-004",
        "Dependência baixada por http://",
        "high",
        "A dependência é obtida por conexão sem criptografia, sujeita a alteração no "
        "caminho — é o cenário clássico de comprometimento de cadeia de suprimentos.",
        "Use https:// ou o registro oficial do ecossistema.",
        0.9,
    ),
    _rule(
        "DEP-005",
        "Ausência de arquivo de lock",
        "medium",
        "O projeto declara dependências mas não tem arquivo de lock. Sem ele, duas "
        "instalações da mesma revisão podem produzir árvores diferentes.",
        "Gere e versione o lock do seu gerenciador — package-lock.json, poetry.lock, "
        "Cargo.lock ou go.sum.",
        0.85,
    ),
]


def register_dependency_rules(registry: RuleRegistry) -> None:
    registry.register_all(DEPENDENCY_RULES)
