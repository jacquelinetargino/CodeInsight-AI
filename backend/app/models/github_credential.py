import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    # Só para o verificador de tipos: em execução o SQLAlchemy resolve
    # os nomes ao configurar os mappers, e importar de verdade aqui
    # criaria ciclo entre os módulos de modelo.
    from app.models.user import User


class GithubCredential(Base):
    """Personal Access Token do GitHub, opcional, associado a um usuário.

    Não existe fluxo OAuth: o usuário cola um PAT próprio (criado em
    https://github.com/settings/tokens) para acessar repositórios privados e
    evitar o rate limit de requisições não autenticadas. Sem essa credencial,
    repositórios públicos ainda podem ser analisados normalmente.
    """

    __tablename__ = "github_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # Sempre criptografado (Fernet) — nunca armazenado em texto puro.
    token_encrypted: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="github_credential")
