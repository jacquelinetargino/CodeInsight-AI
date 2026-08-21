"""As migrations, executadas de verdade, e o schema que elas produzem.

Existem dois caminhos independentes até um banco com tabelas:

- a suíte chama `Base.metadata.create_all()`, a partir dos modelos;
- a produção roda `alembic upgrade head`, a partir das migrations.

Nada os confrontava. O efeito medido: acrescentar uma coluna a um modelo **sem
migration nenhuma** deixava passar `test_migrations.py`, os 908 testes da suíte
e o `alembic upgrade head` do CI — e a produção simplesmente não teria a coluna.

O mesmo buraco já tinha deixado passar uma divergência real: doze colunas
NULLable no banco que os modelos declaram NOT NULL, corrigidas pela migration
0003.

Tudo aqui acontece num schema descartável, criado e removido pelo próprio teste.
"""

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from app.core.database import Base
from app.models.enums import Dimension
from tests.conftest import TEST_DATABASE_URL

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"

_LABELS_SQL = """
    SELECT e.enumlabel
    FROM pg_enum e
    JOIN pg_type t ON t.oid = e.enumtypid
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typname = 'analysis_dimension' AND n.nspname = :schema
    ORDER BY e.enumsortorder
"""


def _alembic_config(connection) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    config.attributes["connection"] = connection
    return config


@pytest_asyncio.fixture
async def migration_schema():
    """Schema efêmero e exclusivo deste teste.

    O nome é aleatório para nunca colidir com um schema existente, e a checagem
    de `current_schema()` garante que o DDL das migrations caia aqui dentro — se
    o search_path não pegasse, o teste derrubaria tabelas de outro schema.
    """
    schema = f"migr_check_{uuid.uuid4().hex[:12]}"
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"server_settings": {"search_path": schema}},
    )

    admin = create_async_engine(TEST_DATABASE_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    async with engine.begin() as conn:
        efetivo = (await conn.execute(text("SELECT current_schema()"))).scalar()
        if efetivo != schema:
            raise RuntimeError(
                f"Schema efetivo é {efetivo!r}, esperado {schema!r}. Abortando antes "
                "de rodar qualquer migration para não afetar o schema errado."
            )

    try:
        yield engine, schema
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            # CASCADE só alcança objetos criados dentro deste schema efêmero.
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


def _diferencas_de_schema(sync_conn) -> list:
    """O que o autogenerate do Alembic escreveria numa migration nova.

    Vazio significa que o banco migrado e os modelos declaram a mesma coisa.
    `compare_type=True` inclui os tipos das colunas, não só a existência delas.
    """
    contexto = MigrationContext.configure(sync_conn, opts={"compare_type": True})
    return compare_metadata(contexto, Base.metadata)


@pytest.mark.asyncio
async def test_o_schema_das_migrations_e_o_dos_modelos(migration_schema):
    """A garantia central deste arquivo.

    Sem ela, os dois caminhos até o schema podem divergir indefinidamente sem
    que nada acuse: a suíte valida um banco que a produção não tem.

    Se este teste falhar depois de mexer num modelo, a correção é uma migration
    nova — nunca editar uma que já rodou.
    """
    engine, _ = migration_schema

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: command.upgrade(_alembic_config(sync), "head"))

    async with engine.connect() as conn:
        diferencas = await conn.run_sync(_diferencas_de_schema)

    assert diferencas == [], (
        "o banco produzido pelas migrations não é o que os modelos declaram. "
        "Cada item abaixo é uma alteração que faltou virar migration:\n  "
        + "\n  ".join(str(d) for d in diferencas)
    )


@pytest.mark.asyncio
async def test_0003_completa_linha_com_nulo_em_vez_de_falhar(migration_schema):
    """O UPDATE antes de cada `SET NOT NULL` não é decorativo.

    Nenhuma linha *deveria* estar com NULL — as doze colunas têm `server_default`
    desde a 0001 — mas "não deveria" não é garantia, e uma migration que quebra
    no meio de um deploy por causa de uma linha é pior do que o problema que
    conserta. Aqui a linha com NULL é criada de propósito.
    """
    engine, _ = migration_schema
    uid = uuid.uuid4()

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: command.upgrade(_alembic_config(sync), "0002"))
        # `server_default` não impede NULL explícito: ele só age quando a coluna
        # é omitida no INSERT.
        await conn.execute(
            text(
                """
                INSERT INTO users (id, email, hashed_password, username, created_at)
                VALUES (:uid, 'nulo@exemplo.test', 'x', 'nulo', NULL)
                """
            ),
            {"uid": uid},
        )
        assert (
            await conn.execute(text("SELECT created_at FROM users WHERE id = :uid"), {"uid": uid})
        ).scalar() is None

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: command.upgrade(_alembic_config(sync), "0003"))
        preenchido = (
            await conn.execute(text("SELECT created_at FROM users WHERE id = :uid"), {"uid": uid})
        ).scalar()

    assert preenchido is not None, "a migration passou por cima da linha em vez de completá-la"


@pytest.mark.asyncio
async def test_downgrade_da_0003_volta_a_aceitar_nulo(migration_schema):
    """A 0003 é reversível de verdade, diferente da 0002 — nada nela é
    destrutivo, então o downgrade devolve exatamente o estado anterior."""
    engine, schema = migration_schema

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: command.upgrade(_alembic_config(sync), "head"))
        await conn.run_sync(lambda sync: command.downgrade(_alembic_config(sync), "0002"))
        nulavel = (
            await conn.execute(
                text(
                    """
                    SELECT is_nullable FROM information_schema.columns
                    WHERE table_schema = :schema
                      AND table_name = 'users' AND column_name = 'created_at'
                    """
                ),
                {"schema": schema},
            )
        ).scalar()

    assert nulavel == "YES"


@pytest.mark.asyncio
async def test_migrations_produzem_o_enum_do_modelo(migration_schema):
    """A cadeia completa de migrations precisa chegar ao mesmo conjunto de
    dimensões que o modelo declara."""
    engine, schema = migration_schema

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: command.upgrade(_alembic_config(sync), "head"))
        labels = (await conn.execute(text(_LABELS_SQL), {"schema": schema})).scalars().all()

    assert set(labels) == {d.value for d in Dimension}


@pytest.mark.asyncio
async def test_migration_0002_renomeia_sem_perder_linha(migration_schema):
    """O rename de `tests` para `testing` não pode apagar nem reescrever dados.

    Uma linha é gravada com o valor antigo em 0001 e precisa continuar lá,
    íntegra, com o rótulo novo depois de 0002.
    """
    engine, schema = migration_schema

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: command.upgrade(_alembic_config(sync), "0001"))
        labels = (await conn.execute(text(_LABELS_SQL), {"schema": schema})).scalars().all()
        assert "tests" in labels
        assert "testing" not in labels

        uid, rid, aid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        await conn.execute(
            text(
                """
                INSERT INTO users (id, email, hashed_password, username)
                VALUES (:uid, 'migracao@exemplo.test', 'x', 'migracao')
                """
            ),
            {"uid": uid},
        )
        await conn.execute(
            text(
                """
                INSERT INTO repositories (id, user_id, github_repo_id, full_name)
                VALUES (:rid, :uid, 1, 'dono/repo')
                """
            ),
            {"rid": rid, "uid": uid},
        )
        await conn.execute(
            text(
                """
                INSERT INTO analyses (id, repository_id, status)
                VALUES (:aid, :rid, 'done')
                """
            ),
            {"aid": aid, "rid": rid},
        )
        await conn.execute(
            text(
                """
                INSERT INTO analysis_results (id, analysis_id, dimension, score, summary, findings)
                VALUES (:res, :aid, 'tests', 42, 'resumo preservado', '[]'::jsonb)
                """
            ),
            {"res": uuid.uuid4(), "aid": aid},
        )

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: command.upgrade(_alembic_config(sync), "0002"))

        linhas = (
            await conn.execute(text("SELECT dimension::text, score, summary FROM analysis_results"))
        ).all()

    assert linhas == [("testing", 42, "resumo preservado")]


@pytest.mark.asyncio
async def test_downgrade_0002_restaura_o_rotulo_antigo(migration_schema):
    """O rename é reversível — a parte do downgrade que dá para garantir."""
    engine, schema = migration_schema

    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: command.upgrade(_alembic_config(sync), "head"))
        await conn.run_sync(lambda sync: command.downgrade(_alembic_config(sync), "0001"))
        labels = (await conn.execute(text(_LABELS_SQL), {"schema": schema})).scalars().all()

    assert "tests" in labels
    assert "testing" not in labels
    # Os valores acrescentados permanecem: o PostgreSQL não remove rótulo de enum
    # e recriar o tipo seria destrutivo. O docstring da migration explica.
    assert {"dependencies", "configuration"} <= set(labels)
