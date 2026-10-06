# Deployment

## Docker Compose (single host)

O jeito mais simples de rodar em produção é `docker-compose.yml` +
`docker-compose.prod.yml`, que troca o estágio `dev` das imagens pelo estágio `prod`
(build final, sem bind mounts, sem `--reload`) e publica o frontend via Nginx.

```bash
cp .env.example .env
# preencha com valores de produção: JWT_SECRET/ENCRYPTION_KEY fortes e únicos,
# AI_API_KEY, senha forte para o Postgres, APP_ENV=production,
# FRONTEND_URL/BACKEND_URL apontando para os domínios reais

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Isso sobe:

- `frontend` — Nginx servindo o build estático, porta `80`
- `backend` — uvicorn com múltiplos workers, porta `8000`
- `postgres`

A análise roda como `BackgroundTask` dentro do próprio backend — não há worker separado
nem broker para hospedar.

## Hospedagem gratuita (Vercel + Render + Neon)

Cada peça num plano gratuito:

| Peça | Serviço | Observação |
|---|---|---|
| Frontend | Vercel | SPA estática, sem expiração |
| Backend | Render (web service Free) | dorme após 15 min sem uso; o primeiro acesso leva ~50 s |
| Banco | Neon (Postgres Free) | não expira; scale-to-zero, acorda em 1–2 s |

Evite o Postgres gratuito do Render (expira em 30 dias e apaga os dados) e o do
Supabase (pausa o projeto após 7 dias sem uso).

### 1. Banco — Neon

1. Crie um projeto na mesma região que vai usar no Render (ex.: `AWS US East 2 (Ohio)`).
   Só o serviço "Postgres database" é necessário.
2. Em **Connect**, desligue **Connection pooling** (o pooler do Neon é PgBouncer, que
   não combina com os prepared statements do asyncpg) e copie a connection string.

Ela pode ser usada como vem (`postgresql://...?sslmode=require&channel_binding=require`):
o `config.py` troca o driver para `postgresql+asyncpg://` e traduz `sslmode` para o
`ssl=` que o asyncpg entende.

### 2. Backend — Render

**New → Web Service**, a partir do repositório:

| Campo | Valor |
|---|---|
| Root Directory | `backend` |
| Runtime | Docker |
| Region | a mesma do Neon |
| Instance Type | Free |
| Docker Command | `sh start.sh` |
| Health Check Path | `/health` |

O Docker Command do Render **não passa por shell** — encadear `alembic ... && uvicorn ...`
direto no campo falha com `not found`. Por isso existe o [`backend/start.sh`](../backend/start.sh):
roda `alembic upgrade head` e sobe o uvicorn na porta que o Render injeta em `$PORT`,
com 1 worker (a instância Free tem 512 MB).

Variáveis de ambiente:

| Chave | Valor |
|---|---|
| `DATABASE_URL` | connection string do Neon |
| `JWT_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` (precisa do pacote `cryptography` — use o Python do venv do backend) |
| `APP_ENV` | `production` |
| `FRONTEND_URL` | URL da Vercel (passo 3) — usada pelo CORS |

Opcional — recursos de IA (README, correções, sugestões) com a Groq gratuita:

| Chave | Valor |
|---|---|
| `AI_PROVIDER` | `groq` |
| `AI_API_KEY` | chave criada em console.groq.com — só aqui, nunca na Vercel |
| `AI_BASE_URL` | `https://api.groq.com/openai/v1` |
| `AI_MODEL` | `openai/gpt-oss-120b` |
| `AI_MAX_CONTEXT_CHARS` | `6000` (limite de 8k tokens/min do plano gratuito) |

Sem elas a análise funciona igual; os recursos de IA respondem 503. Detalhes em
[`ai-providers.md`](ai-providers.md#groq).

`ENCRYPTION_KEY` precisa ser uma chave Fernet (44 caracteres, termina em `=`); qualquer
outro valor derruba o app na importação com `Fernet key must be 32 url-safe
base64-encoded bytes`.

### 3. Frontend — Vercel

**Add New → Project**, importando o repositório:

| Campo | Valor |
|---|---|
| Root Directory | `frontend` |
| Framework / build / output | definidos pelo [`frontend/vercel.json`](../frontend/vercel.json) |
| `VITE_API_BASE_URL` | `https://<serviço>.onrender.com/api/v1` (Produção e Pré-visualização) |

O `vercel.json` também reescreve qualquer rota para `index.html`, para o React Router
funcionar ao recarregar a página. Variáveis `VITE_*` vão embutidas no JavaScript
público — nunca coloque segredos nelas.

Depois do primeiro deploy, copie a URL da Vercel para `FRONTEND_URL` no Render (aceita
várias origens separadas por vírgula).

### Conferindo

- `GET https://<serviço>.onrender.com/health` → `{"status":"ok",...}`
- `GET /` no backend responde 404 — esperado, não há rota na raiz.
- Preflight de CORS com `Origin: <url da Vercel>` deve devolver
  `access-control-allow-origin` com essa mesma origem.

## Checklist antes de ir para produção

- [ ] `APP_ENV=production`
- [ ] `JWT_SECRET` e `ENCRYPTION_KEY` gerados de novo (não reaproveite os de dev)
- [ ] `POSTGRES_PASSWORD` forte, diferente do padrão de desenvolvimento
- [ ] `FRONTEND_URL` aponta para o domínio real (usado pelo CORS)
- [ ] Um reverse proxy (Nginx, Caddy, Traefik) na frente com HTTPS — nem o backend
      nem o frontend fazem TLS termination sozinhos neste setup
- [ ] Backups do volume do Postgres (`postgres_data`) configurados
- [ ] `AI_API_KEY` é uma chave de produção com limites/orçamento configurados no
      provedor escolhido

## Migrations em produção

O `docker-compose.yml` já roda `alembic upgrade head` automaticamente antes de subir o
backend (ver `command` do serviço `backend`). Para rodar manualmente:

```bash
docker compose exec backend alembic upgrade head
```

## Escalando

- Não há serviço `worker`: a análise roda como `BackgroundTask` no processo do backend,
  então mais paralelismo vem de mais workers uvicorn ou mais réplicas do `backend`.
- `backend` já roda com múltiplos workers uvicorn no estágio `prod` (ver `Dockerfile`).
- O gargalo mais provável é o rate limit do provedor de IA e da GitHub API (se estiver
  usando muitas contas sem PAT/`GITHUB_TOKEN`), não o backend em si.

## Sem Docker

O backend é uma aplicação ASGI padrão (`uvicorn app.main:app`) e pode ser implantado
em qualquer plataforma que suporte Python 3.12 + PostgreSQL (FastAPI Cloud, Render,
Railway, Fly.io, um VPS com systemd, etc.). Nenhum serviço de fila é necessário. O frontend é uma SPA estática após `npm run build`
(pasta `dist/`) e pode ser servido por qualquer CDN/host estático.
