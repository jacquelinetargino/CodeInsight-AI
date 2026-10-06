import asyncio
import logging

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletion

from app.ai.base import AIProvider, AIProviderError

logger = logging.getLogger(__name__)

# Uma análise dispara ~7 chamadas em sequência, o que estoura com facilidade o
# limite de tokens/minuto de planos gratuitos. Esperar e repetir é suficiente:
# o limite é por janela de tempo, não uma recusa definitiva.
MAX_RETRIES = 3
FALLBACK_WAIT_SECONDS = 20.0
MAX_WAIT_SECONDS = 65.0

# O padrão do SDK é 600s. Gerar um README leva dezenas de segundos; esperar dez
# minutos só prende a requisição do usuário até o proxy da hospedagem desistir.
REQUEST_TIMEOUT_SECONDS = 120.0


class OpenAIProvider(AIProvider):
    name = "openai"
    default_model: str | None = "gpt-4o-mini"

    def __init__(self, api_key: str | None, model: str, base_url: str | None = None) -> None:
        if not api_key:
            raise ValueError("AI_API_KEY é obrigatório para AI_PROVIDER=openai.")
        self.model = model
        self._client = AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS
        )

    async def generate_text(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 4096
    ) -> str:
        try:
            response = await self._create_with_retry(system_prompt, user_prompt, max_tokens)
        # As mensagens abaixo são montadas aqui, e não repassadas do SDK: o
        # corpo de erro de alguns provedores ecoa parte da chave recusada.
        except APITimeoutError as exc:
            raise AIProviderError(
                f"O provedor de IA não respondeu em {REQUEST_TIMEOUT_SECONDS:.0f}s."
            ) from exc
        except APIConnectionError as exc:
            raise AIProviderError("Não foi possível conectar ao provedor de IA.") from exc
        except APIStatusError as exc:
            raise AIProviderError(_mensagem_de_status(exc.status_code)) from exc

        content = response.choices[0].message.content if response.choices else None
        if not content or not content.strip():
            raise AIProviderError("O provedor de IA devolveu uma resposta vazia.")
        return content

    async def _create_with_retry(
        self, system_prompt: str, user_prompt: str, max_tokens: int
    ) -> ChatCompletion:
        for attempt in range(MAX_RETRIES):
            try:
                return await self._client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
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


def _mensagem_de_status(status_code: int) -> str:
    if status_code in (401, 403):
        return "O provedor de IA recusou a chave (AI_API_KEY inválida ou sem permissão)."
    if status_code == 404:
        return "O provedor de IA não encontrou o modelo configurado em AI_MODEL."
    if status_code == 413:
        # No plano gratuito da Groq o teto é por minuto e conta o prompt inteiro:
        # um repositório grande estoura antes de qualquer retry ajudar.
        return (
            "O pedido excedeu o limite de tamanho do provedor de IA. "
            "Reduza AI_MAX_CONTEXT_CHARS."
        )
    if status_code == 429:
        return "Limite de uso do provedor de IA atingido. Tente de novo em alguns minutos."
    return f"O provedor de IA respondeu com erro {status_code}."


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
