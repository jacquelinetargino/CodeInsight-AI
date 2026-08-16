"""dimensões do CodeInsight Engine: 6 para 8

Alinha o enum `analysis_dimension` com `app.engine.findings.FindingCategory`:

- acrescenta `dependencies` e `configuration`, cobertos pelos analyzers dos
  PRs 08 e 12;
- renomeia `tests` para `testing`, que é o nome usado pelo motor. É um rename de
  rótulo do tipo: as linhas existentes continuam válidas e passam a ler o valor
  novo, sem UPDATE, sem recriação de tipo e sem tabela intermediária.

Nada é removido. Nenhuma linha é reescrita, movida ou apagada.

Sobre o downgrade: PostgreSQL não oferece remoção de valor de enum, então o
downgrade desfaz o rename (a parte reversível) e mantém os dois valores novos.
Removê-los exigiria recriar o tipo e reescrever a coluna — destrutivo, e por
isso não é feito automaticamente.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-15 00:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_NOVOS_VALORES = ("dependencies", "configuration")


def upgrade() -> None:
    # IF NOT EXISTS torna a migration idempotente: reexecutá-la depois de uma
    # falha parcial não estoura em "enum label already exists".
    for valor in _NOVOS_VALORES:
        op.execute(f"ALTER TYPE analysis_dimension ADD VALUE IF NOT EXISTS '{valor}'")

    # Só renomeia se ainda existir o rótulo antigo — a migration precisa ser
    # segura em banco novo (criado já com 'testing') e em banco existente.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'analysis_dimension' AND e.enumlabel = 'tests'
            ) THEN
                ALTER TYPE analysis_dimension RENAME VALUE 'tests' TO 'testing';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'analysis_dimension' AND e.enumlabel = 'testing'
            ) THEN
                ALTER TYPE analysis_dimension RENAME VALUE 'testing' TO 'tests';
            END IF;
        END $$;
        """
    )
