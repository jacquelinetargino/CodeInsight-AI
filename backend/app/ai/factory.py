"""Resolve qual `AIProvider` usar a partir de variáveis de ambiente
(AI_PROVIDER, AI_API_KEY, AI_MODEL, AI_BASE_URL).

LEGACY/OPCIONAL: nenhum provedor externo é necessário para a análise — quem
faz o trabalho principal é o CodeInsight Engine, em Python puro. Use
`get_optional_ai_provider()` em código que deve funcionar sem IA, e
`get_ai_provider()` apenas onde a IA é o ponto do recurso (gerar README,
sugerir correção) — lá a ausência é erro legítimo.

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


class AIProviderNotConfiguredError(Exception):
    """Nenhum provedor de IA disponível. Não é falha: é o estado padrão de uma
    instalação que roda só com o motor próprio."""


@lru_cache
def get_ai_provider() -> AIProvider:
    """O provedor configurado, ou erro se não houver. Use só onde a IA é o
    próprio recurso pedido pelo usuário."""
    settings = get_settings()
    provider_key = settings.ai_provider.lower().strip()

    provider_cls = _PROVIDERS.get(provider_key)
    if provider_cls is None:
        raise UnknownAIProviderError(
            f"AI_PROVIDER={settings.ai_provider!r} desconhecido. "
            f"Opções válidas: {', '.join(sorted(_PROVIDERS))}."
        )

    if not settings.ai_configured:
        raise AIProviderNotConfiguredError(
            "Nenhum provedor de IA configurado. Este recurso é opcional e exige "
            "AI_API_KEY (ou AI_BASE_URL, para AI_PROVIDER=local). A análise de "
            "repositórios não depende disso."
        )

    return provider_cls(
        api_key=settings.ai_api_key, model=settings.ai_model, base_url=settings.ai_base_url
    )


def get_optional_ai_provider() -> AIProvider | None:
    """O provedor configurado, ou `None` quando não há — sem levantar exceção.
    É o caminho para código que deve funcionar igual com ou sem IA."""
    try:
        return get_ai_provider()
    except (AIProviderNotConfiguredError, UnknownAIProviderError, ValueError):
        # ValueError cobre o LocalAIProvider sem AI_BASE_URL.
        return None
