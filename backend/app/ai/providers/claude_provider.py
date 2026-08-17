from anthropic import AsyncAnthropic

from app.ai.base import AIProvider


class ClaudeProvider(AIProvider):
    name = "claude"

    def __init__(self, api_key: str | None, model: str, base_url: str | None = None) -> None:
        if not api_key:
            raise ValueError("AI_API_KEY é obrigatório para AI_PROVIDER=claude.")
        self.model = model
        self._client = AsyncAnthropic(api_key=api_key, base_url=base_url)

    async def generate_text(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 4096
    ) -> str:
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
