import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oauth_identity import OAuthIdentity


class OAuthIdentityRepository:
    """Acesso a dados de `OAuthIdentity`. Só queries."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_subject(self, provider: str, provider_user_id: str) -> OAuthIdentity | None:
        result = await self.db.execute(
            select(OAuthIdentity).where(
                OAuthIdentity.provider == provider,
                OAuthIdentity.provider_user_id == provider_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_user(self, user_id: uuid.UUID, provider: str) -> OAuthIdentity | None:
        result = await self.db.execute(
            select(OAuthIdentity).where(
                OAuthIdentity.user_id == user_id, OAuthIdentity.provider == provider
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[OAuthIdentity]:
        result = await self.db.execute(
            select(OAuthIdentity)
            .where(OAuthIdentity.user_id == user_id)
            .order_by(OAuthIdentity.provider)
        )
        return list(result.scalars().all())

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        provider: str,
        provider_user_id: str,
        email: str | None,
        email_verified: bool,
    ) -> OAuthIdentity:
        identity = OAuthIdentity(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
            email_verified=email_verified,
        )
        self.db.add(identity)
        await self.db.flush()
        return identity

    async def delete(self, identity: OAuthIdentity) -> None:
        await self.db.delete(identity)
        await self.db.flush()
