from app.ai.providers.openai_provider import OpenAIProvider


class LocalAIProvider(OpenAIProvider):
    """Qualquer servidor local compatível com a API de chat completions da
    OpenAI — Ollama, LM Studio, vLLM, llama.cpp server, etc. Reaproveita o
    `OpenAIProvider` por completo: a única diferença é apontar o cliente para
    um `base_url` custom em vez da API oficial da OpenAI.
    """

    name = "local"

    def __init__(self, api_key: str | None, model: str, base_url: str | None = None) -> None:
        if not base_url:
            raise ValueError(
                "AI_BASE_URL é obrigatório quando AI_PROVIDER=local "
                "(ex.: http://localhost:11434/v1 para o Ollama)."
            )
        # A maioria dos servidores locais não exige uma chave de verdade.
        super().__init__(api_key=api_key or "not-needed", model=model, base_url=base_url)
