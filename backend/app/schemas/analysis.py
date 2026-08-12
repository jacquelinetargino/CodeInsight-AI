import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import AnalysisStatus, Dimension, Severity


class Finding(BaseModel):
    title: str
    description: str
    suggestion: str | None = None
    severity: Severity = Severity.MEDIUM
    file_path: str | None = None
    line: int | None = None


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
