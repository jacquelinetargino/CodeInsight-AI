"""Analyzer de qualidade de código.

Duas coisas são verificadas aqui: que as ocorrências de manutenibilidade viram
achados (antes eram detectadas e descartadas) e que segurança e qualidade não se
misturam — cada achado sai pela dimensão a que pertence.
"""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.engine.analyzers.quality import QualityAnalyzer
from app.engine.analyzers.security import SecurityAnalyzer
from app.engine.findings import FindingCategory
from app.engine.rules.quality_rules import QUALITY_RULES, register_quality_rules
from app.engine.rules.registry import RuleRegistry
from app.engine.scanner import scan_repository


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


def run(root: Path):
    return QualityAnalyzer().analyze(root, scan_repository(root))


def rule_ids(resultado) -> set[str]:
    return {f.rule_id for f in resultado.findings}


# --- catálogo ---------------------------------------------------------------


def test_ids_do_catalogo_sao_unicos():
    ids = [r.rule_id for r in QUALITY_RULES]
    assert len(ids) == len(set(ids))


def test_registro_aceita_o_catalogo_inteiro():
    registry = RuleRegistry()
    register_quality_rules(registry)
    for regra in QUALITY_RULES:
        assert registry.get(regra.rule_id).category is FindingCategory.QUALITY


# --- Python -----------------------------------------------------------------


def test_argumento_padrao_mutavel(tmp_path):
    build_repo(tmp_path, {"a.py": "def f(itens=[]):\n    itens.append(1)\n    return itens\n"})
    assert "QUA-005" in rule_ids(run(tmp_path))


def test_except_sem_tipo(tmp_path):
    build_repo(tmp_path, {"a.py": "try:\n    x = 1\nexcept:\n    pass\n"})
    assert "QUA-006" in rule_ids(run(tmp_path))


def test_excecao_descartada(tmp_path):
    build_repo(tmp_path, {"a.py": "try:\n    x = 1\nexcept ValueError:\n    pass\n"})
    assert "QUA-008" in rule_ids(run(tmp_path))


def test_assert_para_validacao(tmp_path):
    build_repo(tmp_path, {"a.py": "def f(x):\n    assert x > 0\n    return x\n"})
    assert "QUA-009" in rule_ids(run(tmp_path))


def test_funcao_longa_demais(tmp_path):
    corpo = "\n".join(f"    x{i} = {i}" for i in range(80))
    build_repo(tmp_path, {"a.py": f"def grande():\n{corpo}\n"})
    assert "QUA-001" in rule_ids(run(tmp_path))


def test_argumentos_demais(tmp_path):
    build_repo(tmp_path, {"a.py": "def f(a, b, c, d, e, g, h):\n    return a\n"})
    assert "QUA-004" in rule_ids(run(tmp_path))


def test_chamada_de_rede_sem_timeout(tmp_path):
    build_repo(tmp_path, {"a.py": "import requests\n\n\ndef f():\n    return requests.get('u')\n"})
    assert "QUA-010" in rule_ids(run(tmp_path))


def test_codigo_limpo_nao_gera_achado(tmp_path):
    build_repo(
        tmp_path,
        {"a.py": "def somar(a: int, b: int) -> int:\n    return a + b\n"},
    )
    assert run(tmp_path).findings == []


def test_arquivo_com_sintaxe_invalida_vira_nota(tmp_path):
    """Arquivo ilegível não é arquivo limpo."""
    build_repo(tmp_path, {"a.py": "def f(\n"})
    resultado = run(tmp_path)
    assert resultado.findings == []
    assert resultado.notes


# --- JavaScript / TypeScript ------------------------------------------------


def test_var_console_e_debugger(tmp_path):
    build_repo(tmp_path, {"a.js": "var x = 1;\nconsole.log(x);\ndebugger;\n"})
    ids = rule_ids(run(tmp_path))
    assert {"QUA-011", "QUA-012", "QUA-013"} <= ids


def test_tipo_any(tmp_path):
    build_repo(tmp_path, {"a.ts": "let valor: any = 1;\n"})
    assert "QUA-014" in rule_ids(run(tmp_path))


def test_deteccao_textual_tem_confianca_limitada(tmp_path):
    """Sem parser não dá para distinguir código de string ou comentário."""
    build_repo(tmp_path, {"a.js": "debugger;\n"})
    achado = next(f for f in run(tmp_path).findings if f.rule_id == "QUA-013")
    assert achado.confidence <= 0.7


# --- separação entre as dimensões -------------------------------------------


def test_qualidade_e_seguranca_nao_se_misturam(tmp_path):
    """O mesmo arquivo alimenta os dois analyzers; cada achado sai pela
    dimensão a que pertence."""
    build_repo(
        tmp_path,
        {"a.py": "import os\n\n\ndef f(itens=[]):\n    os.system('ls')\n    return itens\n"},
    )
    scan = scan_repository(tmp_path)

    qualidade = QualityAnalyzer().analyze(tmp_path, scan)
    seguranca = SecurityAnalyzer().analyze(tmp_path, scan)

    assert all(f.category is FindingCategory.QUALITY for f in qualidade.findings)
    assert all(f.category is FindingCategory.SECURITY for f in seguranca.findings)
    assert "QUA-005" in rule_ids(qualidade)
    assert not rule_ids(qualidade) & rule_ids(seguranca)


def test_binarios_e_outras_linguagens_sao_ignorados(tmp_path):
    build_repo(tmp_path, {"leia.md": "# Documento\n\nvar x = 1;\n"})
    assert run(tmp_path).findings == []


# --- dogfooding -------------------------------------------------------------


def test_o_proprio_backend_nao_tem_achado_critico_de_qualidade():
    """O motor rodando sobre o código deste repositório.

    A afirmação é modesta de propósito: qualidade acumula, e travar o CI numa
    contagem exata transformaria cada refatoração numa negociação com o teste.
    O que não pode acontecer é uma regra de qualidade sair como severidade alta.
    """
    raiz = Path(__file__).resolve().parent.parent / "app"
    resultado = run(raiz)

    assert resultado.files_analyzed > 0
    assert all(f.severity.value in {"low", "medium"} for f in resultado.findings)


# --- calibragem: código de teste não é código de produção --------------------


def test_assert_em_arquivo_de_teste_nao_e_achado(tmp_path):
    """`assert` é como se escreve um teste em pytest.

    Medido em psf/requests: sem esta distinção, 579 dos 753 achados de qualidade
    eram asserts corretos dentro da suíte de testes.
    """
    build_repo(tmp_path, {"tests/test_algo.py": "def test_x():\n    assert 1 == 1\n"})
    assert "QUA-009" not in rule_ids(run(tmp_path))


def test_assert_fora_de_teste_continua_sendo_achado(tmp_path):
    build_repo(tmp_path, {"app/servico.py": "def f(x):\n    assert x > 0\n    return x\n"})
    assert "QUA-009" in rule_ids(run(tmp_path))


def test_rede_sem_timeout_em_teste_nao_e_achado(tmp_path):
    build_repo(
        tmp_path,
        {"tests/test_http.py": "import requests\n\n\ndef test_x():\n    requests.get('u')\n"},
    )
    assert "QUA-010" not in rule_ids(run(tmp_path))


def test_funcao_longa_em_teste_continua_sendo_achado(tmp_path):
    """A isenção vale só para o que é convenção correta em teste. Uma função de
    500 linhas continua difícil de manter, esteja onde estiver."""
    corpo = "\n".join(f"    x{i} = {i}" for i in range(80))
    build_repo(tmp_path, {"tests/test_grande.py": f"def test_enorme():\n{corpo}\n"})
    assert "QUA-001" in rule_ids(run(tmp_path))
