import pytest

from app.ai.base import AIProvider, AIProviderError
from app.ai.factory import _PROVIDERS, UnknownAIProviderError, get_ai_provider
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
