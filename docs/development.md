# Guia de desenvolvimento

## Com Docker (recomendado)

```bash
cp .env.example .env
# preencha AI_API_KEY (e opcionalmente GITHUB_TOKEN) no .env
docker compose up --build
```

- Frontend: http://localhost:5173 (hot-reload)
- Backend: http://localhost:8000/docs (hot-reload via `--reload` do uvicorn)
- Postgres sobe junto. Não há worker separado: a análise roda como `BackgroundTask`

Rebuildar só um serviço depois de mudar dependências:

```bash
docker compose up --build backend
```

Ver logs de um serviço específico:

```bash
docker compose logs -f backend
```

## Sem Docker

Requer Python 3.12, Node 20 e PostgreSQL 16 instalados localmente.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp ../.env.example ../.env
# ajuste DATABASE_URL/REDIS_URL para localhost se não estiver usando os containers

alembic upgrade head
uvicorn app.main:app --reload
```

Não há worker separado para subir: a análise roda como `BackgroundTask` dentro do
próprio processo do backend.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Testando

```bash
# backend — precisa de um Postgres em DATABASE_URL (ver tests/conftest.py)
cd backend && pytest --cov=app -v

# frontend
cd frontend && npm run test
```

Os testes de backend não fazem nenhuma chamada real a provedores de IA ou à GitHub
API — tudo é mockado (`ScriptedAIProvider`, `monkeypatch` no `github_service`).

## Lint

```bash
cd backend && ruff check . && black --check . && mypy app
cd frontend && npm run lint
```

## Migrations

Depois de alterar um modelo em `backend/app/models/`:

```bash
cd backend
alembic revision --autogenerate -m "descrição da mudança"
alembic upgrade head
```

Revise sempre a migration gerada antes de commitar — o autogenerate nem sempre
detecta tudo corretamente (ex.: renomeação de coluna vira drop+add por padrão).

**Esquecer a migration não passa mais despercebido.**
`tests/test_migrations.py::test_o_schema_das_migrations_e_o_dos_modelos` roda a
cadeia inteira num schema descartável e compara o resultado com
`Base.metadata`. Se as duas descrições divergirem, ele falha listando cada
alteração que faltou virar migration.

Antes desse teste as duas coisas não se falavam: a suíte cria as tabelas com
`Base.metadata.create_all()` e a produção roda `alembic upgrade head`.
Acrescentar uma coluna a um modelo sem migration nenhuma passava na suíte
inteira e no CI — e a produção simplesmente não teria a coluna.

**Nunca edite uma migration já aplicada.** Se o teste acusar divergência, a
correção é uma migration nova, como foi a `0003`.

## Adicionando um novo endpoint

1. Modelo (se necessário) em `app/models/` + migration.
2. Schema Pydantic em `app/schemas/`.
3. Método de acesso a dados em `app/repositories/` (se envolver consultas novas).
4. Lógica de negócio em `app/services/` (se houver alguma).
5. Rota em `app/api/routes/`, registrada em `app/main.py`.
6. Teste de integração em `backend/tests/`.
7. No frontend: tipo em `src/types/`, chamada em `src/lib/api.ts`, hook em `src/hooks/`.
