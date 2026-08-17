"""Converte achados em score e nível de risco.

Determinístico: as mesmas entradas produzem sempre a mesma saída, sem chamada de
IA e sem estado externo. É o que torna o score comparável entre duas execuções e
entre dois repositórios.

Três decisões sustentam o cálculo:

**Severidade domina quantidade.** Um segredo versionado é pior que cinquenta
avisos de estilo. Cada severidade tem um peso base e a contagem entra pela raiz
quadrada, com retorno decrescente — o décimo aviso de estilo diz muito menos
sobre o repositório que o primeiro.

**Não avaliado nunca vira nota cheia.** Uma dimensão sem analyzer que a cubra
recebe `None`, não 100. Tratar ausência de informação como ausência de problema
é a forma mais fácil de um relatório mentir.

**O score geral não apaga um achado crítico.** Um repositório excelente com uma
chave privada versionada continua sendo um repositório com uma chave privada
versionada, então a presença de crítico estabelece um piso para o risco.
"""

import math
from enum import Enum

from pydantic import BaseModel, Field

from app.engine.analyzers.base import AnalyzerResult
from app.engine.findings import Finding, FindingCategory
from app.models.enums import Severity

MAX_SCORE = 100

# Tamanho de repositório em que os pesos de severidade foram calibrados. Serve de
# piso do denominador da densidade: até aqui a penalidade é por contagem
# absoluta, e acima disso passa a ser por proporção. Ver `_penalty`.
_BASELINE_FILES = 100


class RiskLevel(str, Enum):
    """Risco agregado do repositório."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Peso base de cada severidade, em pontos descontados do máximo. A distância
# entre crítico e baixo é intencionalmente grande: são problemas de naturezas
# diferentes, não graus do mesmo problema.
SEVERITY_PENALTY: dict[Severity, float] = {
    Severity.CRITICAL: 40.0,
    Severity.HIGH: 15.0,
    Severity.MEDIUM: 5.0,
    Severity.LOW: 1.5,
}

# Quanto cada dimensão pesa no score geral. Segurança pesa mais porque é a única
# cujo pior caso é irreversível: código feio se refatora, credencial vazada não
# se "desvaza".
DIMENSION_WEIGHTS: dict[FindingCategory, float] = {
    FindingCategory.SECURITY: 0.22,
    FindingCategory.QUALITY: 0.16,
    FindingCategory.DEPENDENCIES: 0.14,
    FindingCategory.ARCHITECTURE: 0.12,
    FindingCategory.TESTING: 0.12,
    FindingCategory.CONFIGURATION: 0.10,
    FindingCategory.DOCUMENTATION: 0.08,
    FindingCategory.GIT: 0.06,
}

# Faixas do score geral. Os cortes são redondos de propósito: fingir precisão
# decimal numa avaliação heurística seria falsa exatidão.
_RISK_THRESHOLDS: list[tuple[float, RiskLevel]] = [
    (85.0, RiskLevel.LOW),
    (70.0, RiskLevel.MEDIUM),
    (50.0, RiskLevel.HIGH),
]


class DimensionScore(BaseModel):
    """Score de uma dimensão.

    `score is None` significa "não avaliado" e é diferente de zero: zero é um
    veredito, `None` é a ausência dele.
    """

    category: FindingCategory
    score: int | None = None
    findings_count: int = 0
    severity_counts: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    @property
    def evaluated(self) -> bool:
        return self.score is not None


class RepositoryScore(BaseModel):
    """Score agregado. Mantém as dimensões individuais porque a média esconde
    justamente o que interessa: qual eixo puxou o resultado para baixo."""

    overall: float | None = None
    risk_level: RiskLevel
    dimensions: list[DimensionScore] = Field(default_factory=list)
    total_findings: int = 0
    unevaluated: list[FindingCategory] = Field(
        default_factory=list,
        description="Dimensões sem analyzer correspondente nesta execução",
    )

    def dimension(self, category: FindingCategory) -> DimensionScore | None:
        for item in self.dimensions:
            if item.category == category:
                return item
        return None


def _penalty(findings: list[Finding], files_analyzed: int) -> float:
    """Penalidade total de um conjunto de achados.

    A contagem entra pela raiz quadrada: dez achados médios pesam pouco mais que
    três. A confiança de cada achado escala a contagem — heurística incerta não
    derruba o score como uma certeza derrubaria.

    **A penalidade é por densidade, não por contagem absoluta.** A raiz quadrada
    sozinha não bastava: medido, `numpy/numpy` acumulava 1929 achados baixos em
    2361 arquivos e saturava em zero, o mesmo veredito de um projeto de dez
    arquivos com trinta problemas graves. Repositório grande tem mais achados
    porque tem mais código, e um score que só sabe dizer "zero" para tudo acima
    de mil arquivos não informa nada.

    Abaixo de `_BASELINE_FILES` nada muda: a fórmula é idêntica à anterior, e é
    a faixa em que os limiares de severidade foram calibrados. Acima, o que pesa
    é a proporção — 0,4 achado por arquivo continua sendo 0,4 achado por arquivo,
    tenha o repositório 200 ou 20 000 arquivos.
    """
    # Denominador com piso: um repositório de cinco arquivos não deve ser punido
    # pela raridade, nem premiado por ela.
    escala = _BASELINE_FILES / max(files_analyzed, _BASELINE_FILES)

    total = 0.0
    for severidade, base in SEVERITY_PENALTY.items():
        efetivos = sum(f.confidence for f in findings if f.severity == severidade)
        if efetivos > 0:
            total += base * math.sqrt(efetivos * escala)
    return total


def score_dimension(result: AnalyzerResult) -> DimensionScore:
    """Score de 0 a 100 para uma dimensão, a partir dos achados do analyzer."""
    contagem: dict[str, int] = {}
    for achado in result.findings:
        chave = achado.severity.value
        contagem[chave] = contagem.get(chave, 0) + 1

    bruto = MAX_SCORE - _penalty(result.findings, result.files_analyzed)
    return DimensionScore(
        category=result.category,
        score=max(0, round(bruto)),
        findings_count=len(result.findings),
        severity_counts=contagem,
        notes=list(result.notes),
    )


def risk_level_for(overall: float | None, has_critical_finding: bool) -> RiskLevel:
    """Nível de risco a partir do score e da presença de achado crítico.

    Pública porque a API precisa do mesmo veredito para análises já gravadas, e
    duplicar a regra faria o relatório e a tela discordarem entre si.
    """
    if overall is None:
        # Sem nenhuma dimensão avaliada não há base para afirmar risco baixo.
        nivel = RiskLevel.MEDIUM
    else:
        nivel = RiskLevel.CRITICAL
        for corte, candidato in _RISK_THRESHOLDS:
            if overall >= corte:
                nivel = candidato
                break

    # Um crítico isolado num repositório de resto bom não deve ser diluído pela
    # média: ele estabelece um piso.
    if has_critical_finding and nivel in (RiskLevel.LOW, RiskLevel.MEDIUM):
        return RiskLevel.HIGH
    return nivel


def score_repository(results: list[AnalyzerResult]) -> RepositoryScore:
    """Agrega os analyzers num score geral e num nível de risco.

    Dimensões ausentes não entram na média nem são preenchidas com 100: os pesos
    são renormalizados sobre o que foi de fato avaliado, e o que faltou é
    listado em `unevaluated`.
    """
    dimensoes = [score_dimension(r) for r in results]
    avaliadas = [d for d in dimensoes if d.evaluated]

    peso_total = sum(DIMENSION_WEIGHTS[d.category] for d in avaliadas)
    if peso_total > 0:
        soma = sum((d.score or 0) * DIMENSION_WEIGHTS[d.category] for d in avaliadas)
        overall: float | None = round(soma / peso_total, 1)
    else:
        overall = None

    tem_critico = any(
        achado.severity == Severity.CRITICAL
        for resultado in results
        for achado in resultado.findings
    )
    risco = risk_level_for(overall, tem_critico)

    cobertas = {d.category for d in dimensoes}
    return RepositoryScore(
        overall=overall,
        risk_level=risco,
        dimensions=sorted(dimensoes, key=lambda d: d.category.value),
        total_findings=sum(d.findings_count for d in dimensoes),
        unevaluated=sorted(
            (c for c in FindingCategory if c not in cobertas), key=lambda c: c.value
        ),
    )
