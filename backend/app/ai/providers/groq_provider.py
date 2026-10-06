from app.ai.providers.openai_provider import OpenAIProvider

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(OpenAIProvider):
    """Groq pela API compatível com a da OpenAI (chat completions). Reaproveita
    o `OpenAIProvider` inteiro — retry em 429, timeout, tradução de erros —
    e só fixa o endpoint padrão, para `AI_BASE_URL` ser opcional.
    """

    name = "groq"
    default_model: str | None = "llama-3.3-70b-versatile"

    def __init__(self, api_key: str | None, model: str, base_url: str | None = None) -> None:
        if not api_key:
            raise ValueError("AI_API_KEY é obrigatório para AI_PROVIDER=groq.")
        super().__init__(api_key=api_key, model=model, base_url=base_url or GROQ_BASE_URL)
