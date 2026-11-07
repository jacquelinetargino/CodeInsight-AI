import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class OAuthIdentity(Base):
    """Uma conta externa (Google, GitHub) vinculada a um usuário.

    A chave é `(provider, provider_user_id)` — o `sub` do Google ou o id
    numérico do GitHub —, nunca o e-mail: e-mail muda e pode ser reatribuído,
    o id do provedor não. O e-mail guardado é só informativo (mostrar na tela
    qual conta está ligada).

    Nenhum token do provedor é armazenado: o access token serve apenas para
    descobrir quem é a pessoa durante o login e é descartado em seguida. Em
    particular, o login com GitHub NÃO substitui o PAT usado para analisar
    repositórios (`GithubCredential`).
    """

    __tablename__ = "oauth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_identity_provider_subject"),
        # Uma conta de cada provedor por usuário: deixa "desvincular o Google"
        # sem ambiguidade.
        UniqueConstraint("user_id", "provider", name="uq_oauth_identity_user_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="oauth_identities")
