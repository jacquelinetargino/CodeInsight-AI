import google.generativeai as genai

from app.ai.base import AIProvider


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        # O SDK google-generativeai não expõe override de base_url (é a API
        # gerenciada do Google); o parâmetro é aceito só para manter a mesma
        # assinatura dos demais providers.
        genai.configure(api_key=api_key)
        self.model_name = model

    async def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        model = genai.GenerativeModel(self.model_name, system_instruction=system_prompt)
        response = await model.generate_content_async(
            user_prompt,
            generation_config=genai.GenerationConfig(max_output_tokens=max_tokens),
        )
        return response.text
