import asyncio
import logging

from openai import AsyncOpenAI, RateLimitError

from app.ai.base import AIProvider

logger = logging.getLogger(__name__)

# Uma análise dispara ~7 chamadas em sequência, o que estoura com facilidade o
# limite de tokens/minuto de planos gratuitos. Esperar e repetir é suficiente:
# o limite é por janela de tempo, não uma recusa definitiva.
MAX_RETRIES = 3
FALLBACK_WAIT_SECONDS = 20.0
MAX_WAIT_SECONDS = 65.0


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str | None, model: str, base_url: str | None = None) -> None:
        if not api_key:
            raise ValueError("AI_API_KEY é obrigatório para AI_PROVIDER=openai.")
        self.model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def generate_text(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 4096
    ) -> str:
        for attempt in range(MAX_RETRIES):
            try:
                response = await self._client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                return response.choices[0].message.content or ""
            except RateLimitError as exc:
                if attempt == MAX_RETRIES - 1:
                    raise
                wait = _retry_after_seconds(exc) or FALLBACK_WAIT_SECONDS * (attempt + 1)
                logger.warning(
                    "Rate limit em %s (tentativa %d/%d); repetindo em %.1fs",
                    self.model,
                    attempt + 1,
                    MAX_RETRIES,
                    wait,
                )
                await asyncio.sleep(wait)

        raise AssertionError("inalcançável: o laço acima retorna ou levanta")  # pragma: no cover


def _retry_after_seconds(exc: RateLimitError) -> float | None:
    """Lê o `retry-after` que o provedor manda junto do 429. Preferimos esse
    valor ao backoff fixo porque ele reflete a janela real do rate limit."""
    response = getattr(exc, "response", None)
    raw = getattr(response, "headers", {}).get("retry-after") if response else None
    if raw is None:
        return None
    try:
        return min(float(raw), MAX_WAIT_SECONDS)
    except (TypeError, ValueError):
        return None
