import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Analysis
from app.models.repository import Repository
from app.models.suggestion import Suggestion


class SuggestionRepository:
    """Acesso a dados de `Suggestion` (sugestões priorizadas em lote)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(self, suggestion: Suggestion) -> None:
        self.db.add(suggestion)

    async def count_by_user(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(Suggestion)
            .join(Analysis, Suggestion.analysis_id == Analysis.id)
            .join(Repository, Analysis.repository_id == Repository.id)
            .where(Repository.user_id == user_id)
        )
        return result.scalar_one()
