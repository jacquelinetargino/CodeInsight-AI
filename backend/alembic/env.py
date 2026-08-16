import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Garante que todos os models estejam registrados no Base.metadata.
from app.core.config import get_settings
from app.core.database import Base
from app.models import *  # noqa: F401,F403

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # Conexão injetada por quem chamou (a suíte usa isso para rodar as migrations
    # dentro de um schema descartável). Sem ela, o comportamento é o de sempre:
    # abrir a própria conexão a partir de DATABASE_URL.
    injected = config.attributes.get("connection")
    if injected is not None:
        do_run_migrations(injected)
    else:
        asyncio.run(run_migrations_online())
