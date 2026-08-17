"""Score e nível de risco.

O que está sendo verificado não é a aritmética — é o comportamento que a
aritmética precisa produzir: severidade importa mais que volume, ausência de
informação não vira nota cheia, e um achado crítico não some na média.
"""

import pytest

from app.engine.analyzers.base import AnalyzerResult
from app.engine.findings import Finding, FindingCategory, build_finding_id
from app.engine.scoring import (
    DIMENSION_WEIGHTS,
    RiskLevel,
    score_dimension,
    score_repository,
)
from app.models.enums import Dimension, Severity


def make_finding(
    severity: Severity,
    category: FindingCategory = FindingCategory.SECURITY,
    confidence: float = 1.0,
) -> Finding:
    return Finding(
        id=build_finding_id(rule_id="X-001", file_path="a.py", line_start=1, title="Achado"),
        rule_id="X-001",
        category=category,
        severity=severity,
        title="Achado",
        description="Descrição",
        confidence=confidence,
        analyzer="teste",
    )


def result(
    category: FindingCategory,
    findings: list[Finding] | None = None,
    notes: list[str] | None = None,
) -> AnalyzerResult:
    return AnalyzerResult(
        analyzer=category.value,
        category=category,
        findings=findings or [],
        files_analyzed=10,
        notes=notes or [],
    )


# --- invariantes ------------------------------------------------------------


def test_os_dois_enums_de_dimensao_nao_podem_divergir():
    """`Dimension` (banco) e `FindingCategory` (motor) são duplicados de
    propósito, para o motor não depender da camada de persistência. Divergirem
    seria um bug silencioso: achados de uma categoria sem coluna correspondente
    simplesmente não seriam gravados."""
    assert {d.value for d in Dimension} == {c.value for c in FindingCategory}


def test_toda_dimensao_tem_peso():
    assert set(DIMENSION_WEIGHTS) == set(FindingCategory)
    assert sum(DIMENSION_WEIGHTS.values()) == pytest.approx(1.0)


# --- score por dimensão -----------------------------------------------------


def test_dimensao_sem_achados_recebe_nota_maxima():
    assert score_dimension(result(FindingCategory.SECURITY)).score == 100


def test_severidade_pesa_mais_que_quantidade():
    """Um segredo versionado é pior que uma pilha de avisos de estilo."""
    um_critico = score_dimension(
        result(FindingCategory.SECURITY, [make_finding(Severity.CRITICAL)])
    ).score
    vinte_baixos = score_dimension(
        result(FindingCategory.SECURITY, [make_finding(Severity.LOW) for _ in range(20)])
    ).score

    assert um_critico is not None and vinte_baixos is not None
    assert um_critico < vinte_baixos


def test_achados_repetidos_tem_retorno_decrescente():
    """Repositório grande não pode ser punido só por ser grande: o décimo aviso
    de estilo diz muito menos que o primeiro."""

    def nota(n: int) -> int:
        pontuacao = score_dimension(
            result(FindingCategory.QUALITY, [make_finding(Severity.MEDIUM) for _ in range(n)])
        ).score
        assert pontuacao is not None
        return pontuacao

    primeiro_salto = nota(1) - nota(2)
    salto_tardio = nota(20) - nota(21)
    assert primeiro_salto > salto_tardio


def test_confianca_baixa_desconta_menos():
    """Heurística incerta não derruba o score como uma certeza derrubaria."""
    certo = score_dimension(
        result(FindingCategory.QUALITY, [make_finding(Severity.HIGH, confidence=1.0)])
    ).score
    incerto = score_dimension(
        result(FindingCategory.QUALITY, [make_finding(Severity.HIGH, confidence=0.3)])
    ).score

    assert certo is not None and incerto is not None
    assert certo < incerto


def test_score_nunca_fica_negativo():
    achados = [make_finding(Severity.CRITICAL) for _ in range(50)]
    assert score_dimension(result(FindingCategory.SECURITY, achados)).score == 0


def test_contagem_por_severidade_e_notas_sao_preservadas():
    dimensao = score_dimension(
        result(
            FindingCategory.GIT,
            [make_finding(Severity.HIGH), make_finding(Severity.LOW), make_finding(Severity.LOW)],
            notes=["atividade não avaliada"],
        )
    )
    assert dimensao.severity_counts == {"high": 1, "low": 2}
    assert dimensao.findings_count == 3
    assert dimensao.notes == ["atividade não avaliada"]


# --- agregação --------------------------------------------------------------


def _todas_limpas() -> list[AnalyzerResult]:
    return [result(categoria) for categoria in FindingCategory]


def test_repositorio_limpo_tem_score_maximo_e_risco_baixo():
    score = score_repository(_todas_limpas())
    assert score.overall == 100.0
    assert score.risk_level is RiskLevel.LOW
    assert score.unevaluated == []


def test_dimensao_ausente_nao_vira_cem():
    """A garantia central: 'não avaliado' é diferente de 'sem problema'."""
    parcial = [r for r in _todas_limpas() if r.category is not FindingCategory.SECURITY]
    score = score_repository(parcial)

    assert score.dimension(FindingCategory.SECURITY) is None
    assert score.unevaluated == [FindingCategory.SECURITY]


def test_pesos_sao_renormalizados_sobre_o_que_foi_avaliado():
    """Com uma dimensão fora, as demais dividem 100% entre si — a ausência não
    pode arrastar a média para baixo como se fosse nota zero."""
    apenas_uma = [result(FindingCategory.DOCUMENTATION)]
    assert score_repository(apenas_uma).overall == 100.0


def test_sem_nenhuma_dimensao_avaliada_o_score_e_nulo():
    score = score_repository([])
    assert score.overall is None
    # Sem base para afirmar, o risco não pode ser "baixo".
    assert score.risk_level is not RiskLevel.LOW
    assert len(score.unevaluated) == len(FindingCategory)


def test_um_critico_isolado_nao_e_diluido_pela_media():
    """Um repositório de resto excelente com uma chave privada versionada
    continua sendo um repositório com uma chave privada versionada."""
    resultados = _todas_limpas()
    resultados[0] = result(resultados[0].category, [make_finding(Severity.CRITICAL)])

    score = score_repository(resultados)
    assert score.overall is not None and score.overall > 85  # média ainda alta
    assert score.risk_level is RiskLevel.HIGH  # mas o risco não acompanha


def test_muitos_problemas_graves_levam_a_risco_critico():
    resultados = [
        result(categoria, [make_finding(Severity.CRITICAL, categoria) for _ in range(4)])
        for categoria in FindingCategory
    ]
    score = score_repository(resultados)

    assert score.overall is not None and score.overall < 50
    assert score.risk_level is RiskLevel.CRITICAL


def test_total_de_achados_e_ordem_estavel_das_dimensoes():
    resultados = _todas_limpas()
    resultados[0] = result(resultados[0].category, [make_finding(Severity.LOW)])
    resultados[1] = result(resultados[1].category, [make_finding(Severity.LOW)])

    score = score_repository(resultados)
    assert score.total_findings == 2
    ordem = [d.category.value for d in score.dimensions]
    assert ordem == sorted(ordem)


def test_scores_sao_deterministicos():
    """Duas execuções sobre a mesma entrada precisam dar o mesmo número, ou o
    score deixa de ser comparável entre análises."""
    resultados = [
        result(FindingCategory.SECURITY, [make_finding(Severity.HIGH), make_finding(Severity.LOW)]),
        result(FindingCategory.QUALITY, [make_finding(Severity.MEDIUM, FindingCategory.QUALITY)]),
    ]
    assert score_repository(resultados) == score_repository(resultados)


# --- o score precisa ser invariante à escala ---------------------------------


def _com_arquivos(categoria, achados, files_analyzed):
    return AnalyzerResult(
        analyzer=categoria.value,
        category=categoria,
        findings=achados,
        files_analyzed=files_analyzed,
    )


def test_mesma_densidade_de_problemas_da_mesma_nota():
    """A garantia central: 0,4 achado por arquivo é 0,4 achado por arquivo,
    tenha o repositório 200 ou 20 000 arquivos.

    Sem isso, medido em numpy/numpy, 1929 achados baixos em 2361 arquivos
    saturavam em zero — o mesmo veredito de um projeto de dez arquivos com
    trinta problemas graves.
    """
    pequeno = _com_arquivos(
        FindingCategory.QUALITY,
        [make_finding(Severity.LOW, FindingCategory.QUALITY) for _ in range(80)],
        200,
    )
    grande = _com_arquivos(
        FindingCategory.QUALITY,
        [make_finding(Severity.LOW, FindingCategory.QUALITY) for _ in range(8000)],
        20_000,
    )
    assert score_dimension(pequeno).score == score_dimension(grande).score


def test_repositorio_grande_e_saudavel_nao_satura_em_zero():
    """Um projeto grande e bem cuidado tem muitos achados baixos em termos
    absolutos. Isso não pode significar nota zero."""
    achados = [make_finding(Severity.LOW, FindingCategory.QUALITY) for _ in range(1900)]
    achados += [make_finding(Severity.MEDIUM, FindingCategory.QUALITY) for _ in range(500)]

    pontuacao = score_dimension(_com_arquivos(FindingCategory.QUALITY, achados, 2361)).score
    assert pontuacao is not None
    assert pontuacao > 40


def test_densidade_maior_continua_dando_nota_menor():
    """A trava contra o excesso de tolerância: normalizar não pode virar
    indulto — o repositório com o dobro de problemas por arquivo tem de sair
    pior."""
    poucos = _com_arquivos(
        FindingCategory.QUALITY,
        [make_finding(Severity.MEDIUM, FindingCategory.QUALITY) for _ in range(100)],
        1000,
    )
    muitos = _com_arquivos(
        FindingCategory.QUALITY,
        [make_finding(Severity.MEDIUM, FindingCategory.QUALITY) for _ in range(400)],
        1000,
    )
    assert score_dimension(muitos).score < score_dimension(poucos).score


def test_abaixo_da_linha_de_base_nada_muda():
    """Repositório pequeno mantém exatamente o comportamento anterior — é a
    faixa em que os pesos de severidade foram calibrados."""
    um_critico = _com_arquivos(FindingCategory.SECURITY, [make_finding(Severity.CRITICAL)], 10)
    # 100 - 40*sqrt(1) = 60, o mesmo valor de antes da normalização.
    assert score_dimension(um_critico).score == 60


def test_repositorio_minusculo_nao_e_punido_pela_raridade():
    """Um achado num repositório de cinco arquivos não é dez vezes pior do que
    o mesmo achado num de cinquenta."""
    minusculo = _com_arquivos(FindingCategory.SECURITY, [make_finding(Severity.HIGH)], 5)
    medio = _com_arquivos(FindingCategory.SECURITY, [make_finding(Severity.HIGH)], 50)
    assert score_dimension(minusculo).score == score_dimension(medio).score
