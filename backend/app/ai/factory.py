"""Resolve qual `AIProvider` usar a partir de variáveis de ambiente
(AI_PROVIDER, AI_API_KEY, AI_MODEL, AI_BASE_URL).

Para adicionar um novo provedor: crie uma classe em `app/ai/providers/` que
implemente `AIProvider.generate_text`, registre uma entrada em `_PROVIDERS`
abaixo — nenhuma outra parte do sistema precisa mudar. Veja também
`docs/ai-providers.md`.
"""

from functools import lru_cache

from app.ai.base import AIProvider
from app.ai.providers.claude_provider import ClaudeProvider
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.local_provider import LocalAIProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.core.config import get_settings

_PROVIDERS: dict[str, type[AIProvider]] = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "local": LocalAIProvider,
}


class UnknownAIProviderError(Exception):
    pass


@lru_cache
def get_ai_provider() -> AIProvider:
    settings = get_settings()
    provider_key = settings.ai_provider.lower().strip()

    provider_cls = _PROVIDERS.get(provider_key)
    if provider_cls is None:
        raise UnknownAIProviderError(
            f"AI_PROVIDER={settings.ai_provider!r} desconhecido. "
            f"Opções válidas: {', '.join(sorted(_PROVIDERS))}."
        )

    return provider_cls(api_key=settings.ai_api_key, model=settings.ai_model, base_url=settings.ai_base_url)
