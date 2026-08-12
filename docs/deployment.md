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
- `worker` — Celery worker
- `postgres`, `redis`

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

- `worker` pode ser escalado horizontalmente (`docker compose up -d --scale worker=3`)
  para processar mais análises em paralelo — elas são independentes por análise.
- `backend` já roda com múltiplos workers uvicorn no estágio `prod` (ver `Dockerfile`).
- O gargalo mais provável é o rate limit do provedor de IA e da GitHub API (se estiver
  usando muitas contas sem PAT/`GITHUB_TOKEN`), não o backend em si.

## Sem Docker

O backend é uma aplicação ASGI padrão (`uvicorn app.main:app`) e pode ser implantado
em qualquer plataforma que suporte Python 3.12 + PostgreSQL + Redis (Render, Railway,
Fly.io, um VPS com systemd, etc.). O frontend é uma SPA estática após `npm run build`
(pasta `dist/`) e pode ser servido por qualquer CDN/host estático.
