"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # create_type=False: os tipos são criados manualmente logo abaixo (via
    # .create(checkfirst=True)). Sem isso, op.create_table() tentaria criar o
    # mesmo tipo de novo ao criar a tabela, batendo em "type already exists".
    analysis_status = pg.ENUM(
        "queued", "running", "done", "failed", name="analysis_status", create_type=False
    )
    analysis_dimension = pg.ENUM(
        "security",
        "quality",
        "architecture",
        "documentation",
        "tests",
        "git",
        name="analysis_dimension",
        create_type=False,
    )
    suggestion_severity = pg.ENUM(
        "low", "medium", "high", "critical", name="suggestion_severity", create_type=False
    )

    bind = op.get_bind()
    analysis_status.create(bind, checkfirst=True)
    analysis_dimension.create(bind, checkfirst=True)
    suggestion_severity.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "github_credentials",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("token_encrypted", sa.String(2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "repositories",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_repo_id", sa.BigInteger, nullable=False, index=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1024)),
        sa.Column("default_branch", sa.String(255), server_default="main"),
        sa.Column("private", sa.Boolean, server_default=sa.false()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "analyses",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "repository_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", analysis_status, nullable=False, server_default="queued"),
        sa.Column("overall_score", sa.Float),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "analysis_results",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dimension", analysis_dimension, nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("summary", sa.Text, server_default=""),
        # findings: lista de {title, description, suggestion, severity, file_path, line}
        sa.Column("findings", pg.JSONB, server_default="[]"),
    )

    op.create_table(
        "suggestions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("severity", suggestion_severity, server_default="medium"),
        sa.Column("file_path", sa.String(1024)),
        sa.Column("code_fix", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "fix_suggestions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(1024)),
        sa.Column("line", sa.Integer),
        sa.Column("current_code", sa.Text, nullable=False),
        sa.Column("suggested_code", sa.Text, nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "generated_readmes",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("generated_readmes")
    op.drop_table("fix_suggestions")
    op.drop_table("suggestions")
    op.drop_table("analysis_results")
    op.drop_table("analyses")
    op.drop_table("repositories")
    op.drop_table("github_credentials")
    op.drop_table("users")

    bind = op.get_bind()
    pg.ENUM(name="suggestion_severity").drop(bind, checkfirst=True)
    pg.ENUM(name="analysis_dimension").drop(bind, checkfirst=True)
    pg.ENUM(name="analysis_status").drop(bind, checkfirst=True)
