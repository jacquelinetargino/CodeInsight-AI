import os
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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.base import AIProvider
from app.ai.factory import get_ai_provider
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User

TEST_DATABASE_URL = os.environ["DATABASE_URL"]

# Trava de segurança: as fixtures abaixo rodam drop_all() a cada teste. Apontar
# DATABASE_URL para um banco remoto (Supabase, Render...) e rodar a suíte
# apagaria o schema de produção — algo fácil de fazer sem querer, já que a mesma
# variável é usada em dev, em deploy e nos testes.
_ALLOWED_TEST_HOSTS = ("localhost", "127.0.0.1", "postgres", "::1")
if not any(f"@{host}" in TEST_DATABASE_URL for host in _ALLOWED_TEST_HOSTS):
    raise RuntimeError(
        "DATABASE_URL aponta para um host que não é local. A suíte apaga todas as "
        "tabelas entre os testes — recusando rodar para não destruir dados reais. "
        f"Hosts permitidos: {', '.join(_ALLOWED_TEST_HOSTS)}."
    )


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Engine novo por teste (não session-scoped): conexões do asyncpg ficam
    presas ao event loop em que foram criadas, e o pytest-asyncio cria um loop
    novo por função de teste por padrão — reaproveitar um engine entre testes
    causa erros do tipo "attached to a different loop"."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
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
    """Troca `get_ai_provider` por um `ScriptedAIProvider` com respostas fixas.
    Uso: override_ai_provider(json_responses=[{...}, {...}])."""

    def _set(*, text_responses=None, json_responses=None) -> ScriptedAIProvider:
        provider = ScriptedAIProvider(text_responses=text_responses, json_responses=json_responses)
        app.dependency_overrides[get_ai_provider] = lambda: provider
        return provider

    yield _set
    app.dependency_overrides.pop(get_ai_provider, None)
