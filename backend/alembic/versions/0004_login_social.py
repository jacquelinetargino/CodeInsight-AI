"""login social: identidades OAuth e senha opcional

Duas mudanças, ambas aditivas — nenhuma linha existente é alterada:

1. Tabela `oauth_identities`, uma linha por conta externa (Google, GitHub)
   vinculada a um usuário, identificada pelo id estável do provedor.
2. `users.hashed_password` passa a aceitar NULL. Quem cria a conta pelo login
   social não tem senha; inventar um hash aleatório esconderia esse fato do
   próprio sistema (não daria para impedir que a pessoa desvincule o único
   meio de entrar). Todas as contas atuais têm senha e continuam com ela.

O downgrade é reversível com uma ressalva inevitável: contas sem senha não
cabem no NOT NULL antigo. Em vez de falhar no meio do downgrade, elas recebem
o hash bcrypt de um segredo aleatório que ninguém conhece — continuam
existindo e podem definir senha pelo "esqueci a senha".

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-07 00:00:00
"""

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_identities",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("email_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "provider", "provider_user_id", name="uq_oauth_identity_provider_subject"
        ),
        sa.UniqueConstraint("user_id", "provider", name="uq_oauth_identity_user_provider"),
    )
    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    # Import local: só o downgrade precisa de bcrypt, e só se houver conta sem senha.
    from passlib.context import CryptContext

    conn = op.get_bind()
    sem_senha = conn.execute(
        sa.text("SELECT count(*) FROM users WHERE hashed_password IS NULL")
    ).scalar()
    if sem_senha:
        inutilizavel = CryptContext(schemes=["bcrypt"]).hash(secrets.token_urlsafe(32))
        conn.execute(
            sa.text("UPDATE users SET hashed_password = :h WHERE hashed_password IS NULL"),
            {"h": inutilizavel},
        )
    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=False)
    op.drop_table("oauth_identities")
