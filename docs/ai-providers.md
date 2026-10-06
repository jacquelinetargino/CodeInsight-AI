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
  groq_provider.py       -> GroqProvider     (subclasse de OpenAIProvider, endpoint da Groq por padrão)
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
AI_PROVIDER=claude   # claude | openai | gemini | groq | local
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
| `groq` | `llama-3.3-70b-versatile`, `llama-3.1-8b-instant` | opcional (padrão `https://api.groq.com/openai/v1`) |
| `local` | o nome do modelo carregado no seu servidor | **obrigatório** (ex.: `http://localhost:11434/v1` para o Ollama) |

Sem `AI_MODEL`, cada provider usa o próprio modelo padrão (`default_model` na
classe): `claude-sonnet-5`, `gpt-4o-mini`, `gemini-1.5-flash`,
`llama-3.3-70b-versatile`. `local` não tem padrão — o modelo depende do que foi
baixado no servidor — e sem `AI_MODEL` conta como não configurado.

`local` funciona com qualquer servidor que exponha uma API compatível com a
da OpenAI (Ollama, LM Studio, vLLM, llama.cpp server, text-generation-webui
com o flag `--api`, etc.) — por isso ele é implementado como uma subclasse de
`OpenAIProvider` que só troca o `base_url`.

## Groq

A Groq expõe uma API compatível com a de chat completions da OpenAI, então
`GroqProvider` é uma subclasse de `OpenAIProvider` que só fixa o endpoint
padrão — retry em 429, timeout e tradução de erros vêm de lá.

```env
AI_PROVIDER=groq
AI_API_KEY=your-groq-api-key
AI_BASE_URL=https://api.groq.com/openai/v1   # opcional, já é o padrão
AI_MODEL=llama-3.3-70b-versatile
AI_MAX_CONTEXT_CHARS=16000
```

- **A chave fica só no backend** (variável de ambiente do servidor). Nunca em
  variável `VITE_*`, que vai embutida no JavaScript público, nem em arquivo
  versionado. O frontend só fala com a API do CodeInsight.
- **`AI_MAX_CONTEXT_CHARS=16000`**: o plano gratuito limita o
  `llama-3.3-70b-versatile` a 12 mil tokens por minuto, e o prompt e a resposta
  (até 6000 tokens no README) entram nessa conta. Com o padrão de 100 mil
  caracteres (~28 mil tokens) a Groq recusa o pedido inteiro com 413.
- A análise de repositórios não depende da Groq; sem a chave, só README,
  correções e sugestões ficam indisponíveis (503).

## Erros do provedor

`OpenAIProvider` (e portanto `local` e `groq`) traduz falhas do SDK em
`AIProviderError`, com mensagem montada pelo próprio código — nunca o corpo de
erro do provedor, que pode ecoar parte da chave:

| Situação | Mensagem | HTTP nas rotas |
|---|---|---|
| 401/403 | chave inválida ou sem permissão | 502 |
| 404 | modelo de `AI_MODEL` não encontrado | 502 |
| 413 | pedido grande demais — reduza `AI_MAX_CONTEXT_CHARS` | 502 |
| 429 após 3 tentativas | limite de uso atingido | 502 |
| timeout (120s) / falha de conexão | provedor não respondeu / não conectou | 502 |
| resposta vazia | resposta vazia | 502 |
| sem chave / `AI_PROVIDER` desconhecido | nenhum provedor configurado | 503 |

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
- Não há fallback automático entre provedores. Se a chamada de IA falhar
  durante a análise, a análise continua concluída — só as sugestões por IA
  ficam de fora (ver `_enrich_with_ai` em `app/tasks/analysis_tasks.py`).
