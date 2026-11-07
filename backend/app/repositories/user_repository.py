import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Acesso a dados de `User`. Nenhuma regra de negócio aqui — só queries."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def email_taken(self, email: str) -> bool:
        """Se algum usuário já usa este e-mail, sem diferenciar maiúsculas.

        `first()` e não `scalar_one_or_none()`: contas antigas podem ter o mesmo
        endereço com caixas diferentes, e isso não pode virar exceção aqui."""
        result = await self.db.execute(
            select(User.id).where(func.lower(User.email) == email.strip().lower()).limit(1)
        )
        return result.first() is not None

    async def create(self, *, email: str, hashed_password: str | None, username: str) -> User:
        user = User(email=email, hashed_password=hashed_password, username=username)
        self.db.add(user)
        await self.db.flush()
        return user
