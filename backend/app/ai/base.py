"""Interface comum a qualquer provedor de IA usado pela aplicação.

Nenhum outro módulo (services, tasks, rotas) deve importar um SDK de IA
específico — sempre dependa de `AIProvider`, obtido via
`app.ai.factory.get_ai_provider()`. Isso é o que permite trocar de Claude
para OpenAI/Gemini/um modelo local só mudando variáveis de ambiente.
"""

import json
import re
from abc import ABC, abstractmethod

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", re.DOTALL)


class AIProviderError(Exception):
    """Erro de comunicação com o provedor ou resposta em formato inesperado."""


class AIProvider(ABC):
    name: str

    @abstractmethod
    async def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        """Chama o modelo e retorna a resposta em texto livre (ex.: um README em markdown).
        Cada provider implementa isso usando seu próprio SDK/cliente HTTP."""
        raise NotImplementedError

    async def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict | list:
        """Chama o modelo esperando uma resposta em JSON e já retorna parseada.

        Implementado uma única vez aqui (em cima de `generate_text`) para que
        nenhum provider precise duplicar a lógica de extração/parsing de JSON.
        """
        text = await self.generate_text(system_prompt, user_prompt, max_tokens=max_tokens)
        return self._extract_json(text)

    @staticmethod
    def _extract_json(text: str) -> dict | list:
        match = _JSON_BLOCK_RE.search(text)
        raw = match.group(1) if match else text.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIProviderError(f"Resposta do provedor de IA não é um JSON válido: {exc}") from exc
