"""O achado declara de onde veio a evidência.

A confiança sozinha não separava as coisas: `os.system()` confirmado pela árvore
sintática sai com 0.85 e um casamento de regex em JavaScript com 0.7 — números
diferentes que caem na mesma faixa de rótulo e chegavam ao usuário como se
fossem a mesma evidência.
"""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.engine.findings import DetectionMethod, Finding
from app.engine.pipeline import analyze_directory


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def build_repo(root: Path, arquivos: dict[str, str]) -> Path:
    for caminho, conteudo in arquivos.items():
        destino = root / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")
    return root


def achados_de(root: Path) -> list[Finding]:
    return [f for res in analyze_directory(root).results for f in res.findings]


# --- a garantia central ------------------------------------------------------


def test_python_e_javascript_nao_se_confundem(tmp_path):
    """O mesmo risco, detectado por meios diferentes, sai marcado como tal."""
    build_repo(
        tmp_path,
        {
            "a.py": "eval('1 + 1')\n",
            "a.js": "eval('1 + 1');\n",
        },
    )
    por_arquivo = {f.file_path: f for f in achados_de(tmp_path) if f.rule_id == "SEC-006"}

    assert por_arquivo["a.py"].detection_method is DetectionMethod.AST
    assert por_arquivo["a.js"].detection_method is DetectionMethod.TEXT


def test_deteccao_textual_nunca_se_apresenta_como_ast(tmp_path):
    """A trava: nenhum achado de JS/TS pode sair marcado como árvore sintática,
    porque não existe parser de JS no motor."""
    build_repo(
        tmp_path,
        {
            "a.js": "eval('x');\nvar y = 1;\ndocument.write(z);\nconsole.log(1);\n",
            "b.ts": "let v: any = 1;\ndebugger;\n",
        },
    )
    de_js = [f for f in achados_de(tmp_path) if (f.file_path or "").endswith((".js", ".ts"))]

    assert de_js
    assert all(f.detection_method is not DetectionMethod.AST for f in de_js)


def test_credencial_e_deteccao_textual(tmp_path):
    """O detector de credenciais é regex sobre texto, inclusive em arquivo
    Python — o método é do detector, não da linguagem do arquivo."""
    build_repo(tmp_path, {"conf.py": 'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n'})
    achados = [f for f in achados_de(tmp_path) if f.rule_id.startswith("SEC-00")]

    assert achados
    assert all(f.detection_method is DetectionMethod.TEXT for f in achados)


def test_achado_por_ausencia_de_arquivo_e_metadado(tmp_path):
    """Não ter README é fato do repositório, não do código."""
    build_repo(tmp_path, {"a.py": "x = 1\n"})
    docs = [f for f in achados_de(tmp_path) if f.rule_id.startswith("DOC-")]

    assert docs
    assert all(f.detection_method is DetectionMethod.METADATA for f in docs)


# --- serialização ------------------------------------------------------------


def test_o_metodo_sobrevive_ao_formato_legado(tmp_path):
    build_repo(tmp_path, {"a.py": "eval('1')\n"})
    achado = next(f for f in achados_de(tmp_path) if f.rule_id == "SEC-006")

    bruto = achado.to_legacy_dict()
    assert bruto["detection_method"] == "ast"
    assert Finding.from_legacy_dict(bruto).detection_method is DetectionMethod.AST


def test_analise_antiga_nao_ganha_procedencia_inventada():
    """Análise gravada antes deste campo não registrava o método. Afirmar "AST"
    sobre um achado de origem desconhecida seria inventar procedência."""
    antigo = {
        "title": "Achado antigo",
        "description": "de uma análise anterior",
        "severity": "medium",
        "file_path": "a.py",
        "line": 1,
    }
    assert Finding.from_legacy_dict(antigo).detection_method is DetectionMethod.METADATA


# --- a regra que afirmava cobertura ------------------------------------------


def test_a_regra_de_proporcao_nao_afirma_cobertura(tmp_path):
    """TST-002 conta arquivos. Poucos arquivos de teste podem exercitar muita
    coisa, e muitos podem exercitar pouca — o motor não executa a suíte e não
    tem como saber."""
    from app.engine.rules.testing_rules import TESTING_RULES

    regra = next(r for r in TESTING_RULES if r.rule_id == "TST-002")
    texto = f"{regra.description} {regra.recommendation}".lower()

    assert "não é uma medida de cobertura" in texto or "não uma medida de cobertura" in texto
    assert "arquivo" in texto


def test_nenhuma_regra_afirma_cobertura_medida():
    """Trava geral: nenhuma regra pode afirmar cobertura como fato observado.

    TST-005 fala de cobertura para dizer que ela **não** foi medida e
    recomendar medi-la, o que é o oposto de alegá-la.
    """
    from app.engine.rules import testing_rules

    for regra in testing_rules.TESTING_RULES:
        texto = regra.description.lower()
        if "cobertura" not in texto:
            continue
        assert any(
            marcador in texto
            for marcador in (
                "não é uma medida",
                "não uma medida",
                "sem medir",
                "nenhuma configuração",
            )
        ), f"{regra.rule_id} menciona cobertura sem qualificar que ela não foi medida"
