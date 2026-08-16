# CodeInsight AI — Backend

API em FastAPI (async) responsável por autenticação (e-mail/senha + JWT), integração
com a GitHub API (sem OAuth — repositórios públicos ou PAT opcional) e execução do
**CodeInsight Engine**, o motor de análise estática que vive em `app/engine/`.

O motor não usa IA e não exige chave de API. A interface `AIProvider` é **opcional** e
só habilita sugestões, correções, geração de README e explicações.

## Rodando fora do Docker

Requer PostgreSQL rodando localmente (ou apontar `DATABASE_URL` para uma instância já
existente).

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp ../.env.example ../.env  # se ainda não existir na raiz
alembic upgrade head
uvicorn app.main:app --reload
```

## Estrutura

```
app/
├── engine/         # CodeInsight Engine — a análise em si (sem banco, sem HTTP, sem IA)
│   ├── acquisition.py  # Download e extração segura do tarball
│   ├── scanner.py      # Inventário de arquivos
│   ├── analyzers/      # Um por dimensão (security, quality, dependency,
│   │                   #   architecture, testing, configuration, documentation, git)
│   ├── rules/          # Detectores (AST, regex) e catálogos de regras
│   ├── scoring.py      # Score por dimensão, score geral e nível de risco
│   └── pipeline.py     # Orquestração: adquire → inventaria → analisa → pontua
├── api/routes/     # Endpoints REST (auth, repos, analysis, reports, settings, dashboard)
├── core/           # Config, segurança (JWT/bcrypt/Fernet), engine do banco
├── models/         # Modelos SQLAlchemy
├── schemas/        # Schemas Pydantic (request/response)
├── repositories/   # Acesso a dados (Repository pattern) — usado por services/rotas
├── services/       # Lógica de negócio (GitHub, persistência da análise, PDF, dashboard)
├── ai/             # Interface AIProvider + providers + factory (OPCIONAL)
├── tasks/          # Execução em segundo plano do pipeline de análise
├── prompts/        # Templates de prompt por dimensão (caminho de IA)
└── templates/      # Template HTML do relatório em PDF
```

## Testes e lint

```bash
pytest --cov=app
ruff check .
black --check .
mypy app
```

Os testes usam um PostgreSQL de teste (`DATABASE_URL` aponta para `codeinsight_test`
por padrão em `tests/conftest.py`). **Nenhuma variável de IA é definida na suíte, de
propósito**: o estado padrão é "sem provedor configurado", que é o mesmo de uma
instalação normal — se algum caminho voltasse a exigir IA, os testes falhariam. Testes
que precisam de um provedor declaram isso explicitamente com um `ScriptedAIProvider`
falso. Nenhuma chamada real a provedor de IA ou à GitHub API acontece nos testes.

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
