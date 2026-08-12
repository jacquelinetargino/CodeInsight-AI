import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import AnalysisStatus, Dimension


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(
            AnalysisStatus,
            name="analysis_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=AnalysisStatus.QUEUED,
        nullable=False,
    )
    overall_score: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    repository: Mapped["Repository"] = relationship(back_populates="analyses")  # noqa: F821
    results: Mapped[list["AnalysisResult"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )
    suggestions: Mapped[list["Suggestion"]] = relationship(  # noqa: F821
        back_populates="analysis", cascade="all, delete-orphan"
    )
    fix_suggestions: Mapped[list["FixSuggestion"]] = relationship(  # noqa: F821
        back_populates="analysis", cascade="all, delete-orphan"
    )
    readme: Mapped["GeneratedReadme | None"] = relationship(  # noqa: F821
        back_populates="analysis", uselist=False, cascade="all, delete-orphan"
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[Dimension] = mapped_column(
        Enum(
            Dimension, name="analysis_dimension", values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    findings: Mapped[list[dict]] = mapped_column(JSONB, default=list)

    analysis: Mapped["Analysis"] = relationship(back_populates="results")
