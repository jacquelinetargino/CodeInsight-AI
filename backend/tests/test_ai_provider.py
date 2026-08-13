from types import SimpleNamespace

import pytest
from openai import RateLimitError

from app.ai.base import AIProvider, AIProviderError
from app.ai.factory import _PROVIDERS, UnknownAIProviderError, get_ai_provider
from app.ai.providers import openai_provider
from app.ai.providers.claude_provider import ClaudeProvider
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.local_provider import LocalAIProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.core.config import get_settings


class _FakeProvider(AIProvider):
    """Provider de teste: implementa só `generate_text` para exercitar o
    `generate_json` compartilhado da classe base."""

    name = "fake"

    def __init__(self, canned_text: str) -> None:
        self._canned_text = canned_text

    async def generate_text(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 4096
    ) -> str:
        return self._canned_text


async def test_generate_json_parses_fenced_block():
    provider = _FakeProvider('```json\n{"score": 80, "summary": "ok"}\n```')
    result = await provider.generate_json("system", "user")
    assert result == {"score": 80, "summary": "ok"}


async def test_generate_json_parses_raw_json():
    provider = _FakeProvider('{"score": 42, "findings": []}')
    result = await provider.generate_json("system", "user")
    assert result == {"score": 42, "findings": []}


async def test_generate_json_raises_on_invalid_json():
    provider = _FakeProvider("isso não é JSON")
    with pytest.raises(AIProviderError):
        await provider.generate_json("system", "user")


def test_factory_maps_all_documented_providers():
    assert set(_PROVIDERS) == {"claude", "openai", "gemini", "local"}
    assert _PROVIDERS["claude"] is ClaudeProvider
    assert _PROVIDERS["openai"] is OpenAIProvider
    assert _PROVIDERS["gemini"] is GeminiProvider
    assert _PROVIDERS["local"] is LocalAIProvider


@pytest.fixture(autouse=True)
def _clear_caches():
    get_settings.cache_clear()
    get_ai_provider.cache_clear()
    yield
    get_settings.cache_clear()
    get_ai_provider.cache_clear()


def test_get_ai_provider_returns_configured_provider(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "claude")
    assert isinstance(get_ai_provider(), ClaudeProvider)


def test_get_ai_provider_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "OpenAI")
    assert isinstance(get_ai_provider(), OpenAIProvider)


def test_get_ai_provider_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "not-a-real-provider")
    with pytest.raises(UnknownAIProviderError):
        get_ai_provider()


def test_local_provider_requires_base_url(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="AI_BASE_URL"):
        get_ai_provider()


def test_local_provider_works_with_base_url(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_BASE_URL", "http://localhost:11434/v1")
    assert isinstance(get_ai_provider(), LocalAIProvider)


class _FakeRateLimitError(RateLimitError):
    """Constrói um RateLimitError sem passar pelo __init__ do SDK, que exige um
    objeto de resposta httpx completo."""

    def __init__(self, retry_after: str | None) -> None:
        headers = {"retry-after": retry_after} if retry_after is not None else {}
        self.response = SimpleNamespace(headers=headers)


def _provider() -> OpenAIProvider:
    return OpenAIProvider(api_key="k", model="m", base_url="http://exemplo/v1")


async def test_generate_text_retries_after_rate_limit(monkeypatch):
    calls = []
    slept = []

    async def fake_create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise _FakeRateLimitError(retry_after="2")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="depois do retry"))]
        )

    provider = _provider()
    monkeypatch.setattr(provider._client.chat.completions, "create", fake_create)
    monkeypatch.setattr(openai_provider.asyncio, "sleep", lambda s: slept.append(s) or _noop())

    assert await provider.generate_text("s", "u") == "depois do retry"
    assert len(calls) == 2
    # Respeitou o retry-after do provedor em vez do backoff fixo.
    assert slept == [2.0]


async def test_generate_text_desiste_apos_o_limite_de_tentativas(monkeypatch):
    calls = []

    async def always_rate_limited(**kwargs):
        calls.append(kwargs)
        raise _FakeRateLimitError(retry_after=None)

    provider = _provider()
    monkeypatch.setattr(provider._client.chat.completions, "create", always_rate_limited)
    monkeypatch.setattr(openai_provider.asyncio, "sleep", lambda s: _noop())

    with pytest.raises(RateLimitError):
        await provider.generate_text("s", "u")
    assert len(calls) == openai_provider.MAX_RETRIES


async def _noop() -> None:
    return None
