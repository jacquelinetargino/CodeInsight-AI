import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engine.scoring import RiskLevel, risk_level_for
from app.models.enums import AnalysisStatus, Dimension, Severity


class Finding(BaseModel):
    """Um achado, como o frontend o recebe.

    Os campos abaixo da linha são os que o motor acrescentou. Todos são
    opcionais porque análises gravadas antes do motor só têm os seis primeiros —
    exigi-los quebraria a leitura do histórico.
    """

    title: str
    description: str
    suggestion: str | None = None
    severity: Severity = Severity.MEDIUM
    file_path: str | None = None
    line: int | None = None

    # --- acrescentados pelo motor ---
    rule_id: str | None = None
    category: str | None = None
    line_end: int | None = None
    evidence: str | None = Field(
        default=None, description="Trecho curto que sustenta o achado; segredos já vêm mascarados"
    )
    confidence: float | None = Field(
        default=None,
        description="0 a 1. Existe porque boa parte da análise é heurística: "
        "afirmar certeza sobre o que foi inferido seria pior que declarar a dúvida",
    )
    analyzer: str | None = None


class AnalysisResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dimension: Dimension
    score: int
    summary: str
    findings: list[Finding]


class SuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    severity: Severity
    file_path: str | None
    code_fix: str | None


class FixRequest(BaseModel):
    """Referencia o achado (Finding) para o qual o usuário quer uma correção.
    O front-end reenvia os dados do achado que já tem em mãos — achados vivem
    dentro do JSONB de `AnalysisResult`, não têm um id próprio no banco."""

    title: str
    description: str
    file_path: str | None = None
    line: int | None = None


class FixSuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_path: str | None
    line: int | None
    current_code: str
    suggested_code: str
    explanation: str
    created_at: datetime


class AnalysisCreateRequest(BaseModel):
    repository_id: uuid.UUID


class AnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    status: AnalysisStatus
    overall_score: float | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None


class AnalysisDetailRead(AnalysisRead):
    results: list[AnalysisResultRead] = []
    suggestions: list[SuggestionRead] = []
    fix_suggestions: list[FixSuggestionRead] = []
    has_readme: bool = False

    risk_level: RiskLevel | None = Field(
        default=None,
        description="Derivado do score e dos achados, com a mesma regra do motor",
    )
    unevaluated_dimensions: list[Dimension] = Field(
        default_factory=list,
        description="Dimensões sem resultado nesta análise: não avaliadas, não isentas",
    )

    @model_validator(mode="after")
    def _derive_risk(self) -> "AnalysisDetailRead":
        """Calcula risco e lacunas a partir do que já veio do banco.

        Fica aqui, e não numa coluna, porque a regra é do motor: gravar o
        veredito congelaria análises antigas com um critério que pode mudar.
        `risk_level` usa a função do próprio motor para que relatório e tela
        nunca discordem.
        """
        if self.status is not AnalysisStatus.DONE:
            return self

        tem_critico = any(
            achado.severity is Severity.CRITICAL
            for resultado in self.results
            for achado in resultado.findings
        )
        self.risk_level = risk_level_for(self.overall_score, tem_critico)

        avaliadas = {resultado.dimension for resultado in self.results}
        self.unevaluated_dimensions = [d for d in Dimension if d not in avaliadas]
        return self
