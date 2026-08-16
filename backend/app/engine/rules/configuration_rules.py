"""Catálogo de regras de configuração (CFG-*).

Cobrem infraestrutura declarada em arquivo: Dockerfile, compose, CI e
.gitignore. Nenhuma imagem é construída e nenhum workflow executado — tudo vem
da leitura do texto.
"""

from app.engine.findings import FindingCategory
from app.engine.rules.registry import Rule, RuleRegistry

_C = FindingCategory.CONFIGURATION


def _rule(
    rule_id: str, name: str, severity: str, description: str, recommendation: str, confidence: float
) -> Rule:
    return Rule(
        rule_id=rule_id,
        name=name,
        category=_C,
        severity=severity,  # type: ignore[arg-type]
        description=description,
        recommendation=recommendation,
        confidence=confidence,
    )


CONFIGURATION_RULES: list[Rule] = [
    _rule(
        "CFG-001",
        "Container executa como root",
        "high",
        "O Dockerfile não define um usuário não privilegiado. O padrão do Docker é root, "
        "então qualquer falha na aplicação vira acesso root dentro do container.",
        "Crie um usuário sem privilégio e declare `USER` antes do comando de inicialização.",
        0.9,
    ),
    _rule(
        "CFG-002",
        "Imagem base sem versão fixa",
        "medium",
        "A imagem base usa `latest` ou não tem tag. A mesma build produz imagens diferentes "
        "ao longo do tempo, e uma atualização de terceiros pode quebrar ou comprometer o "
        "container sem nenhuma alteração no repositório.",
        "Fixe uma tag específica, ou o digest `@sha256:` para imutabilidade real.",
        0.85,
    ),
    _rule(
        "CFG-003",
        "Credencial embutida na imagem",
        "critical",
        "Um valor de senha, token ou chave está escrito no Dockerfile. Ele fica gravado "
        "numa camada da imagem e permanece recuperável mesmo se removido depois.",
        "Injete o valor em tempo de execução por variável de ambiente ou secret do "
        "orquestrador, e rotacione a credencial exposta.",
        0.9,
    ),
    _rule(
        "CFG-004",
        "Download remoto durante o build",
        "medium",
        "`ADD` com URL busca conteúdo externo no momento do build, sem verificação de "
        "integridade — o que for servido naquele instante entra na imagem.",
        "Baixe com verificação de checksum, ou use o gerenciador de pacotes do sistema.",
        0.8,
    ),
    _rule(
        "CFG-005",
        "Container privilegiado",
        "critical",
        "`privileged: true` remove praticamente todo o isolamento do container em relação "
        "ao host.",
        "Remova o modo privilegiado e conceda apenas as capacidades específicas necessárias.",
        0.95,
    ),
    _rule(
        "CFG-006",
        "Rede do host compartilhada",
        "high",
        "`network_mode: host` faz o container usar a pilha de rede do host, sem isolamento.",
        "Use a rede padrão do compose e publique apenas as portas necessárias.",
        0.9,
    ),
    _rule(
        "CFG-007",
        "Ação de CI sem versão imutável",
        "medium",
        "A ação é referenciada por tag, que pode ser reapontada para outro commit. Um "
        "comprometimento da ação executa código arbitrário com acesso ao repositório e aos "
        "secrets do CI.",
        "Fixe o commit completo (`@` seguido do sha de 40 caracteres).",
        0.8,
    ),
    _rule(
        "CFG-008",
        "Script remoto executado direto no shell",
        "high",
        "Um `curl` canalizado para o shell executa o que o servidor devolver naquele "
        "momento, sem revisão nem verificação.",
        "Baixe o script, verifique o checksum e só então execute.",
        0.9,
    ),
    _rule(
        "CFG-009",
        ".gitignore ausente",
        "medium",
        "Sem .gitignore, arquivos de ambiente, credenciais e artefatos de build podem ser "
        "versionados por acidente.",
        "Adicione um .gitignore cobrindo ambiente, credenciais, dependências e build.",
        0.9,
    ),
    _rule(
        "CFG-010",
        ".gitignore sem entradas críticas",
        "medium",
        "O .gitignore existe mas não cobre categorias cujo versionamento acidental causa "
        "vazamento ou poluição do repositório.",
        "Inclua as categorias faltantes — em especial arquivos de ambiente e credenciais.",
        0.8,
    ),
    _rule(
        "CFG-011",
        "Container sem verificação de saúde",
        "low",
        "Sem `HEALTHCHECK`, o orquestrador considera o container saudável enquanto o "
        "processo existir, mesmo que a aplicação esteja travada.",
        "Declare um HEALTHCHECK que exercite de fato a aplicação.",
        0.7,
    ),
]


def register_configuration_rules(registry: RuleRegistry) -> None:
    registry.register_all(CONFIGURATION_RULES)
