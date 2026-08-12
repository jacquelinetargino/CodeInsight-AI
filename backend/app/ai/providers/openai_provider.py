from openai import AsyncOpenAI

from app.ai.base import AIProvider


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        self.model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        response = await self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""
