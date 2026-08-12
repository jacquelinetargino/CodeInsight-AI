import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analysis import Analysis, AnalysisResult
from app.models.enums import AnalysisStatus
from app.models.repository import Repository
from app.models.user import User


class AnalysisRepository:
    """Acesso a dados de `Analysis`."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, *, repository_id: uuid.UUID) -> Analysis:
        analysis = Analysis(repository_id=repository_id, status=AnalysisStatus.QUEUED)
        self.db.add(analysis)
        await self.db.flush()
        return analysis

    async def get_by_id(self, analysis_id: uuid.UUID) -> Analysis | None:
        return await self.db.get(Analysis, analysis_id)

    async def get_owned_detail(self, analysis_id: uuid.UUID, user_id: uuid.UUID) -> Analysis | None:
        """Carrega a análise com todos os relacionamentos usados na tela de detalhe,
        já validando que ela pertence a um repositório do usuário."""
        result = await self.db.execute(
            select(Analysis)
            .where(Analysis.id == analysis_id)
            .options(
                selectinload(Analysis.results),
                selectinload(Analysis.suggestions),
                selectinload(Analysis.fix_suggestions),
                selectinload(Analysis.readme),
                selectinload(Analysis.repository)
                .selectinload(Repository.user)
                .selectinload(User.github_credential),
            )
        )
        analysis = result.scalar_one_or_none()
        if analysis is None or analysis.repository.user_id != user_id:
            return None
        return analysis

    async def list_by_repository(self, repository_id: uuid.UUID) -> list[Analysis]:
        result = await self.db.execute(
            select(Analysis)
            .where(Analysis.repository_id == repository_id)
            .order_by(Analysis.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_recent_by_user(self, user_id: uuid.UUID, limit: int = 10) -> list[Analysis]:
        result = await self.db.execute(
            select(Analysis)
            .join(Repository, Analysis.repository_id == Repository.id)
            .where(Repository.user_id == user_id)
            .options(selectinload(Analysis.repository))
            .order_by(Analysis.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_user(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(Analysis)
            .join(Repository, Analysis.repository_id == Repository.id)
            .where(Repository.user_id == user_id)
        )
        return result.scalar_one()

    async def average_score_by_user(self, user_id: uuid.UUID) -> float | None:
        result = await self.db.execute(
            select(func.avg(Analysis.overall_score))
            .join(Repository, Analysis.repository_id == Repository.id)
            .where(Repository.user_id == user_id, Analysis.status == AnalysisStatus.DONE)
        )
        avg = result.scalar_one()
        return round(avg, 1) if avg is not None else None

    async def count_findings_by_user(self, user_id: uuid.UUID) -> int:
        """Soma o número de achados (findings) em todas as análises do usuário."""
        result = await self.db.execute(
            select(func.coalesce(func.sum(func.jsonb_array_length(AnalysisResult.findings)), 0))
            .join(Analysis, AnalysisResult.analysis_id == Analysis.id)
            .join(Repository, Analysis.repository_id == Repository.id)
            .where(Repository.user_id == user_id)
        )
        return result.scalar_one()
