"""Analyzer AST de Python.

Todo código nestes testes é **dado**: passa por `ast.parse` e nunca é executado.
Vários trechos são propositalmente perigosos — se alguma vez rodassem, os testes
falhariam de formas óbvias.
"""

import ast
import textwrap

import pytest

from app.engine.rules.python_ast import (
    MAX_COMPLEXITY,
    MAX_FUNCTION_LINES,
    analyze_python,
)


def kinds(source: str) -> set[str]:
    return {issue.kind for issue in analyze_python(textwrap.dedent(source)).issues}


# --- garantia central: nada é executado -------------------------------------


def test_analysis_never_executes_the_code(tmp_path):
    """Um módulo que escreveria arquivo e falharia ao rodar é apenas lido."""
    marcador = tmp_path / "nunca-deve-existir.txt"
    fonte = f"""
        from pathlib import Path
        Path({str(marcador)!r}).write_text("executado")
        raise SystemExit("este modulo nao pode rodar")
    """

    relatorio = analyze_python(textwrap.dedent(fonte))

    assert relatorio.parse_error is None
    assert not marcador.exists()


def test_module_with_side_effects_is_not_imported():
    relatorio = analyze_python("import os\nos.environ['INVADIDO'] = '1'\n")
    assert relatorio.parse_error is None
    import os

    assert "INVADIDO" not in os.environ


# --- erro de sintaxe --------------------------------------------------------


@pytest.mark.parametrize(
    "fonte",
    [
        "print 'python 2'",  # sintaxe do Python 2
        "def quebrado(:\n    pass",
        "isto nao e python de jeito nenhum {{{",
    ],
)
def test_invalid_syntax_is_reported_not_raised(fonte: str):
    """Repositório de terceiros tem código quebrado; isso não pode derrubar a análise."""
    relatorio = analyze_python(fonte)
    assert relatorio.parse_error is not None
    assert relatorio.issues == []


def test_parse_error_distinguishes_from_clean_file():
    """Arquivo limpo e arquivo ilegível não podem parecer a mesma coisa."""
    limpo = analyze_python("x = 1\n")
    quebrado = analyze_python("def (:")

    assert limpo.parse_error is None
    assert quebrado.parse_error is not None


def test_empty_source():
    relatorio = analyze_python("")
    assert relatorio.parse_error is None
    assert relatorio.issues == []


# --- execução dinâmica ------------------------------------------------------


@pytest.mark.parametrize(
    ("fonte", "esperado"),
    [
        ("eval(entrada)", "dangerous-eval"),
        ("exec(codigo)", "dangerous-exec"),
        ("compile(fonte, '<x>', 'exec')", "dangerous-compile"),
        ("import os\nos.system('ls')", "os-command-execution"),
        ("import os\nos.popen('ls')", "os-command-execution"),
    ],
)
def test_detects_dynamic_execution(fonte: str, esperado: str):
    assert esperado in kinds(fonte)


def test_detects_subprocess_with_shell_true():
    achados = kinds("import subprocess\nsubprocess.run(cmd, shell=True)")
    assert "subprocess-shell-true" in achados


def test_subprocess_without_shell_is_lower_severity_kind():
    """Usar subprocess não é igual a usar shell=True — são achados diferentes."""
    achados = kinds("import subprocess\nsubprocess.run(['ls', '-l'])")
    assert "subprocess-usage" in achados
    assert "subprocess-shell-true" not in achados


# --- desserialização e criptografia -----------------------------------------


@pytest.mark.parametrize(
    ("fonte", "esperado"),
    [
        ("import pickle\npickle.loads(dados)", "unsafe-deserialization"),
        ("import marshal\nmarshal.loads(dados)", "unsafe-deserialization"),
        ("import yaml\nyaml.load(conteudo)", "yaml-unsafe-load"),
        ("import hashlib\nhashlib.md5(senha)", "weak-hash"),
        ("import hashlib\nhashlib.sha1(senha)", "weak-hash"),
    ],
)
def test_detects_unsafe_apis(fonte: str, esperado: str):
    assert esperado in kinds(fonte)


def test_yaml_safe_load_is_not_reported():
    assert "yaml-unsafe-load" not in kinds("import yaml\nyaml.load(c, Loader=yaml.SafeLoader)")


def test_sha256_is_not_reported():
    assert "weak-hash" not in kinds("import hashlib\nhashlib.sha256(dados)")


# --- SQL --------------------------------------------------------------------


@pytest.mark.parametrize(
    "fonte",
    [
        'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")',
        'cursor.execute("SELECT * FROM users WHERE id = " + user_id)',
        'cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)',
    ],
)
def test_detects_sql_built_by_interpolation(fonte: str):
    assert "sql-injection-risk" in kinds(fonte)


def test_parameterized_sql_is_not_reported():
    """Consulta parametrizada é justamente a forma correta."""
    achados = kinds('cursor.execute("SELECT * FROM users WHERE id = %s", [user_id])')
    assert "sql-injection-risk" not in achados


def test_dynamic_string_without_sql_is_not_reported():
    """f-string em log não é injeção de SQL."""
    assert "sql-injection-risk" not in kinds('logger.execute(f"processando {item}")')


# --- rede -------------------------------------------------------------------


@pytest.mark.parametrize("modulo", ["requests", "httpx"])
def test_detects_request_without_timeout(modulo: str):
    assert "request-without-timeout" in kinds(f"import {modulo}\n{modulo}.get(url)")


@pytest.mark.parametrize("modulo", ["requests", "httpx"])
def test_request_with_timeout_is_not_reported(modulo: str):
    assert "request-without-timeout" not in kinds(f"import {modulo}\n{modulo}.get(url, timeout=10)")


# --- tratamento de exceção --------------------------------------------------


def test_detects_bare_except():
    assert "bare-except" in kinds("try:\n    f()\nexcept:\n    pass")


def test_detects_broad_except():
    assert "broad-except" in kinds("try:\n    f()\nexcept Exception:\n    log()")


def test_detects_silenced_exception():
    achados = kinds("try:\n    f()\nexcept ValueError:\n    pass")
    assert "silenced-exception" in achados


def test_specific_except_with_handling_is_clean():
    fonte = """
        try:
            f()
        except ValueError as exc:
            logger.warning("falhou: %s", exc)
    """
    achados = kinds(fonte)
    assert "bare-except" not in achados
    assert "broad-except" not in achados
    assert "silenced-exception" not in achados


def test_detects_assert_used_for_validation():
    assert "assert-for-validation" in kinds("def f(x):\n    assert x > 0\n    return x")


# --- métricas ---------------------------------------------------------------


def test_detects_long_function():
    corpo = "\n".join(f"    x{i} = {i}" for i in range(MAX_FUNCTION_LINES + 10))
    assert "function-too-long" in kinds(f"def grande():\n{corpo}")


def test_short_function_is_clean():
    assert "function-too-long" not in kinds("def pequena():\n    return 1")


def test_detects_complex_function():
    condicoes = "\n".join(
        f"    if x == {i}:\n        return {i}" for i in range(MAX_COMPLEXITY + 3)
    )
    assert "function-too-complex" in kinds(f"def ramificada(x):\n{condicoes}")


def test_detects_too_many_arguments():
    assert "too-many-arguments" in kinds("def f(a, b, c, d, e, f_, g, h):\n    return a")


def test_self_does_not_count_as_argument():
    """Métodos não podem ser penalizados por `self`, que é imposto pela linguagem."""
    fonte = "class C:\n    def m(self, a, b, c, d, e, f):\n        return a"
    assert "too-many-arguments" not in kinds(fonte)


def test_detects_mutable_default_argument():
    assert "mutable-default-argument" in kinds("def f(itens=[]):\n    return itens")


def test_immutable_default_is_clean():
    assert "mutable-default-argument" not in kinds("def f(itens=None):\n    return itens or []")


def test_collects_function_metrics():
    fonte = """
        def alpha(a, b):
            if a:
                return b
            return a

        async def beta():
            return 1
    """
    relatorio = analyze_python(textwrap.dedent(fonte))
    por_nome = {f.name: f for f in relatorio.functions}

    assert set(por_nome) == {"alpha", "beta"}
    assert por_nome["alpha"].arguments == 2
    assert por_nome["alpha"].complexity == 2  # base + um if
    assert por_nome["beta"].complexity == 1


def test_collects_class_metrics_and_imports():
    fonte = """
        import os
        from pathlib import Path
        from app.core.config import get_settings

        class Servico:
            def metodo(self):
                return os.getcwd()
    """
    relatorio = analyze_python(textwrap.dedent(fonte))

    assert [c.name for c in relatorio.classes] == ["Servico"]
    assert relatorio.imports == {"os", "pathlib", "app"}


def test_detects_large_class():
    metodos = "\n\n".join(f"    def m{i}(self):\n        return {i}" for i in range(120))
    assert "class-too-large" in kinds(f"class Enorme:\n{metodos}")


# --- evidência e localização ------------------------------------------------


def test_issue_has_line_and_evidence():
    fonte = "import os\n\n\nos.system('rm -rf /')\n"
    (ocorrencia,) = [i for i in analyze_python(fonte).issues if i.kind == "os-command-execution"]

    assert ocorrencia.line == 4
    assert "os.system" in ocorrencia.evidence
    assert ocorrencia.detail


def test_evidence_is_truncated():
    linha_longa = "eval(" + "'x' + " * 200 + "'fim')"
    (ocorrencia,) = [i for i in analyze_python(linha_longa).issues if i.kind == "dangerous-eval"]
    assert len(ocorrencia.evidence) <= 200


# --- determinismo -----------------------------------------------------------


def test_analysis_is_deterministic():
    fonte = "import os\nos.system('ls')\ntry:\n    f()\nexcept:\n    pass"
    primeiro = analyze_python(fonte)
    segundo = analyze_python(fonte)
    assert primeiro.issues == segundo.issues


def test_clean_module_produces_no_issues():
    fonte = """
        import logging

        logger = logging.getLogger(__name__)


        def somar(a: int, b: int) -> int:
            return a + b
    """
    relatorio = analyze_python(textwrap.dedent(fonte))
    assert relatorio.issues == []
    assert relatorio.parse_error is None


def test_analyzes_this_project_without_crashing():
    """O motor precisa aguentar código real, não só exemplos de teste."""
    from pathlib import Path

    alvo = Path(__file__).parent.parent / "app" / "engine" / "scanner.py"
    relatorio = analyze_python(alvo.read_text(encoding="utf-8"))

    assert relatorio.parse_error is None
    assert relatorio.functions


def test_uses_ast_module_not_execution():
    """Salvaguarda explícita: o módulo depende de `ast`, não de exec/eval."""
    import app.engine.rules.python_ast as modulo

    fonte = ast.parse(Path_read(modulo.__file__))
    chamadas = {
        no.func.id
        for no in ast.walk(fonte)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
    }
    assert "exec" not in chamadas
    assert "eval" not in chamadas
    assert "__import__" not in chamadas


def Path_read(caminho: str) -> str:
    from pathlib import Path

    return Path(caminho).read_text(encoding="utf-8")


# --- memoização --------------------------------------------------------------


def test_mesmo_conteudo_devolve_o_mesmo_relatorio():
    """Dois analyzers consomem este relatório; calcular duas vezes era 44% do
    tempo total da análise, medido por profiler."""
    from app.engine.rules.python_ast import analyze_python, clear_analysis_cache

    clear_analysis_cache()
    fonte = "def f(x=[]):\n    return x\n"
    assert analyze_python(fonte) is analyze_python(fonte)


def test_conteudos_diferentes_nao_se_confundem():
    """A chave é o digest do conteúdo — a trava contra o erro que um cache mal
    indexado produziria: o relatório de um arquivo aparecer em outro."""
    from app.engine.rules.python_ast import analyze_python, clear_analysis_cache

    clear_analysis_cache()
    um = analyze_python("def f(x=[]):\n    return x\n")
    outro = analyze_python("def g(a, b):\n    return a + b\n")

    assert um is not outro
    assert {i.kind for i in um.issues} != {i.kind for i in outro.issues}


def test_arquivo_invalido_tambem_e_memoizado():
    """Sintaxe inválida é comum em repositório de terceiros e o resultado é tão
    reaproveitável quanto o de um arquivo válido."""
    from app.engine.rules.python_ast import analyze_python, clear_analysis_cache

    clear_analysis_cache()
    primeiro = analyze_python("def f(\n")
    assert primeiro.parse_error
    assert analyze_python("def f(\n") is primeiro


def test_o_cache_tem_teto():
    """Sem teto, analisar repositórios grandes em sequência faria o processo
    crescer sem limite."""
    from app.engine.rules import python_ast

    python_ast.clear_analysis_cache()
    original = python_ast._CACHE_MAX_ENTRIES
    python_ast._CACHE_MAX_ENTRIES = 3
    try:
        for i in range(10):
            python_ast.analyze_python(f"x = {i}\n")
        assert len(python_ast._CACHE) <= 4
    finally:
        python_ast._CACHE_MAX_ENTRIES = original
        python_ast.clear_analysis_cache()
