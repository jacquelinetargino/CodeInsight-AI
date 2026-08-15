"""Análise estática de Python pela árvore sintática.

`ast.parse` constrói a árvore **sem executar nada**: decoradores não rodam,
código de nível de módulo não roda, imports não são resolvidos. É por isso que
esta é a forma segura de analisar código de terceiros — e é uma garantia da
biblioteca padrão, não uma promessa nossa.

O módulo só detecta e localiza. Transformar ocorrência em achado, com regra e
severidade, é trabalho do analyzer que consome isto.
"""

import ast
from dataclasses import dataclass, field

# Trecho de código na evidência serve para o humano se situar, não para
# reproduzir o arquivo.
MAX_EVIDENCE_CHARS = 200

# Acima disto uma função deixa de caber na cabeça de quem lê. O valor é
# convencional, não científico — por isso os achados derivados são heurísticos.
MAX_FUNCTION_LINES = 50
MAX_CLASS_LINES = 300
MAX_COMPLEXITY = 10
MAX_ARGUMENTS = 6

# Funções cuja simples presença já é o problema.
_DANGEROUS_BUILTINS = {"eval", "exec", "compile"}
_DANGEROUS_OS_CALLS = {"system", "popen", "spawn", "spawnl", "spawnv"}
# Desserialização que executa código embutido no dado.
_UNSAFE_DESERIALIZERS = {("pickle", "loads"), ("pickle", "load"), ("marshal", "loads")}
# Chamadas de rede que travam para sempre sem timeout.
_NETWORK_CALLS = {"get", "post", "put", "delete", "patch", "head", "options", "request"}
_NETWORK_MODULES = {"requests", "httpx"}
# Hashes quebrados para uso criptográfico.
_WEAK_HASHES = {"md5", "sha1"}


@dataclass(frozen=True)
class PythonIssue:
    """Uma ocorrência localizada. `kind` é o vocabulário que o analyzer mapeia
    para regras — manter o mapeamento fora daqui deixa este módulo focado em
    detectar, e o analyzer em classificar."""

    kind: str
    line: int
    evidence: str
    detail: str = ""


@dataclass
class FunctionMetrics:
    name: str
    line: int
    length: int
    complexity: int
    arguments: int


@dataclass
class PythonModuleReport:
    """Resultado da análise de um arquivo. `parse_error` distingue "arquivo
    limpo" de "arquivo que não deu para ler" — tratar os dois como iguais
    inflaria o score de um repositório cheio de código inválido."""

    issues: list[PythonIssue] = field(default_factory=list)
    functions: list[FunctionMetrics] = field(default_factory=list)
    classes: list[FunctionMetrics] = field(default_factory=list)
    imports: set[str] = field(default_factory=set)
    parse_error: str | None = None


def _evidence(source_lines: list[str], line: int) -> str:
    if 1 <= line <= len(source_lines):
        texto = source_lines[line - 1].strip()
        return texto[:MAX_EVIDENCE_CHARS]
    return ""


def _attribute_path(node: ast.AST) -> str:
    """Reconstrói `os.path.join` a partir dos nós encadeados de atributo."""
    partes: list[str] = []
    atual: ast.AST | None = node
    while isinstance(atual, ast.Attribute):
        partes.append(atual.attr)
        atual = atual.value
    if isinstance(atual, ast.Name):
        partes.append(atual.id)
    return ".".join(reversed(partes))


def _has_keyword(node: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in node.keywords)


def _keyword_is_true(node: ast.Call, name: str) -> bool:
    for kw in node.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


def _is_dynamic_string(node: ast.AST) -> bool:
    """f-string, concatenação com `+` ou `%`: indícios clássicos de SQL montado
    com dado externo."""
    if isinstance(node, ast.JoinedStr):  # f-string
        return any(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return True
    return False


def _looks_like_sql(node: ast.AST) -> bool:
    """Procura palavra-chave de SQL nas partes constantes da string."""
    fragmentos: list[str] = []
    for filho in ast.walk(node):
        if isinstance(filho, ast.Constant) and isinstance(filho.value, str):
            fragmentos.append(filho.value.upper())
    texto = " ".join(fragmentos)
    return any(kw in texto for kw in ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "WHERE "))


class _Visitor(ast.NodeVisitor):
    """Percorre a árvore acumulando ocorrências e métricas.

    Nunca avalia nós: só inspeciona estrutura. Um `ast.Constant` é lido como
    dado, jamais executado.
    """

    def __init__(self, source_lines: list[str]) -> None:
        self.source_lines = source_lines
        self.report = PythonModuleReport()

    # --- helpers ---

    def _add(self, kind: str, node: ast.AST, detail: str = "") -> None:
        line = getattr(node, "lineno", 0)
        self.report.issues.append(
            PythonIssue(
                kind=kind, line=line, evidence=_evidence(self.source_lines, line), detail=detail
            )
        )

    # --- imports ---

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.report.imports.add(alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.report.imports.add(node.module.split(".")[0])
        self.generic_visit(node)

    # --- chamadas ---

    def visit_Call(self, node: ast.Call) -> None:
        nome = node.func.id if isinstance(node.func, ast.Name) else _attribute_path(node.func)
        raiz = nome.split(".")[0]
        folha = nome.split(".")[-1]

        if isinstance(node.func, ast.Name) and node.func.id in _DANGEROUS_BUILTINS:
            self._add(f"dangerous-{node.func.id}", node, f"Uso de {node.func.id}()")

        if raiz == "os" and folha in _DANGEROUS_OS_CALLS:
            self._add("os-command-execution", node, f"Uso de {nome}()")

        if raiz == "subprocess":
            if _keyword_is_true(node, "shell"):
                self._add("subprocess-shell-true", node, "subprocess com shell=True")
            elif folha in {"run", "call", "check_call", "check_output", "Popen"}:
                self._add("subprocess-usage", node, f"Uso de {nome}()")

        if (raiz, folha) in _UNSAFE_DESERIALIZERS:
            self._add("unsafe-deserialization", node, f"{nome}() executa código embutido no dado")

        if raiz == "yaml" and folha == "load" and not _has_keyword(node, "Loader"):
            self._add("yaml-unsafe-load", node, "yaml.load() sem Loader seguro")

        if raiz == "hashlib" and folha in _WEAK_HASHES:
            self._add("weak-hash", node, f"hashlib.{folha}() não serve para uso criptográfico")

        if (
            raiz in _NETWORK_MODULES
            and folha in _NETWORK_CALLS
            and not _has_keyword(node, "timeout")
        ):
            self._add("request-without-timeout", node, f"{nome}() sem timeout")

        # SQL montado por concatenação ou f-string.
        if folha in {"execute", "executemany", "raw", "text"}:
            for argumento in node.args:
                if _is_dynamic_string(argumento) and _looks_like_sql(argumento):
                    self._add("sql-injection-risk", node, "SQL construído por interpolação")
                    break

        self.generic_visit(node)

    # --- tratamento de erro ---

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        corpo_vazio = len(node.body) == 1 and isinstance(node.body[0], ast.Pass)

        if node.type is None:
            self._add("bare-except", node, "except: captura até KeyboardInterrupt e SystemExit")
        elif isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}:
            self._add("broad-except", node, f"except {node.type.id} esconde falhas inesperadas")

        if corpo_vazio:
            self._add("silenced-exception", node, "Exceção capturada e descartada sem tratamento")

        self.generic_visit(node)

    # --- asserts ---

    def visit_Assert(self, node: ast.Assert) -> None:
        # `python -O` remove asserts: usá-los para validar entrada some em produção.
        self._add("assert-for-validation", node, "assert é removido com -O")
        self.generic_visit(node)

    # --- definições ---

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        comprimento = _node_length(node)
        self.report.classes.append(
            FunctionMetrics(
                name=node.name, line=node.lineno, length=comprimento, complexity=0, arguments=0
            )
        )
        if comprimento > MAX_CLASS_LINES:
            self._add("class-too-large", node, f"{node.name} tem {comprimento} linhas")
        self.generic_visit(node)

    def _record_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        comprimento = _node_length(node)
        complexidade = _cyclomatic_complexity(node)
        argumentos = _count_arguments(node)

        self.report.functions.append(
            FunctionMetrics(
                name=node.name,
                line=node.lineno,
                length=comprimento,
                complexity=complexidade,
                arguments=argumentos,
            )
        )

        if comprimento > MAX_FUNCTION_LINES:
            self._add("function-too-long", node, f"{node.name} tem {comprimento} linhas")
        if complexidade > MAX_COMPLEXITY:
            self._add("function-too-complex", node, f"{node.name} tem complexidade {complexidade}")
        if argumentos > MAX_ARGUMENTS:
            self._add("too-many-arguments", node, f"{node.name} recebe {argumentos} argumentos")

        # Argumento default mutável é compartilhado entre chamadas.
        for default in list(node.args.defaults) + [d for d in node.args.kw_defaults if d]:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self._add(
                    "mutable-default-argument",
                    node,
                    f"{node.name} usa default mutável, compartilhado entre chamadas",
                )
                break


def _node_length(node: ast.AST) -> int:
    fim = getattr(node, "end_lineno", None)
    inicio = getattr(node, "lineno", None)
    if fim is None or inicio is None:
        return 0
    return fim - inicio + 1


def _count_arguments(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    args = node.args
    total = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    # `self` e `cls` não contam: são impostos pelo modelo de objetos.
    if args.args and args.args[0].arg in {"self", "cls"}:
        total -= 1
    return total


def _cyclomatic_complexity(node: ast.AST) -> int:
    """Complexidade ciclomática aproximada: um caminho base mais um por ponto de
    decisão. Aproximada porque conta a estrutura, não os caminhos reais — o
    suficiente para sinalizar função difícil de testar."""
    complexidade = 1
    for filho in ast.walk(node):
        if isinstance(filho, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
            complexidade += 1
        elif isinstance(filho, ast.BoolOp):
            complexidade += len(filho.values) - 1
        elif isinstance(filho, ast.IfExp):
            complexidade += 1
        elif isinstance(filho, ast.comprehension):
            complexidade += 1 + len(filho.ifs)
        elif isinstance(filho, ast.Match):
            complexidade += len(filho.cases)
    return complexidade


def analyze_python(source: str) -> PythonModuleReport:
    """Analisa um módulo Python a partir do texto.

    Nunca executa nem importa o código: `ast.parse` só constrói a árvore.
    Arquivo com sintaxe inválida — comum em repositório de terceiros, que pode
    ter Python 2 ou código quebrado — devolve um relatório com `parse_error` em
    vez de derrubar a análise.
    """
    try:
        arvore = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as exc:
        return PythonModuleReport(parse_error=f"{type(exc).__name__}: {exc}")

    visitante = _Visitor(source.splitlines())
    visitante.visit(arvore)
    return visitante.report
