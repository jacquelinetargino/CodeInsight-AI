"""nullability: alinhar o banco ao que os modelos declaram

Doze colunas eram criadas como NULLable pela 0001 enquanto o modelo as declara
NOT NULL. A causa é a mesma nas doze, e não é descuido de digitação: as duas
declarações inferem coisas diferentes a partir da mesma intenção.

    # migration — sem `nullable=`, o SQLAlchemy assume True
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now())

    # modelo — `Mapped[datetime]` (e não `datetime | None`) infere nullable=False
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

O efeito era um schema de teste mais estrito que o de produção: a suíte cria as
tabelas do `Base.metadata` e ganha NOT NULL; a produção roda as migrations e não
ganha. Uma restrição que o código assume não existia onde importa.

Nenhuma linha deveria estar com NULL nessas colunas — todas as doze têm
`server_default` desde a 0001, e a aplicação sempre envia valor. O UPDATE antes
de cada `SET NOT NULL` está aqui porque "não deveria" não é garantia: se houver
uma linha, a migration precisa completá-la em vez de falhar no meio de um
deploy. Os valores usados são os mesmos `server_default` já declarados — não
inventam dado, só materializam o que o banco poria ali.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# (tabela, coluna, tipo, valor de preenchimento igual ao server_default da 0001)
_COLUNAS: list[tuple[str, str, sa.types.TypeEngine, str]] = [
    ("users", "created_at", sa.DateTime(timezone=True), "now()"),
    ("github_credentials", "created_at", sa.DateTime(timezone=True), "now()"),
    ("repositories", "default_branch", sa.String(255), "'main'"),
    ("repositories", "private", sa.Boolean(), "false"),
    ("repositories", "created_at", sa.DateTime(timezone=True), "now()"),
    ("analyses", "created_at", sa.DateTime(timezone=True), "now()"),
    ("analysis_results", "summary", sa.Text(), "''"),
    ("analysis_results", "findings", pg.JSONB(), "'[]'::jsonb"),
    (
        "suggestions",
        "severity",
        pg.ENUM("low", "medium", "high", "critical", name="suggestion_severity", create_type=False),
        "'medium'",
    ),
    ("suggestions", "created_at", sa.DateTime(timezone=True), "now()"),
    ("fix_suggestions", "created_at", sa.DateTime(timezone=True), "now()"),
    ("generated_readmes", "created_at", sa.DateTime(timezone=True), "now()"),
]


def upgrade() -> None:
    for tabela, coluna, tipo, preenchimento in _COLUNAS:
        op.execute(
            f'UPDATE {tabela} SET "{coluna}" = {preenchimento} WHERE "{coluna}" IS NULL'  # noqa: S608
        )
        op.alter_column(tabela, coluna, existing_type=tipo, nullable=False)


def downgrade() -> None:
    for tabela, coluna, tipo, _ in _COLUNAS:
        op.alter_column(tabela, coluna, existing_type=tipo, nullable=True)
