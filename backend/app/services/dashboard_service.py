import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.repo_repository import RepoRepository
from app.repositories.suggestion_repository import SuggestionRepository
from app.schemas.dashboard import DashboardHistoryItem, DashboardSummary


async def build_dashboard_summary(db: AsyncSession, user_id: uuid.UUID) -> DashboardSummary:
    repo_repo = RepoRepository(db)
    analysis_repo = AnalysisRepository(db)
    suggestion_repo = SuggestionRepository(db)

    recent = await analysis_repo.list_recent_by_user(user_id, limit=10)

    return DashboardSummary(
        repositories_analyzed=await repo_repo.count_by_user(user_id),
        total_analyses=await analysis_repo.count_by_user(user_id),
        average_score=await analysis_repo.average_score_by_user(user_id),
        total_findings=await analysis_repo.count_findings_by_user(user_id),
        total_suggestions=await suggestion_repo.count_by_user(user_id),
        recent_history=[
            DashboardHistoryItem(
                analysis_id=a.id,
                repository_full_name=a.repository.full_name,
                status=a.status,
                overall_score=a.overall_score,
                created_at=a.created_at,
            )
            for a in recent
        ],
    )
