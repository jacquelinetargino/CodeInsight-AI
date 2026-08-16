"""Catálogo de regras de Git (GIT-*).

Cobrem dois riscos distintos: **o que foi versionado** (arquivo sensível,
binário grande) e **como o repositório é operado** (proteção de branch,
concentração de autoria, qualidade do histórico).

Nenhuma regra reporta conteúdo de arquivo sensível — apenas o caminho, que é o
que o usuário precisa para agir.
"""

from app.engine.findings import FindingCategory
from app.engine.rules.registry import Rule, RuleRegistry

_G = FindingCategory.GIT


def _rule(
    rule_id: str, name: str, severity: str, description: str, recommendation: str, confidence: float
) -> Rule:
    return Rule(
        rule_id=rule_id,
        name=name,
        category=_G,
        severity=severity,  # type: ignore[arg-type]
        description=description,
        recommendation=recommendation,
        confidence=confidence,
    )


GIT_RULES: list[Rule] = [
    _rule(
        "GIT-001",
        "Arquivo sensível versionado",
        "critical",
        "Um arquivo que costuma conter credencial ou dado privado está no repositório. "
        "Removê-lo agora não resolve: o conteúdo permanece recuperável em todo o histórico.",
        "Remova o arquivo, rotacione o que estava nele e reescreva o histórico com "
        "git-filter-repo se o repositório for público.",
        0.85,
    ),
    _rule(
        "GIT-002",
        "Arquivo grande versionado",
        "medium",
        "O git guarda todas as versões de cada arquivo. Um arquivo grande incha o "
        "repositório permanentemente e torna cada clone mais lento.",
        "Mova o arquivo para armazenamento externo ou use Git LFS.",
        0.8,
    ),
    _rule(
        "GIT-003",
        "Branch principal sem proteção",
        "high",
        "A branch principal aceita escrita direta. Sem revisão obrigatória, qualquer "
        "alteração — inclusive uma feita por engano — chega à linha principal.",
        "Ative a proteção da branch exigindo pull request e checagens de CI aprovadas.",
        0.85,
    ),
    _rule(
        "GIT-004",
        "Autoria concentrada em uma pessoa",
        "medium",
        "Todos os commits recentes vêm do mesmo autor. É um risco de continuidade: o "
        "conhecimento do projeto não está distribuído.",
        "Distribua a autoria por revisão de código e programação em par.",
        0.7,
    ),
    _rule(
        "GIT-005",
        "Histórico com mensagens pouco informativas",
        "low",
        "Boa parte dos commits recentes tem mensagens que não dizem o que mudou. Isso "
        "dificulta entender uma alteração meses depois e investigar uma regressão.",
        "Descreva o que mudou e por quê. Uma convenção como Conventional Commits ajuda a "
        "manter consistência.",
        0.7,
    ),
    _rule(
        "GIT-006",
        "Sem uso de pull requests",
        "low",
        "Não há pull requests mergeados no histórico recente, o que sugere que as "
        "alterações entram sem revisão.",
        "Adote pull requests mesmo em projeto individual: eles dão um ponto natural para "
        "o CI rodar antes do merge.",
        0.6,
    ),
]


def register_git_rules(registry: RuleRegistry) -> None:
    registry.register_all(GIT_RULES)
