import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import AnalysisStatus


class DashboardHistoryItem(BaseModel):
    analysis_id: uuid.UUID
    repository_full_name: str
    status: AnalysisStatus
    overall_score: float | None
    created_at: datetime


class DashboardSummary(BaseModel):
    repositories_analyzed: int
    total_analyses: int
    average_score: float | None
    total_findings: int
    total_suggestions: int
    recent_history: list[DashboardHistoryItem]
