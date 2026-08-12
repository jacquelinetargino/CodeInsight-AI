import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository import Repository


class RepoRepository:
    """Acesso a dados de `Repository` (o repositório do GitHub sendo rastreado)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, repository_id: uuid.UUID) -> Repository | None:
        return await self.db.get(Repository, repository_id)

    async def get_owned(self, repository_id: uuid.UUID, user_id: uuid.UUID) -> Repository | None:
        repo = await self.get_by_id(repository_id)
        return repo if repo is not None and repo.user_id == user_id else None

    async def get_by_full_name(self, user_id: uuid.UUID, full_name: str) -> Repository | None:
        result = await self.db.execute(
            select(Repository).where(Repository.user_id == user_id, Repository.full_name == full_name)
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[Repository]:
        result = await self.db.execute(
            select(Repository).where(Repository.user_id == user_id).order_by(Repository.created_at.desc())
        )
        return list(result.scalars().all())

    async def count_by_user(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(Repository).where(Repository.user_id == user_id)
        )
        return result.scalar_one()

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        github_repo_id: int,
        full_name: str,
        description: str | None,
        default_branch: str,
        private: bool,
    ) -> Repository:
        repo = Repository(
            user_id=user_id,
            github_repo_id=github_repo_id,
            full_name=full_name,
            description=description,
            default_branch=default_branch,
            private=private,
        )
        self.db.add(repo)
        await self.db.flush()
        return repo
