from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from app.ai.base import AIProvider, AIProviderError
from app.ai.factory import (
    _PROVIDERS,
    AIProviderNotConfiguredError,
    UnknownAIProviderError,
    get_ai_provider,
    get_optional_ai_provider,
)
from app.ai.providers import openai_provider
from app.ai.providers.claude_provider import ClaudeProvider
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.groq_provider import GROQ_BASE_URL, GroqProvider
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
    assert set(_PROVIDERS) == {"claude", "openai", "gemini", "groq", "local"}
    assert _PROVIDERS["groq"] is GroqProvider
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
    monkeypatch.setenv("AI_API_KEY", "chave-de-teste")
    assert isinstance(get_ai_provider(), ClaudeProvider)


def test_get_ai_provider_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "OpenAI")
    monkeypatch.setenv("AI_API_KEY", "chave-de-teste")
    assert isinstance(get_ai_provider(), OpenAIProvider)


def test_get_ai_provider_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "not-a-real-provider")
    with pytest.raises(UnknownAIProviderError):
        get_ai_provider()


def test_local_without_base_url_counts_as_not_configured(monkeypatch):
    """Para `local`, o endpoint é o que define se há provedor — não a chave.
    Sem ele o estado é 'não configurado', não um erro de programação."""
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    with pytest.raises(AIProviderNotConfiguredError):
        get_ai_provider()


def test_local_provider_class_still_requires_base_url():
    """O contrato do próprio provider segue valendo quando instanciado direto,
    sem passar pela factory."""
    with pytest.raises(ValueError, match="AI_BASE_URL"):
        LocalAIProvider(api_key=None, model="m", base_url=None)


def test_local_provider_works_with_base_url(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("AI_MODEL", "qwen2.5-coder:7b")
    assert isinstance(get_ai_provider(), LocalAIProvider)


class _FakeRateLimitError(RateLimitError):
    """Constrói um RateLimitError sem passar pelo __init__ do SDK, que exige um
    objeto de resposta httpx completo."""

    def __init__(self, retry_after: str | None) -> None:
        headers = {"retry-after": retry_after} if retry_after is not None else {}
        self.response = SimpleNamespace(headers=headers)
        self.status_code = 429


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

    # Esgotadas as tentativas, o 429 sai como o erro do contrato (AIProviderError),
    # que as rotas traduzem em 502 — antes escapava cru e virava 500.
    with pytest.raises(AIProviderError, match="Limite de uso") as exc:
        await provider.generate_text("s", "u")
    assert isinstance(exc.value.__cause__, RateLimitError)
    assert len(calls) == openai_provider.MAX_RETRIES


async def _noop() -> None:
    return None


def test_optional_provider_is_none_when_unconfigured(monkeypatch):
    """O caminho que o motor próprio usa: sem IA, devolve None em vez de falhar."""
    monkeypatch.delenv("AI_API_KEY", raising=False)
    assert get_optional_ai_provider() is None


def test_optional_provider_returns_provider_when_configured(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "claude")
    monkeypatch.setenv("AI_API_KEY", "chave-de-teste")
    assert isinstance(get_optional_ai_provider(), ClaudeProvider)


def test_optional_provider_is_none_for_unknown_provider(monkeypatch):
    """Configuração inválida também não pode derrubar quem só quer saber se há IA."""
    monkeypatch.setenv("AI_PROVIDER", "not-a-real-provider")
    monkeypatch.setenv("AI_API_KEY", "chave-de-teste")
    assert get_optional_ai_provider() is None


def test_get_ai_provider_raises_when_unconfigured(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "claude")
    monkeypatch.delenv("AI_API_KEY", raising=False)
    with pytest.raises(AIProviderNotConfiguredError):
        get_ai_provider()


# --- o contrato de construção dos providers ---------------------------------


def test_todo_provider_aceita_a_mesma_assinatura():
    """A factory constrói qualquer provider com `(api_key, model, base_url)`.

    O contrato existia e não estava declarado em lugar nenhum — nada verificava
    se um provider novo o respeitava. Agora está em `AIProvider.__init__`, e
    este teste confirma que os concretos o seguem.
    """
    import inspect

    from app.ai.base import AIProvider
    from app.ai.factory import _PROVIDERS

    esperado = list(inspect.signature(AIProvider.__init__).parameters)

    for nome, classe in _PROVIDERS.items():
        assinatura = list(inspect.signature(classe.__init__).parameters)
        assert assinatura == esperado, f"{nome}: {assinatura} != {esperado}"


@pytest.mark.parametrize("provider", ["claude", "openai", "gemini", "groq"])
def test_provider_sem_chave_falha_com_mensagem_propria(provider):
    """Sem chave, o erro precisa dizer qual variável falta — antes o `None` ia
    para dentro do SDK e voltava como erro obscuro dele."""
    from app.ai.factory import _PROVIDERS

    with pytest.raises(ValueError, match="AI_API_KEY"):
        _PROVIDERS[provider](api_key=None, model="qualquer", base_url=None)


def test_provider_local_nao_exige_chave_mas_exige_endpoint():
    """Servidor local aceita qualquer chave; o que importa é o endpoint."""
    from app.ai.factory import _PROVIDERS

    with pytest.raises(ValueError, match="AI_BASE_URL"):
        _PROVIDERS["local"](api_key=None, model="llama", base_url=None)

    # Com endpoint, constrói sem chave.
    assert _PROVIDERS["local"](api_key=None, model="llama", base_url="http://localhost:11434/v1")


# --- Groq ---------------------------------------------------------------------


def test_groq_usa_o_endpoint_compativel_com_openai_por_padrao():
    provider = GroqProvider(api_key="chave-de-teste", model="llama-3.3-70b-versatile")
    assert GROQ_BASE_URL == "https://api.groq.com/openai/v1"
    assert str(provider._client.base_url).rstrip("/") == GROQ_BASE_URL
    assert provider._client.api_key == "chave-de-teste"
    assert provider.model == "llama-3.3-70b-versatile"


def test_groq_respeita_ai_base_url_explicito():
    provider = GroqProvider(api_key="k", model="m", base_url="http://proxy.interno/v1")
    assert str(provider._client.base_url).rstrip("/") == "http://proxy.interno/v1"


def test_factory_monta_groq_a_partir_das_variaveis(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("AI_API_KEY", "chave-de-teste")
    monkeypatch.setenv("AI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("AI_MODEL", "llama-3.3-70b-versatile")

    provider = get_ai_provider()

    assert isinstance(provider, GroqProvider)
    assert provider.model == "llama-3.3-70b-versatile"
    assert str(provider._client.base_url).rstrip("/") == GROQ_BASE_URL


def test_groq_sem_chave_conta_como_nao_configurado(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.delenv("AI_API_KEY", raising=False)
    with pytest.raises(AIProviderNotConfiguredError, match="AI_API_KEY"):
        get_ai_provider()


# --- modelo padrão -------------------------------------------------------------


def test_sem_ai_model_cada_provider_usa_o_proprio_padrao(monkeypatch):
    """Antes havia um único padrão global ("claude-sonnet-5"): trocar só o
    AI_PROVIDER para groq mandava um modelo da Anthropic para a Groq."""
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.delenv("AI_MODEL", raising=False)
    assert get_ai_provider().model == "llama-3.3-70b-versatile"


def test_ai_model_sobrescreve_o_padrao(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("AI_MODEL", "llama-3.1-8b-instant")
    assert get_ai_provider().model == "llama-3.1-8b-instant"


def test_local_sem_modelo_conta_como_nao_configurado(monkeypatch):
    """Servidor local não tem modelo padrão possível: depende do que foi baixado."""
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("AI_MODEL", raising=False)
    with pytest.raises(AIProviderNotConfiguredError, match="AI_MODEL"):
        get_ai_provider()


# --- tradução de erros do provedor --------------------------------------------

_REQ = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def _status_error(status_code: int, message: str = "erro") -> APIStatusError:
    return APIStatusError(message, response=httpx.Response(status_code, request=_REQ), body=None)


def _groq_que_falha(monkeypatch, exc: Exception) -> GroqProvider:
    provider = GroqProvider(api_key="gsk_chave_secreta_de_teste", model="m")

    async def falha(**kwargs):
        raise exc

    monkeypatch.setattr(provider._client.chat.completions, "create", falha)
    return provider


@pytest.mark.parametrize(
    ("status_code", "trecho"),
    [
        (401, "AI_API_KEY"),
        (404, "AI_MODEL"),
        (413, "AI_MAX_CONTEXT_CHARS"),
        (500, "erro 500"),
    ],
)
async def test_erro_http_vira_ai_provider_error(monkeypatch, status_code, trecho):
    provider = _groq_que_falha(monkeypatch, _status_error(status_code))
    with pytest.raises(AIProviderError, match=trecho):
        await provider.generate_text("s", "u")


async def test_mensagem_de_erro_nao_ecoa_a_chave(monkeypatch):
    """Alguns provedores devolvem parte da chave no corpo do 401; a mensagem que
    chega ao usuário (e ao log) é montada por nós, não repassada."""
    provider = _groq_que_falha(
        monkeypatch, _status_error(401, "Invalid API Key: gsk_chave_secreta_de_teste")
    )
    with pytest.raises(AIProviderError) as exc:
        await provider.generate_text("s", "u")
    assert "gsk_" not in str(exc.value)


async def test_timeout_vira_ai_provider_error(monkeypatch):
    provider = _groq_que_falha(monkeypatch, APITimeoutError(request=_REQ))
    with pytest.raises(AIProviderError, match="não respondeu"):
        await provider.generate_text("s", "u")


async def test_falha_de_conexao_vira_ai_provider_error(monkeypatch):
    provider = _groq_que_falha(monkeypatch, APIConnectionError(request=_REQ))
    with pytest.raises(AIProviderError, match="conectar"):
        await provider.generate_text("s", "u")


def test_cliente_tem_timeout_explicito():
    provider = GroqProvider(api_key="k", model="m")
    assert provider._client.timeout == openai_provider.REQUEST_TIMEOUT_SECONDS


def _resposta(conteudo):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=conteudo))])


@pytest.mark.parametrize("conteudo", [None, "", "   \n"])
async def test_resposta_vazia_vira_ai_provider_error(monkeypatch, conteudo):
    provider = GroqProvider(api_key="k", model="m")

    async def vazio(**kwargs):
        return _resposta(conteudo)

    monkeypatch.setattr(provider._client.chat.completions, "create", vazio)
    with pytest.raises(AIProviderError, match="vazia"):
        await provider.generate_text("s", "u")


async def test_resposta_sem_choices_vira_ai_provider_error(monkeypatch):
    provider = GroqProvider(api_key="k", model="m")

    async def sem_choices(**kwargs):
        return SimpleNamespace(choices=[])

    monkeypatch.setattr(provider._client.chat.completions, "create", sem_choices)
    with pytest.raises(AIProviderError, match="vazia"):
        await provider.generate_text("s", "u")


async def test_chamada_usa_modelo_e_mensagens_configurados(monkeypatch):
    provider = GroqProvider(api_key="k", model="llama-3.3-70b-versatile")
    chamadas = []

    async def captura(**kwargs):
        chamadas.append(kwargs)
        return _resposta("# OK")

    monkeypatch.setattr(provider._client.chat.completions, "create", captura)

    assert await provider.generate_text("sistema", "usuário", max_tokens=123) == "# OK"
    assert chamadas[0]["model"] == "llama-3.3-70b-versatile"
    assert chamadas[0]["max_tokens"] == 123
    assert chamadas[0]["messages"] == [
        {"role": "system", "content": "sistema"},
        {"role": "user", "content": "usuário"},
    ]
