import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    # Só para o verificador de tipos: em execução o SQLAlchemy resolve
    # os nomes ao configurar os mappers, e importar de verdade aqui
    # criaria ciclo entre os módulos de modelo.
    from app.models.analysis import Analysis


class FixSuggestion(Base):
    """Resultado de uma correção solicitada sob demanda para um achado específico.

    Diferente de `Suggestion` (lote de melhorias priorizadas gerado automaticamente
    ao final da análise), este registro é criado quando o usuário pede explicitamente
    a correção de UM achado. Nunca é aplicado de volta no repositório — é apenas
    exibido para o usuário decidir o que fazer.
    """

    __tablename__ = "fix_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str | None] = mapped_column(String(1024))
    line: Mapped[int | None] = mapped_column(Integer)
    current_code: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_code: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped["Analysis"] = relationship(back_populates="fix_suggestions")
