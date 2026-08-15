"""Análise de JavaScript e TypeScript por padrões textuais.

Diferente do Python, aqui não há parser na biblioteca padrão — e instalar um
runtime de JS para analisar código de terceiros seria exatamente o que o motor
promete não fazer. Então o código é tratado como **texto não confiável**: nunca
executado, nunca passado para `node`, nunca interpretado.

A consequência honesta dessa escolha é menos precisão que a análise AST do
Python. Por isso as ocorrências daqui carregam confiança mais baixa, e o
analyzer que as consome reflete isso no achado.
"""

import re
from dataclasses import dataclass, field

MAX_EVIDENCE_CHARS = 200

# Comentários de linha e de bloco geram a maior parte dos falsos positivos:
# um exemplo de código dentro de JSDoc não é código executável.
_LINE_COMMENT_RE = re.compile(r"^\s*(//|/\*|\*|\*/)")


@dataclass(frozen=True)
class JavaScriptIssue:
    kind: str
    line: int
    evidence: str
    detail: str = ""


@dataclass
class JavaScriptReport:
    issues: list[JavaScriptIssue] = field(default_factory=list)
    # Sem parser não há erro de sintaxe detectável; o campo existe para manter
    # a mesma forma do relatório de Python.
    parse_error: str | None = None


@dataclass(frozen=True)
class _Pattern:
    kind: str
    regex: re.Pattern[str]
    detail: str


def _p(kind: str, pattern: str, detail: str) -> _Pattern:
    return _Pattern(kind, re.compile(pattern), detail)


JS_PATTERNS: list[_Pattern] = [
    # --- execução dinâmica ---
    _p("js-eval", r"\beval\s*\(", "eval() executa qualquer string recebida"),
    _p(
        "js-function-constructor",
        r"\bnew\s+Function\s*\(",
        "new Function() compila código em tempo de execução",
    ),
    _p(
        "js-settimeout-string",
        r"\bset(?:Timeout|Interval)\s*\(\s*[\"'`]",
        "setTimeout/setInterval com string executa código como eval",
    ),
    # --- XSS ---
    _p(
        "js-inner-html",
        r"\.(?:innerHTML|outerHTML)\s*=",
        "Atribuir HTML dinâmico permite injeção de script",
    ),
    _p(
        "js-document-write",
        r"\bdocument\.write(?:ln)?\s*\(",
        "document.write injeta HTML sem sanitização",
    ),
    _p(
        "js-dangerously-set-html",
        r"\bdangerouslySetInnerHTML\b",
        "dangerouslySetInnerHTML ignora a proteção do React contra XSS",
    ),
    _p(
        "js-insert-adjacent-html",
        r"\.insertAdjacentHTML\s*\(",
        "insertAdjacentHTML injeta HTML sem sanitização",
    ),
    # --- comando do sistema (Node) ---
    _p(
        "js-child-process-exec",
        r"\b(?:child_process\.)?exec(?:Sync)?\s*\(",
        "exec() do child_process passa a string pelo shell",
    ),
    # --- criptografia e aleatoriedade ---
    # A palavra que denuncia o uso de segurança pode vir antes
    # (`const token = Math.random()`) ou depois (`Math.random() as token`).
    _p(
        "js-math-random-security",
        r"(?i)(?:\b(?:token|secret|password|senha|nonce|salt|uuid|session)\b[^\n]{0,80}"
        r"Math\.random\s*\(|Math\.random\s*\([^\n]{0,80}"
        r"\b(?:token|secret|password|senha|nonce|salt|uuid|session)\b)",
        "Math.random() não é criptograficamente seguro",
    ),
    # --- transporte e armazenamento ---
    _p(
        "js-insecure-transport",
        r"[\"'`]http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)",
        "URL em http:// trafega sem criptografia",
    ),
    # Case-insensitive: a chave costuma vir em camelCase (`authToken`).
    _p(
        "js-credential-in-storage",
        r"(?i)\b(?:localStorage|sessionStorage)\.setItem\s*\(\s*[\"'`][^\"'`]*"
        r"(?:token|jwt|secret|password|senha|apikey|api_key|credential)",
        "Credencial em localStorage fica acessível a qualquer script da página",
    ),
    # --- qualidade (consumidas por outro analyzer) ---
    _p("js-console-log", r"\bconsole\.(?:log|debug|info)\s*\(", "console deixado em produção"),
    _p("js-debugger", r"^\s*debugger\s*;?\s*$", "debugger interrompe a execução no navegador"),
    _p("js-var-declaration", r"^\s*var\s+\w+", "var tem escopo de função; prefira let/const"),
    _p(
        "js-loose-equality",
        r"[^=!<>]==[^=]|[^=!]!=[^=]",
        "== faz coerção de tipo; prefira === e !==",
    ),
    _p(
        "js-ts-ignore",
        r"@ts-(?:ignore|nocheck)\b",
        "@ts-ignore desliga a checagem de tipos naquele ponto",
    ),
    _p("js-any-type", r":\s*any\b", "any anula a checagem de tipos do TypeScript"),
]


def _is_comment(line: str) -> bool:
    return bool(_LINE_COMMENT_RE.match(line))


def analyze_javascript(source: str) -> JavaScriptReport:
    """Varre JS/TS linha a linha.

    O conteúdo é tratado apenas como texto: nada é executado, nenhum runtime é
    invocado, nenhum módulo é resolvido. Linhas que são comentário são puladas,
    porque exemplo de código em JSDoc não é código executável.
    """
    relatorio = JavaScriptReport()

    for numero, linha in enumerate(source.splitlines(), start=1):
        if _is_comment(linha):
            continue

        for padrao in JS_PATTERNS:
            if padrao.regex.search(linha):
                relatorio.issues.append(
                    JavaScriptIssue(
                        kind=padrao.kind,
                        line=numero,
                        evidence=linha.strip()[:MAX_EVIDENCE_CHARS],
                        detail=padrao.detail,
                    )
                )

    return relatorio
