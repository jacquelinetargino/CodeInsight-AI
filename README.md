# 🤖 CodeInsight AI

> AI-powered GitHub Repository Analyzer

<!--
  Badges de CI/Tests/Linguagem principal só renderizam depois que os workflows
  tiverem rodado pelo menos uma vez no repositório publicado — até lá ficam
  preparados (sem inventar status).
-->

[![CI](https://github.com/jacquelinetargino/CodeInsight-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/jacquelinetargino/CodeInsight-AI/actions/workflows/ci.yml)
[![Tests](https://github.com/jacquelinetargino/CodeInsight-AI/actions/workflows/tests.yml/badge.svg)](https://github.com/jacquelinetargino/CodeInsight-AI/actions/workflows/tests.yml)
[![Version](https://img.shields.io/badge/version-0.2.0-blue)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Top language](https://img.shields.io/github/languages/top/jacquelinetargino/CodeInsight-AI)](https://github.com/jacquelinetargino/CodeInsight-AI)

Uma plataforma open source para análise inteligente de repositórios do GitHub,
utilizando provedores de Inteligência Artificial configuráveis.

Avalia **segurança**, **qualidade de código**, **arquitetura**, **documentação**,
**testes** e **saúde do histórico Git** — com score de 0 a 100 por dimensão, achados
com severidade/arquivo/linha, correções de código sob demanda, geração automática de
README, histórico de análises, dashboard de agregados e exportação de relatórios em PDF.

---

## 🔐 API Keys & AI Credits

> **🔐 API Keys:** This project does not provide or share AI API credits. Users must configure their own API credentials.

CodeInsight AI is an open-source, self-hosted project.

Each user is responsible for configuring their own AI provider and API credentials.

The project does **NOT** provide shared AI credits and does **NOT** use the author's
personal API keys.

Users are responsible for any costs associated with the AI provider they choose.

Supported providers may include:

- Claude
- OpenAI
- Google Gemini
- Local AI models
- Other compatible providers

As credenciais devem ser configuradas através de variáveis de ambiente:

```env
AI_PROVIDER=
AI_API_KEY=
AI_MODEL=
```

Nunca coloque credenciais reais no README, em issues, ou em qualquer arquivo
versionado do repositório — use sempre o `.env` local (fora do controle de versão,
veja [`.gitignore`](.gitignore)).

---

## 📌 Project Information

**Repository:** CodeInsight-AI

**Type:** Open Source / Self-Hosted

**Purpose:** AI-powered GitHub Repository Analysis

**License:** [MIT](LICENSE)

---

## Funcionalidades

- **Autenticação própria**: cadastro/login por e-mail e senha (hash bcrypt), JWT, logout, rotas protegidas
- **Dashboard**: repositórios analisados, quantidade de análises, score médio, problemas encontrados, melhorias sugeridas, histórico recente
- **Integração com GitHub sem OAuth**: analise qualquer repositório público só com `owner/repo` ou a URL; conecte opcionalmente um Personal Access Token para repositórios privados e listagem automática dos seus repositórios
- **Dados ricos do repositório**: nome, descrição, linguagens, branches, commits, issues, pull requests, contribuidores e estrutura de arquivos
- **Análise por IA em 6 dimensões**: segurança, qualidade, arquitetura, documentação, testes e git — cada achado traz severidade, arquivo, linha (quando disponível), descrição e sugestão
- **Correções sob demanda**: peça uma correção para qualquer achado específico — a IA retorna código atual, código sugerido e a explicação; **nada é alterado no repositório automaticamente**
- **Geração automática de README.md** a partir da análise
- **Histórico completo** de todas as análises por repositório
- **Exportação de relatório em PDF**
- **Múltiplos provedores de IA** (Claude, OpenAI, Gemini ou um modelo local) trocáveis por variável de ambiente — veja [`docs/ai-providers.md`](docs/ai-providers.md)

## Tecnologias

| Camada | Tecnologias |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, TanStack Query, Zustand |
| Backend | Python, FastAPI, SQLAlchemy 2.0 (async), Alembic, Celery, Redis |
| Banco de dados | PostgreSQL |
| IA | Interface `AIProvider` própria — Claude (Anthropic), OpenAI, Gemini (Google) ou qualquer servidor local compatível com a API da OpenAI |
| Integração | GitHub REST API |
| Infra | Docker, Docker Compose, GitHub Actions (CI/CD) |

## Arquitetura

```
┌──────────────────┐      Bearer JWT       ┌───────────────────┐
│  React + TS SPA   │ <──────────────────> │   FastAPI backend   │
└──────────────────┘       REST             └─────────┬──────────┘
                                                        │
                    ┌────────────────────────────────────┼───────────────────────────┐
                    │                                     │                            │
             ┌──────▼──────┐                    ┌─────────▼─────────┐        ┌─────────▼─────────┐
             │ PostgreSQL   │                    │ Redis + Celery     │        │  AIProvider         │
             │ (usuários,   │                    │ worker (jobs de    │        │  (interface)         │
             │ análises)    │                    │ análise async)     │        │  ├─ ClaudeProvider    │
             └──────────────┘                    └─────────┬──────────┘        │  ├─ OpenAIProvider    │
                                                              │                   │  ├─ GeminiProvider    │
                                                    ┌─────────▼─────────┐        │  └─ LocalAIProvider   │
                                                    │   GitHub REST API   │        └───────────────────┘
                                                    │ (pública + PAT opc.) │
                                                    └─────────────────────┘
```

Documentação detalhada em [`docs/architecture.md`](docs/architecture.md).

## Como funciona

1. Você cria uma conta (e-mail/senha) e faz login — recebe um token JWT.
2. Informa `owner/repo` ou cola a URL de um repositório do GitHub (público — nenhum
   token necessário). Opcionalmente conecta um Personal Access Token em
   **Configurações** para repositórios privados.
3. Dispara uma análise: um worker Celery coleta o código, as linguagens, branches,
   commits, issues, PRs e contribuidores, e chama o provedor de IA configurado uma vez
   por dimensão (segurança, qualidade, arquitetura, documentação, testes, git).
4. Os resultados (score + achados com severidade/arquivo/linha/sugestão) ficam
   disponíveis no dashboard, junto com sugestões de melhoria priorizadas.
5. Para qualquer achado específico, você pode pedir uma correção — a IA responde com
   código atual, código sugerido e a explicação, sem tocar no seu repositório.
6. Você pode gerar um README, exportar tudo em PDF, e consultar o histórico completo
   a qualquer momento.

## Instalação

### Pré-requisitos

- Docker e Docker Compose
- Uma chave de API de pelo menos um provedor de IA suportado (Anthropic, OpenAI ou
  Google) — ou um servidor local compatível com a API da OpenAI (Ollama, LM Studio, etc.)
  **por sua própria conta** (veja "API Keys & AI Credits" acima)

```bash
git clone https://github.com/jacquelinetargino/CodeInsight-AI.git
cd CodeInsight-AI
cp .env.example .env
```

## Configuração das variáveis de ambiente

Edite o `.env` (nunca o versione — já está no `.gitignore`). Veja a referência
completa em [`docs/configuration.md`](docs/configuration.md). Resumo:

```env
# Segurança — gere com os comandos abaixo
JWT_SECRET=...
ENCRYPTION_KEY=...

# GitHub (opcional — só para elevar o rate limit em repos públicos)
GITHUB_TOKEN=

# Provedor de IA (obrigatório escolher um — sua própria chave, veja aviso acima)
AI_PROVIDER=claude   # claude | openai | gemini | local
AI_API_KEY=...
AI_MODEL=claude-sonnet-5
```

Gere os segredos:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"        # JWT_SECRET
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # ENCRYPTION_KEY
```

## Como executar

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend (Swagger): http://localhost:8000/docs

Passo a passo completo (incluindo rodar sem Docker) em [`docs/development.md`](docs/development.md).

## Docker

- `docker-compose.yml` — desenvolvimento (hot-reload, bind mounts)
- `docker-compose.prod.yml` — overrides de produção (imagens finais, sem bind mounts)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Detalhes em [`docs/deployment.md`](docs/deployment.md).

## API

Documentação interativa (Swagger) em `/docs` com o backend rodando. Referência dos
principais endpoints em [`docs/api.md`](docs/api.md).

## Testes

```bash
# backend
cd backend && pytest --cov=app

# frontend
cd frontend && npm run test
```

CI e execução automática dos testes em cada push/PR: veja
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) e
[`.github/workflows/tests.yml`](.github/workflows/tests.yml).

## Estrutura do projeto

```
CodeInsight-AI/
├── frontend/               # SPA React + TypeScript
├── backend/
│   └── app/
│       ├── api/routes/      # Endpoints REST
│       ├── core/             # Config, segurança, Celery
│       ├── models/           # Modelos SQLAlchemy
│       ├── schemas/          # Schemas Pydantic
│       ├── repositories/     # Acesso a dados (Repository pattern)
│       ├── services/         # Lógica de negócio
│       ├── ai/                # Interface AIProvider + providers + factory
│       ├── tasks/             # Tasks Celery
│       └── prompts/           # Templates de prompt por dimensão
├── docs/                     # Documentação detalhada
├── .github/workflows/         # CI/CD
└── docker-compose.yml
```

Veja também [backend/README.md](backend/README.md) e [frontend/README.md](frontend/README.md).

## Segurança

- Nenhuma credencial é versionada — tudo via variáveis de ambiente (`.env`, nunca commitado)
- Senhas com hash bcrypt; nunca armazenadas em texto puro
- PATs do GitHub sempre criptografados em repouso (Fernet)
- Autenticação via JWT Bearer; rotas protegidas por dependência do FastAPI
- Rate limiting nos endpoints mais sensíveis (criação de análise, correções)
- CORS restrito ao domínio do frontend
- Nenhum código enviado pelo usuário é executado — apenas analisado como texto pela IA

Política completa de divulgação de vulnerabilidades em [`SECURITY.md`](SECURITY.md) e
detalhes técnicos em [`docs/security.md`](docs/security.md).

## Roadmap

- [ ] Streaming do progresso da análise (WebSocket) em vez de polling
- [ ] Cache de análises recentes para o mesmo commit
- [ ] Suporte a monorepos (analisar subpastas específicas)
- [ ] Comentários automáticos em Pull Requests via GitHub App
- [ ] Blocklist de tokens JWT revogados (logout server-side)

## Contribuição

Contribuições são bem-vindas! Veja [`CONTRIBUTING.md`](CONTRIBUTING.md) para o guia
completo e [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) para as regras de convivência.

## Licença

Este projeto está licenciado sob a [MIT License](LICENSE).
