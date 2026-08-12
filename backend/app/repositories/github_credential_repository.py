import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.github_credential import GithubCredential


class GithubCredentialRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_user_id(self, user_id: uuid.UUID) -> GithubCredential | None:
        result = await self.db.execute(
            select(GithubCredential).where(GithubCredential.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(self, *, user_id: uuid.UUID, token_encrypted: str) -> GithubCredential:
        credential = await self.get_by_user_id(user_id)
        if credential is None:
            credential = GithubCredential(user_id=user_id, token_encrypted=token_encrypted)
            self.db.add(credential)
        else:
            credential.token_encrypted = token_encrypted
        await self.db.flush()
        return credential

    async def delete(self, user_id: uuid.UUID) -> None:
        credential = await self.get_by_user_id(user_id)
        if credential is not None:
            await self.db.delete(credential)
