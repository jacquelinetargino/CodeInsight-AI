"""Catálogo de regras de documentação (DOC-*).

Duas coisas diferentes são reportadas separadamente, e isso é deliberado:
**arquivo ausente** e **seção ausente**. "Não existe README" e "o README não
explica como instalar" pedem ações distintas, e juntá-los numa regra só tornaria
a recomendação vaga.

Severidades ficam em `low` e `medium`: documentação ausente é dívida, não
vulnerabilidade. Inflar isso competiria com achados de segurança no score.
"""

from app.engine.findings import FindingCategory
from app.engine.rules.registry import Rule, RuleRegistry

_D = FindingCategory.DOCUMENTATION


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


DOCUMENTATION_RULES: list[Rule] = [
    _rule(
        "DOC-001",
        "README ausente",
        "medium",
        "O repositório não tem README. É o primeiro arquivo que qualquer pessoa abre, e "
        "sem ele não há como saber o que o projeto faz nem como executá-lo.",
        "Crie um README explicando o propósito do projeto, como instalar e como usar.",
        0.95,
    ),
    _rule(
        "DOC-002",
        "README sem conteúdo substancial",
        "low",
        "O README existe mas tem pouco texto além de título e distintivos.",
        "Descreva o propósito do projeto, os pré-requisitos e os passos para executá-lo.",
        0.8,
    ),
    _rule(
        "DOC-003",
        "Instruções de instalação não encontradas",
        "medium",
        "Não foi encontrada seção explicando como instalar ou preparar o ambiente.",
        "Adicione uma seção de instalação com pré-requisitos e comandos.",
        0.7,
    ),
    _rule(
        "DOC-004",
        "Instruções de uso não encontradas",
        "medium",
        "Não foi encontrada seção mostrando como usar o projeto depois de instalado.",
        "Adicione uma seção de uso com pelo menos um exemplo executável.",
        0.7,
    ),
    _rule(
        "DOC-005",
        "Configuração não documentada",
        "low",
        "Não foi encontrada seção sobre variáveis de ambiente ou configuração — "
        "informação necessária para rodar o projeto fora da máquina de quem o escreveu.",
        "Documente as variáveis de ambiente e seus valores esperados, sem incluir valores reais.",
        0.6,
    ),
    _rule(
        "DOC-006",
        "Sem exemplos de código",
        "low",
        "O README não tem nenhum bloco de código. Exemplo executável costuma ensinar mais "
        "rápido que descrição em prosa.",
        "Inclua ao menos um bloco de código com o caso de uso mais comum.",
        0.75,
    ),
    _rule(
        "DOC-007",
        "LICENSE ausente",
        "medium",
        "Sem arquivo de licença, o padrão legal é que ninguém tem permissão para usar, "
        "modificar ou distribuir o código — mesmo que o repositório seja público.",
        "Adicione um arquivo LICENSE com a licença escolhida.",
        0.9,
    ),
    _rule(
        "DOC-008",
        "CONTRIBUTING ausente",
        "low",
        "O projeto não documenta como contribuir. Em repositório público, isso aumenta o "
        "custo de cada contribuição externa.",
        "Adicione um CONTRIBUTING explicando fluxo de branches, testes e revisão.",
        0.85,
    ),
]


def register_documentation_rules(registry: RuleRegistry) -> None:
    registry.register_all(DOCUMENTATION_RULES)
