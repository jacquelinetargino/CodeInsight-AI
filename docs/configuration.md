# Configuração

Todas as variáveis de ambiente ficam num único `.env` na raiz do projeto (lido pelo
`docker-compose.yml` via `env_file`, e pelo backend via `pydantic-settings`). Copie
`.env.example` para `.env` e preencha os valores — **nunca** versione o `.env`.

## App

| Variável | Padrão | Descrição |
|---|---|---|
| `APP_ENV` | `development` | `development` ou `production` (afeta cookies/CORS se aplicável) |
| `APP_NAME` | `CodeInsight AI` | Nome exibido |
| `API_V1_PREFIX` | `/api/v1` | Prefixo das rotas da API |
| `FRONTEND_URL` | `http://localhost:5173` | Usado pelo CORS |
| `BACKEND_URL` | `http://localhost:8000` | — |

## Banco de dados

| Variável | Descrição |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Credenciais do Postgres (usadas pelo container `postgres` e pela `DATABASE_URL`) |
| `DATABASE_URL` | String de conexão async: `postgresql+asyncpg://user:pass@host:5432/db` |

## Motor de análise

Todas têm padrão razoável — só mexa se souber por quê. Os limites existem porque o
repositório analisado é dado de terceiros e pode ser hostil.

| Variável | Padrão | Descrição |
|---|---|---|
| `ENGINE_MAX_ARCHIVE_BYTES` | — | Teto de bytes recebidos durante o download. O GitHub responde sem `Content-Length`, então a contagem é feita durante a transferência e aborta ao estourar |
| `ENGINE_MAX_UNCOMPRESSED_BYTES` | `200 MB` | Teto do conteúdo descomprimido, contra bomba de descompressão |
| `ENGINE_MAX_FILES` | `20000` | Teto de arquivos inventariados |
| `ENGINE_MAX_FILE_BYTES` | `2 MB` | Arquivo acima disso não é lido. Continua inventariado: um binário enorme ou uma chave privada grande demais ainda são achados |
| `ENGINE_MAX_ANALYSIS_SECONDS` | `300` | Timeout da análise. Medido: django/django (7008 arquivos) leva ~116s. A análise roda em thread, então esperar mais não bloqueia o event loop |

## Segurança

| Variável | Descrição |
|---|---|
| `JWT_SECRET` | Chave de assinatura dos tokens JWT. Gere com `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `JWT_ALGORITHM` | Padrão `HS256` |
| `JWT_EXPIRE_MINUTES` | Validade do token de acesso (padrão 1440 = 24h) |
| `ENCRYPTION_KEY` | Chave Fernet usada para criptografar o PAT do GitHub em repouso. Gere com `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

## GitHub

| Variável | Descrição |
|---|---|
| `GITHUB_TOKEN` | **Opcional.** Token do servidor (não do usuário) para elevar o rate limit de requisições não autenticadas (60/h → 5000/h) ao analisar repositórios públicos. Crie em [github.com/settings/tokens](https://github.com/settings/tokens), sem escopos especiais. |

Não há `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` — o projeto não usa OAuth App do
GitHub. PATs de usuário são conectados pela própria interface (Configurações), não
via variável de ambiente.

## Provedor de IA

| Variável | Descrição |
|---|---|
| `AI_PROVIDER` | `claude` \| `openai` \| `gemini` \| `local` |
| `AI_API_KEY` | Chave do provedor escolhido |
| `AI_MODEL` | Nome do modelo (ex.: `claude-sonnet-5`, `gpt-4o`, `gemini-1.5-pro`, ou o nome carregado no seu servidor local) |
| `AI_BASE_URL` | Obrigatório só para `local`; opcional para os demais | 

Veja [`ai-providers.md`](ai-providers.md) para detalhes de cada provider.

## Frontend

| Variável | Descrição |
|---|---|
| `VITE_API_BASE_URL` | URL base da API consumida pelo frontend (padrão `http://localhost:8000/api/v1`) |
