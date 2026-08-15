# CodeInsight AI — Backend

API em FastAPI (async) responsável por autenticação (e-mail/senha + JWT), integração
com a GitHub API (sem OAuth — repositórios públicos ou PAT opcional), orquestração das
análises via Celery, e chamadas ao provedor de IA configurado (Claude, OpenAI, Gemini
ou um modelo local) através da interface `AIProvider`.

## Rodando fora do Docker

Requer PostgreSQL e Redis rodando localmente (ou apontar `DATABASE_URL`/`REDIS_URL`
para instâncias já existentes).

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp ../.env.example ../.env  # se ainda não existir na raiz
alembic upgrade head
uvicorn app.main:app --reload
```

Para rodar o worker de análises:

```bash
celery -A app.core.celery_app worker --loglevel=info
```

## Estrutura

```
app/
├── api/routes/     # Endpoints REST (auth, repos, analysis, reports, settings, dashboard)
├── core/           # Config, segurança (JWT/bcrypt/Fernet), engine do banco, Celery
├── models/         # Modelos SQLAlchemy
├── schemas/        # Schemas Pydantic (request/response)
├── repositories/   # Acesso a dados (Repository pattern) — usado por services/rotas
├── services/       # Lógica de negócio (GitHub, análise, PDF, dashboard)
├── ai/             # Interface AIProvider + providers (claude/openai/gemini/local) + factory
├── tasks/          # Tasks assíncronas (Celery) do pipeline de análise
├── prompts/        # Templates de prompt por dimensão de análise
└── templates/      # Template HTML do relatório em PDF
```

## Testes e lint

```bash
pytest --cov=app
ruff check .
black --check .
mypy app
```

Os testes usam um PostgreSQL de teste (`DATABASE_URL` aponta para
`codeinsight_test` por padrão em `tests/conftest.py`) e um `ScriptedAIProvider` falso
— nenhuma chamada real a provedores de IA ou à GitHub API acontece nos testes.

### Banco de testes

A suíte recria e apaga todas as tabelas entre os testes, então precisa de um alvo
descartável. Há dois modos:

**Banco dedicado (padrão, usado pelo CI).** Crie um banco só para testes e aponte
`DATABASE_URL` para ele:

```bash
createdb codeinsight_test
export DATABASE_URL=postgresql+asyncpg://USUARIO:SENHA@localhost:5432/codeinsight_test
pytest
```

**Schema isolado (alternativa local).** Criar um banco exige a permissão `CREATEDB`,
que nem todo ambiente concede. Nesse caso a suíte pode viver num schema separado
dentro de um banco existente, sem tocar em `public`:

```bash
export DATABASE_URL=postgresql+asyncpg://USUARIO:SENHA@localhost:5432/codeinsight
export TEST_DB_SCHEMA=codeinsight_test
pytest
```

O schema é criado automaticamente na primeira execução. Este modo é **exclusivo de
desenvolvimento local** — o CI continua usando um banco dedicado.

Em ambos os modos o `conftest` recusa rodar se detectar risco de destruir dados
reais: host remoto, `TEST_DB_SCHEMA=public`, nome de schema inválido, ou um banco
sem "test" no nome quando não há schema isolado.

## Migrations

```bash
alembic revision --autogenerate -m "descrição"
alembic upgrade head
```
