# Provedores de IA

O CodeInsight AI não depende de nenhum SDK de IA específico. Toda a lógica de
análise, geração de README e sugestões fala apenas com a interface
`AIProvider` (`backend/app/ai/base.py`). Qual implementação concreta é usada
em runtime é decidido só por variáveis de ambiente.

## Como funciona

```
app/ai/base.py
  class AIProvider(ABC):
      name: str
      async def generate_text(system, user, max_tokens) -> str        # cada provider implementa
      async def generate_json(system, user, max_tokens) -> dict|list  # implementado 1x na base:
                                                                        # chama generate_text() e faz o parsing do JSON

app/ai/providers/
  claude_provider.py    -> ClaudeProvider   (SDK oficial da Anthropic)
  openai_provider.py     -> OpenAIProvider   (SDK oficial da OpenAI, chat.completions)
  gemini_provider.py     -> GeminiProvider   (google-generativeai)
  local_provider.py      -> LocalAIProvider  (subclasse de OpenAIProvider, aponta para um base_url custom)

app/ai/factory.py
  get_ai_provider() -> AIProvider
```

`analysis_service.py` e as rotas que chamam IA recebem um `AIProvider` já
instanciado (via `Depends(get_ai_provider)` nas rotas, ou chamando
`get_optional_ai_provider()` diretamente na task de análise) — nunca importam
`anthropic`, `openai` ou `google.generativeai` diretamente.

## Configuração (variáveis de ambiente)

```env
AI_PROVIDER=claude   # claude | openai | gemini | local
AI_API_KEY=...
AI_MODEL=claude-sonnet-5
AI_BASE_URL=          # obrigatório só para "local"; opcional para apontar
                       # os demais para um endpoint compatível custom
```

| Provider | `AI_MODEL` (exemplos) | `AI_BASE_URL` |
|---|---|---|
| `claude` | `claude-sonnet-5`, `claude-opus-5` | opcional |
| `openai` | `gpt-4o`, `gpt-4o-mini` | opcional |
| `gemini` | `gemini-1.5-pro`, `gemini-1.5-flash` | não suportado pelo SDK atual |
| `local` | o nome do modelo carregado no seu servidor | **obrigatório** (ex.: `http://localhost:11434/v1` para o Ollama) |

`local` funciona com qualquer servidor que exponha uma API compatível com a
da OpenAI (Ollama, LM Studio, vLLM, llama.cpp server, text-generation-webui
com o flag `--api`, etc.) — por isso ele é implementado como uma subclasse de
`OpenAIProvider` que só troca o `base_url`.

## Como adicionar um novo provedor

Sem tocar em `analysis_service.py`, nas rotas ou em qualquer outro lugar da
aplicação:

1. Crie `app/ai/providers/meu_provider.py`:

   ```python
   from app.ai.base import AIProvider

   class MeuProvider(AIProvider):
       name = "meu_provider"

       def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
           self.model = model
           # instancie aqui o client do SDK/HTTP do seu provedor

       async def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
           # chame o provedor e retorne a resposta como string
           ...
   ```

   Não é necessário implementar `generate_json` — a classe base já faz isso
   chamando `generate_text` e extraindo o JSON da resposta (incluindo respostas
   dentro de blocos ```json).

2. Registre em `app/ai/factory.py`:

   ```python
   from app.ai.providers.meu_provider import MeuProvider

   _PROVIDERS = {
       ...,
       "meu_provider": MeuProvider,
   }
   ```

3. Configure `AI_PROVIDER=meu_provider` no `.env`.

Pronto — nenhuma outra parte do sistema precisa ser alterada, porque tudo
depende só de `AIProvider`.

## Limitações conhecidas

- `GeminiProvider` não usa `AI_BASE_URL` (o SDK `google-generativeai` fala só
  com a API gerenciada do Google); o parâmetro é aceito na assinatura por
  consistência com os outros providers, mas é ignorado.
- Não há retry/fallback automático entre provedores — se a chamada de IA
  falhar, a análise inteira é marcada como `failed` (ver `app/tasks/analysis_tasks.py`).
