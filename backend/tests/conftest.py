import os
import re
import uuid
from collections.abc import AsyncGenerator

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://codeinsight:codeinsight@localhost:5432/codeinsight_test"
)
os.environ.setdefault("JWT_SECRET", "test-secret-key")
os.environ.setdefault("ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")

# Nenhuma variável de IA é definida aqui de propósito: o estado padrão da suíte
# é "sem provedor configurado", que é o mesmo de uma instalação normal. Testes
# que precisam de um provedor devem declarar isso explicitamente com monkeypatch.

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.base import AIProvider
from app.api.routes.analysis import require_ai_provider
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User

TEST_DATABASE_URL = os.environ["DATABASE_URL"]

# Isolamento por schema (OPCIONAL, só para desenvolvimento local).
#
# O padrão — usado pelo CI e recomendado para qualquer dev — é um BANCO de testes
# dedicado (ex.: `codeinsight_test`), onde a suíte usa o schema `public` à
# vontade. Criar um banco exige a permissão CREATEDB, que nem todo ambiente
# concede; quando ela falta, defina TEST_DB_SCHEMA e a suíte passa a viver num
# schema separado dentro do banco já existente, sem tocar em `public`.
#
#   pytest                                    -> banco de testes dedicado (padrão)
#   TEST_DB_SCHEMA=codeinsight_test pytest    -> schema isolado no banco atual
TEST_SCHEMA = os.environ.get("TEST_DB_SCHEMA", "").strip()

# --- Travas de segurança ---------------------------------------------------
# As fixtures abaixo rodam drop_all() a cada teste, então apontar para o lugar
# errado destrói dados de verdade. Cada trava cobre um erro plausível.

# 1) Banco remoto: a mesma variável DATABASE_URL é usada em dev, deploy e testes,
#    então apontar para produção sem querer é fácil.
_ALLOWED_TEST_HOSTS = ("localhost", "127.0.0.1", "postgres", "::1")
if not any(f"@{host}" in TEST_DATABASE_URL for host in _ALLOWED_TEST_HOSTS):
    raise RuntimeError(
        "DATABASE_URL aponta para um host que não é local. A suíte apaga todas as "
        "tabelas entre os testes — recusando rodar para não destruir dados reais. "
        f"Hosts permitidos: {', '.join(_ALLOWED_TEST_HOSTS)}."
    )

if TEST_SCHEMA:
    # 2) O schema isolado nunca pode ser `public`: é lá que vivem os dados de
    #    desenvolvimento do banco compartilhado.
    if TEST_SCHEMA == "public":
        raise RuntimeError(
            "TEST_DB_SCHEMA=public é proibido: o modo de schema isolado existe "
            "justamente para não tocar em `public`."
        )
    # 3) O nome vira identificador SQL, então precisa ser um identificador de fato.
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", TEST_SCHEMA):
        raise RuntimeError(
            f"TEST_DB_SCHEMA={TEST_SCHEMA!r} não é um identificador SQL válido "
            "(use letras, dígitos e underscore, começando por letra ou underscore)."
        )
else:
    # 4) Sem schema isolado, a suíte usa `public` — o que só é seguro num banco
    #    descartável. Exigir "test" no nome impede o acidente clássico de apontar
    #    DATABASE_URL para o banco de desenvolvimento e perder os dados.
    _db_name = TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?")[0]
    if "test" not in _db_name.lower():
        raise RuntimeError(
            f"O banco {_db_name!r} não parece ser de testes e nenhum TEST_DB_SCHEMA "
            "foi definido. A suíte apaga todas as tabelas entre os testes. Use um "
            "banco dedicado (ex.: codeinsight_test) ou defina TEST_DB_SCHEMA para "
            "isolar a suíte num schema separado."
        )


def _engine_kwargs() -> dict:
    """No modo isolado, o search_path faz create_all/drop_all agirem dentro do
    schema de testes em vez de `public`."""
    if not TEST_SCHEMA:
        return {}
    return {"connect_args": {"server_settings": {"search_path": TEST_SCHEMA}}}


async def _prepare_schema(conn) -> None:
    """Cria o schema de testes e confirma que ele é mesmo o schema efetivo —
    se o search_path não tivesse pegado, o drop_all seguinte atingiria `public`."""
    if not TEST_SCHEMA:
        return
    await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{TEST_SCHEMA}"'))
    current = (await conn.execute(text("SELECT current_schema()"))).scalar()
    if current != TEST_SCHEMA:
        raise RuntimeError(
            f"Schema efetivo é {current!r}, esperado {TEST_SCHEMA!r}. Abortando "
            "antes de qualquer DDL para não afetar o schema errado."
        )


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Engine novo por teste (não session-scoped): conexões do asyncpg ficam
    presas ao event loop em que foram criadas, e o pytest-asyncio cria um loop
    novo por função de teste por padrão — reaproveitar um engine entre testes
    causa erros do tipo "attached to a different loop"."""
    engine = create_async_engine(TEST_DATABASE_URL, **_engine_kwargs())
    async with engine.begin() as conn:
        await _prepare_schema(conn)
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email="octocat@example.com",
        hashed_password=hash_password("correct-horse-battery-staple"),
        username="octocat",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def authed_client_factory():
    """Retorna os headers de Authorization (Bearer) para autenticar requests nos testes."""

    def _make_headers(user_id: uuid.UUID) -> dict[str, str]:
        token = create_access_token(str(user_id))
        return {"Authorization": f"Bearer {token}"}

    return _make_headers


class ScriptedAIProvider(AIProvider):
    """Provider de IA falso para testes: retorna respostas pré-programadas em
    vez de chamar um SDK de verdade."""

    name = "scripted"

    def __init__(self, text_responses=None, json_responses=None) -> None:
        self._text_responses = list(text_responses or [])
        self._json_responses = list(json_responses or [])

    async def generate_text(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 4096
    ) -> str:
        return self._text_responses.pop(0)

    async def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096):
        return self._json_responses.pop(0)


@pytest.fixture
def override_ai_provider():
    """Troca o provedor de IA por um `ScriptedAIProvider` com respostas fixas.
    Uso: override_ai_provider(json_responses=[{...}, {...}]).

    O override tem de usar exatamente o callable declarado no `Depends()` das
    rotas — `require_ai_provider` — porque é assim que o FastAPI indexa
    `dependency_overrides`."""

    def _set(*, text_responses=None, json_responses=None) -> ScriptedAIProvider:
        provider = ScriptedAIProvider(text_responses=text_responses, json_responses=json_responses)
        app.dependency_overrides[require_ai_provider] = lambda: provider
        return provider

    yield _set
    app.dependency_overrides.pop(require_ai_provider, None)
