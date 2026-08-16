"""Catálogo de regras de arquitetura (ARC-*).

Nenhuma destas afirma que a arquitetura está errada — não existe estrutura
universalmente correta. O que elas apontam são sinais conhecidos de custo de
manutenção, todos com confiança baixa e redação que evita veredito.
"""

from app.engine.findings import FindingCategory
from app.engine.rules.registry import Rule, RuleRegistry

_A = FindingCategory.ARCHITECTURE


def _rule(
    rule_id: str, name: str, severity: str, description: str, recommendation: str, confidence: float
) -> Rule:
    return Rule(
        rule_id=rule_id,
        name=name,
        category=_A,
        severity=severity,  # type: ignore[arg-type]
        description=description,
        recommendation=recommendation,
        confidence=confidence,
    )


ARCHITECTURE_RULES: list[Rule] = [
    _rule(
        "ARC-001",
        "Arquivo muito extenso",
        "medium",
        "Um arquivo com muitas linhas costuma acumular responsabilidades distintas, o que "
        "dificulta leitura, teste e revisão.",
        "Separe em módulos por responsabilidade. Comece extraindo o que tem menos "
        "dependências com o resto.",
        0.7,
    ),
    _rule(
        "ARC-002",
        "Arquivo excessivamente extenso",
        "high",
        "O arquivo é grande a ponto de dificultar qualquer alteração segura.",
        "Divida o arquivo antes de adicionar funcionalidade nova a ele.",
        0.8,
    ),
    _rule(
        "ARC-003",
        "Estrutura de diretórios muito profunda",
        "low",
        "Caminhos muito aninhados aumentam o custo de navegar e de importar módulos.",
        "Achate a hierarquia agrupando por domínio em vez de por camadas sucessivas.",
        0.5,
    ),
    _rule(
        "ARC-004",
        "Raiz do repositório com muitos arquivos",
        "low",
        "Muitos arquivos soltos na raiz dificultam localizar o que importa.",
        "Mova código para um diretório de fonte e mantenha na raiz apenas manifestos e "
        "documentação.",
        0.6,
    ),
    _rule(
        "ARC-005",
        "Sem separação aparente de responsabilidades",
        "medium",
        "Não foi encontrado nenhum diretório que sugira organização por camada ou domínio. "
        "Em projetos pequenos isso é aceitável; conforme cresce, vira obstáculo.",
        "Adote uma organização explícita — por domínio ou por camada — e mantenha-a "
        "consistente.",
        0.5,
    ),
    _rule(
        "ARC-006",
        "Diretório com arquivos demais",
        "low",
        "Um único diretório concentra muitos arquivos, o que costuma indicar que ele virou "
        "depósito em vez de unidade coesa.",
        "Subdivida por subdomínio ou responsabilidade.",
        0.5,
    ),
]


def register_architecture_rules(registry: RuleRegistry) -> None:
    registry.register_all(ARCHITECTURE_RULES)
