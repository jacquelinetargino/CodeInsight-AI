"""Catálogo de regras de qualidade de código (QUA-*).

Cobrem duas famílias: **manutenibilidade** (função longa, complexidade,
argumentos demais) e **tratamento de erro** (`except` genérico, exceção
descartada). Nenhuma é sobre estilo — indentação e aspas ficam para o
formatador, e reportá-las aqui só ensinaria o usuário a ignorar o relatório.

As severidades são deliberadamente baixas: código difícil de manter é um custo
que se paga aos poucos, não um incidente. O que empurra o score para baixo é o
acúmulo, e o cálculo já trata isso com retorno decrescente.
"""

from app.engine.findings import FindingCategory
from app.engine.rules.registry import Rule, RuleRegistry

_Q = FindingCategory.QUALITY


def _rule(
    rule_id: str, name: str, severity: str, description: str, recommendation: str, confidence: float
) -> Rule:
    return Rule(
        rule_id=rule_id,
        name=name,
        category=_Q,
        severity=severity,  # type: ignore[arg-type]
        description=description,
        recommendation=recommendation,
        confidence=confidence,
    )


QUALITY_RULES: list[Rule] = [
    _rule(
        "QUA-001",
        "Função longa demais",
        "low",
        "A função tem mais linhas do que cabe na cabeça de quem lê. Funções assim "
        "concentram várias responsabilidades e ficam difíceis de testar isoladamente.",
        "Extraia blocos coesos para funções com nome próprio.",
        0.8,
    ),
    _rule(
        "QUA-002",
        "Função complexa demais",
        "medium",
        "A quantidade de caminhos de execução da função é alta. Cada ramo é um caso "
        "a mais para testar e um lugar a mais onde um bug pode se esconder.",
        "Reduza os ramos: cláusulas de guarda, extração de decisões para funções "
        "com nome, ou tabela de despacho no lugar de encadeamento de if.",
        0.8,
    ),
    _rule(
        "QUA-003",
        "Classe grande demais",
        "low",
        "A classe acumulou responsabilidades a ponto de ninguém conseguir descrevê-la "
        "em uma frase.",
        "Separe as responsabilidades em classes ou módulos distintos.",
        0.75,
    ),
    _rule(
        "QUA-004",
        "Argumentos demais",
        "low",
        "Uma lista longa de parâmetros costuma indicar que falta um tipo: os valores "
        "andam juntos e deveriam viajar juntos.",
        "Agrupe os parâmetros relacionados num dataclass ou modelo.",
        0.75,
    ),
    _rule(
        "QUA-005",
        "Argumento padrão mutável",
        "medium",
        "O valor padrão é criado uma única vez, na definição da função, e passa a ser "
        "compartilhado por todas as chamadas. O estado vaza de uma chamada para a "
        "seguinte — é um bug silencioso, não um detalhe de estilo.",
        "Use None como padrão e crie a lista ou o dicionário dentro da função.",
        0.9,
    ),
    _rule(
        "QUA-006",
        "except sem tipo",
        "medium",
        "`except:` captura tudo, inclusive KeyboardInterrupt e SystemExit. Um Ctrl+C "
        "deixa de encerrar o programa e a causa real do erro desaparece.",
        "Capture a exceção específica que você sabe tratar.",
        0.9,
    ),
    _rule(
        "QUA-007",
        "except genérico",
        "low",
        "Capturar Exception esconde falhas que não estavam previstas, e o erro real "
        "só aparece muito depois, em outro lugar.",
        "Capture as exceções esperadas; deixe as inesperadas subirem.",
        0.7,
    ),
    _rule(
        "QUA-008",
        "Exceção descartada",
        "medium",
        "A exceção é capturada e o bloco não faz nada com ela. A falha acontece e "
        "ninguém fica sabendo — nem log, nem métrica, nem mensagem.",
        "Registre a exceção ou trate-a de fato. Se ignorar for mesmo a intenção, "
        "deixe isso explícito com contextlib.suppress e um comentário.",
        0.8,
    ),
    _rule(
        "QUA-009",
        "assert usado para validação",
        "medium",
        "`assert` é removido quando o Python roda com -O. Uma validação escrita com "
        "assert simplesmente deixa de existir em produção.",
        "Valide com if e levante a exceção apropriada.",
        0.85,
    ),
    _rule(
        "QUA-010",
        "Chamada de rede sem timeout",
        "medium",
        "Sem timeout, a chamada pode ficar pendurada indefinidamente e prender a "
        "thread ou o worker que a executou.",
        "Passe um timeout explícito em toda chamada de rede.",
        0.85,
    ),
    _rule(
        "QUA-011",
        "Declaração com var",
        "low",
        "`var` tem escopo de função e sofre hoisting, o que produz surpresas em " "laços e blocos.",
        "Use let ou const.",
        0.7,
    ),
    _rule(
        "QUA-012",
        "console.log em produção",
        "low",
        "Chamadas de log esquecidas poluem o console e, às vezes, expõem dados que "
        "não deveriam aparecer no navegador do usuário.",
        "Remova ou troque por um logger que respeite o ambiente.",
        0.6,
    ),
    _rule(
        "QUA-013",
        "debugger esquecido",
        "medium",
        "Um `debugger` versionado trava a execução quando as ferramentas de "
        "desenvolvimento estão abertas.",
        "Remova a instrução antes do commit.",
        0.85,
    ),
    _rule(
        "QUA-014",
        "Uso do tipo any",
        "low",
        "`any` desliga a verificação de tipos justamente onde ela seria útil, e o "
        "erro reaparece em tempo de execução.",
        "Descreva o tipo real ou use unknown com verificação explícita.",
        0.6,
    ),
]


def register_quality_rules(registry: RuleRegistry) -> None:
    registry.register_all(QUALITY_RULES)
