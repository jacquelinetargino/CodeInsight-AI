"""Analyzer de JavaScript/TypeScript.

Sem parser de JS na biblioteca padrão, a análise é textual — e o código nunca é
executado nem passado para nenhum runtime.
"""

import pytest

from app.engine.rules.javascript import JS_PATTERNS, analyze_javascript


def kinds(source: str) -> set[str]:
    return {issue.kind for issue in analyze_javascript(source).issues}


# --- execução dinâmica ------------------------------------------------------


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("const r = eval(entrada);", "js-eval"),
        ("const f = new Function('return 1');", "js-function-constructor"),
        ("setTimeout('alert(1)', 100);", "js-settimeout-string"),
        ('setInterval("tick()", 1000);', "js-settimeout-string"),
    ],
)
def test_detects_dynamic_execution(codigo: str, esperado: str):
    assert esperado in kinds(codigo)


def test_settimeout_with_function_is_clean():
    """A forma correta passa função, não string."""
    assert "js-settimeout-string" not in kinds("setTimeout(() => tick(), 100);")


# --- XSS --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("el.innerHTML = dadoDoUsuario;", "js-inner-html"),
        ("node.outerHTML = html;", "js-inner-html"),
        ("document.write(conteudo);", "js-document-write"),
        ("<div dangerouslySetInnerHTML={{ __html: html }} />", "js-dangerously-set-html"),
        ("el.insertAdjacentHTML('beforeend', html);", "js-insert-adjacent-html"),
    ],
)
def test_detects_html_injection(codigo: str, esperado: str):
    assert esperado in kinds(codigo)


def test_text_content_is_clean():
    """textContent é justamente a alternativa segura."""
    assert "js-inner-html" not in kinds("el.textContent = dadoDoUsuario;")


# --- Node -------------------------------------------------------------------


def test_detects_child_process_exec():
    assert "js-child-process-exec" in kinds("child_process.exec(`ls ${dir}`);")


# --- aleatoriedade e transporte ---------------------------------------------


def test_detects_math_random_for_security():
    assert "js-math-random-security" in kinds("const token = Math.random().toString(36);")


def test_math_random_for_animation_is_clean():
    """Math.random() em animação não é problema de segurança."""
    assert "js-math-random-security" not in kinds("const offset = Math.random() * 10;")


def test_detects_insecure_transport():
    assert "js-insecure-transport" in kinds('fetch("http://api.exemplo.com/dados");')


@pytest.mark.parametrize(
    "url",
    ['"https://api.exemplo.com"', '"http://localhost:3000"', '"http://127.0.0.1:8000"'],
)
def test_https_and_localhost_are_clean(url: str):
    assert "js-insecure-transport" not in kinds(f"fetch({url});")


def test_detects_credential_in_browser_storage():
    assert "js-credential-in-storage" in kinds('localStorage.setItem("authToken", token);')


def test_storing_preference_is_clean():
    assert "js-credential-in-storage" not in kinds('localStorage.setItem("theme", "dark");')


# --- qualidade --------------------------------------------------------------


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("console.log(valor);", "js-console-log"),
        ("  debugger;", "js-debugger"),
        ("var contador = 0;", "js-var-declaration"),
        ("if (a == b) return;", "js-loose-equality"),
        ("// @ts-ignore", "js-ts-ignore"),
        ("const dados: any = resposta;", "js-any-type"),
    ],
)
def test_detects_quality_issues(codigo: str, esperado: str):
    # `@ts-ignore` costuma vir em comentário; o teste usa a forma inline.
    fonte = codigo if not codigo.startswith("//") else f"const x = 1; {codigo[3:]}"
    assert esperado in kinds(fonte)


def test_strict_equality_is_clean():
    assert "js-loose-equality" not in kinds("if (a === b) return;")


def test_let_and_const_are_clean():
    assert "js-var-declaration" not in kinds("let contador = 0;\nconst total = 1;")


# --- comentários ------------------------------------------------------------


@pytest.mark.parametrize(
    "linha",
    [
        "// const r = eval(x);",
        "  * @example el.innerHTML = html;",
        "/* document.write(a); */",
    ],
)
def test_comments_are_skipped(linha: str):
    """Exemplo de código em JSDoc não é código executável."""
    assert analyze_javascript(linha).issues == []


# --- forma e robustez -------------------------------------------------------


def test_reports_line_and_evidence():
    fonte = "const a = 1;\n\nel.innerHTML = perigoso;\n"
    (ocorrencia,) = [i for i in analyze_javascript(fonte).issues if i.kind == "js-inner-html"]

    assert ocorrencia.line == 3
    assert "innerHTML" in ocorrencia.evidence
    assert ocorrencia.detail


def test_empty_and_clean_sources():
    assert analyze_javascript("").issues == []
    assert analyze_javascript("export const soma = (a: number, b: number) => a + b;\n").issues == []


def test_is_deterministic():
    fonte = "eval(x);\nel.innerHTML = y;\n"
    assert analyze_javascript(fonte).issues == analyze_javascript(fonte).issues


def test_never_executes_javascript(monkeypatch):
    """Nenhum runtime é invocado para analisar JS."""
    import os
    import subprocess

    def explode(*args, **kwargs):  # pragma: no cover - só falha se for chamado
        raise AssertionError("o analyzer nao pode invocar runtime de JS")

    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(subprocess, "Popen", explode)
    monkeypatch.setattr(os, "system", explode)

    relatorio = analyze_javascript("require('child_process').exec('rm -rf /');")
    assert relatorio.issues


def test_pattern_kinds_are_unique():
    tipos = [p.kind for p in JS_PATTERNS]
    assert len(tipos) == len(set(tipos))


def test_all_patterns_have_detail():
    for padrao in JS_PATTERNS:
        assert padrao.detail


def test_analyzes_this_projects_frontend():
    """Código real do frontend deste repositório, não só fixtures."""
    from pathlib import Path

    raiz = Path(__file__).parent.parent.parent / "frontend" / "src"
    if not raiz.exists():  # pragma: no cover - frontend ausente em alguns checkouts
        pytest.skip("frontend não disponível")

    arquivos = list(raiz.rglob("*.tsx")) + list(raiz.rglob("*.ts"))
    assert arquivos

    for arquivo in arquivos:
        relatorio = analyze_javascript(arquivo.read_text(encoding="utf-8", errors="replace"))
        assert relatorio.parse_error is None
