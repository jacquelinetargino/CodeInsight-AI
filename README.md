# 🤖 CodeInsight AI

> Análise estática de repositórios do GitHub — sem chave de API, sem crédito, sem serviço externo

<!--
  Badges de CI/Tests/Linguagem principal só renderizam depois que os workflows
  tiverem rodado pelo menos uma vez no repositório publicado — até lá ficam
  preparados (sem inventar status).
-->

[![CI](https://github.com/jacquelinetargino/CodeInsight-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/jacquelinetargino/CodeInsight-AI/actions/workflows/ci.yml)
[![Tests](https://github.com/jacquelinetargino/CodeInsight-AI/actions/workflows/tests.yml/badge.svg)](https://github.com/jacquelinetargino/CodeInsight-AI/actions/workflows/tests.yml)
[![Version](https://img.shields.io/badge/version-0.3.3-blue)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Top language](https://img.shields.io/github/languages/top/jacquelinetargino/CodeInsight-AI)](https://github.com/jacquelinetargino/CodeInsight-AI)

Uma plataforma open source para análise de repositórios do GitHub. O núcleo é o
**CodeInsight Engine**: um motor de análise estática próprio, escrito em Python, que
roda inteiramente no seu servidor.

Avalia **segurança**, **qualidade de código**, **dependências**, **arquitetura**,
**testes**, **configuração**, **documentação** e **saúde do histórico Git** — com score
de 0 a 100 por dimensão, nível de risco do repositório, e achados com regra, severidade,
arquivo, linha, evidência e confiança.

**Você não precisa de chave de API, crédito em serviço de IA nem conexão com nenhum
provedor externo para analisar um repositório.** A IA é opcional e serve apenas para
enriquecer o resultado — veja [A IA é opcional](#a-ia-é-opcional).

---

## A IA é opcional

A análise é feita pelo **CodeInsight Engine**, que roda no seu servidor e **não usa IA**.
Instalar o projeto e analisar repositórios não exige nenhuma chave, crédito ou conta em
serviço de terceiros.

Um provedor de IA, se configurado, acrescenta quatro recursos — e só eles:

| Recurso | Precisa de IA? |
|---|---|
| Análise das oito dimensões, score e nível de risco | Não |
| Achados com regra, severidade, arquivo, linha e evidência | Não |
| Relatório em PDF, histórico, dashboard | Não |
| Sugestões priorizadas de melhoria | Sim |
| Correção de código sob demanda | Sim |
| Geração automática de README | Sim |
| Explicação em linguagem natural de um achado | Sim |

Sem provedor configurado, esses quatro simplesmente não aparecem. Nada falha, nada fica
pela metade, e o score não muda.

### Se você quiser habilitá-los

O projeto **não fornece créditos de IA** e **não usa a chave de ninguém**: cada pessoa
configura o próprio provedor e responde pelos custos dele. São suportados Claude
(Anthropic), OpenAI, Google Gemini e qualquer servidor local compatível com a API da
OpenAI (Ollama, LM Studio).

```env
AI_PROVIDER=claude   # claude | openai | gemini | local
AI_API_KEY=...
AI_MODEL=claude-sonnet-5
```

Nunca coloque credenciais reais no README, em issues, ou em qualquer arquivo versionado
— use sempre o `.env` local (fora do controle de versão, veja [`.gitignore`](.gitignore)).

---

## 📌 Project Information

**Repository:** CodeInsight-AI

**Type:** Open Source / Self-Hosted

**Purpose:** Static analysis of GitHub repositories (self-hosted engine, optional AI)

**License:** [MIT](LICENSE)

---

## Funcionalidades

- **Autenticação própria**: cadastro/login por e-mail e senha (hash bcrypt), JWT, logout, rotas protegidas
- **Dashboard**: repositórios analisados, quantidade de análises, score médio, problemas encontrados, melhorias sugeridas, histórico recente
- **Integração com GitHub sem OAuth**: analise qualquer repositório público só com `owner/repo` ou a URL; conecte opcionalmente um Personal Access Token para repositórios privados e listagem automática dos seus repositórios
- **Dados ricos do repositório**: nome, descrição, linguagens, branches, commits, issues, pull requests, contribuidores e estrutura de arquivos
- **Análise estática em 8 dimensões**, sem IA: segurança, qualidade, dependências, arquitetura, testes, configuração, documentação e git
- **Achados rastreáveis**: cada um traz identificador de regra, severidade, arquivo, linha, evidência, **confiança** e o **método de detecção** — árvore sintática, busca textual ou metadados. Boa parte da análise é heurística, e a dúvida é declarada em vez de escondida
- **Score e nível de risco**: 0 a 100 por dimensão e um veredito agregado. Dimensão não avaliada recebe "não avaliado", nunca nota cheia
- **Tema claro, escuro ou automático**, acompanhando a preferência do sistema
- **Histórico completo** de todas as análises por repositório
- **Exportação de relatório em PDF**
- *(opcional, com IA)* **Sugestões priorizadas**, **correções sob demanda** (**nada é alterado no repositório automaticamente**), **geração de README** e **explicação de achados** — veja [`docs/ai-providers.md`](docs/ai-providers.md)

## Tecnologias

| Camada | Tecnologias |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, TanStack Query, Zustand |
| Backend | Python, FastAPI, SQLAlchemy 2.0 (async), Alembic |
| Motor de análise | CodeInsight Engine — `ast` da biblioteca padrão para Python, análise textual para JS/TS. Sem dependência externa de análise |
| Banco de dados | PostgreSQL |
| IA (opcional) | Interface `AIProvider` própria — Claude (Anthropic), OpenAI, Gemini (Google) ou qualquer servidor local compatível com a API da OpenAI |
| Integração | GitHub REST API |
| Infra | Docker, Docker Compose, GitHub Actions (CI/CD) |

## Arquitetura

```
┌───────────────────┐     Bearer JWT      ┌──────────────────────┐
│   React + TS SPA   │ <─────────────────> │   FastAPI backend     │
└───────────────────┘        REST          └──────────┬───────────┘
                                                      │
                 ┌────────────────────────────────────┼────────────────────────┐
                 │                                    │                        │
       ┌─────────▼─────────┐         ┌────────────────▼───────────────┐        │
       │    PostgreSQL      │         │      CodeInsight Engine         │        │
       │ (usuários,         │         │   (BackgroundTask, sem IA)      │        │
       │  análises)         │         │                                 │        │
       └────────────────────┘         │  acquisition → scanner          │        │
                                      │      → 8 analyzers → scoring    │        │
                                      └────────────────┬────────────────┘        │
                                                       │                         │
                                        ┌──────────────▼─────────┐   ┌───────────▼──────────┐
                                        │    GitHub REST API      │   │  AIProvider           │
                                        │ (tarball + metadados;   │   │  OPCIONAL             │
                                        │  pública + PAT opc.)    │   │  só enriquecimento    │
                                        └─────────────────────────┘   └───────────────────────┘
```

O caminho da análise não passa pelo `AIProvider`. Ele fica ao lado, e só é acionado
depois que a análise já terminou e foi gravada.

Documentação detalhada em [`docs/architecture.md`](docs/architecture.md).

## Como funciona

1. Você cria uma conta (e-mail/senha) e faz login — recebe um token JWT.
2. Informa `owner/repo` ou cola a URL de um repositório do GitHub (público — nenhum
   token necessário). Opcionalmente conecta um Personal Access Token em
   **Configurações** para repositórios privados.
3. Dispara uma análise. O motor baixa o tarball do repositório para um diretório
   temporário, inventaria os arquivos e roda os oito analyzers sobre eles. **Nada do
   repositório é executado** — só lido: a análise de Python usa a AST da biblioteca
   padrão, e a de JS/TS é textual. O diretório temporário é apagado ao final, inclusive
   em erro ou timeout.
4. Os resultados ficam disponíveis no dashboard: score por dimensão, nível de risco e
   cada achado com regra, severidade, arquivo, linha, evidência e confiança.
5. Você pode exportar tudo em PDF e consultar o histórico completo a qualquer momento.
6. *(opcional)* Se houver provedor de IA configurado, sugestões priorizadas são geradas
   a partir dos achados, e você pode pedir a correção de um achado específico ou a
   geração de um README. Nada disso altera o seu repositório.

## Instalação

### Pré-requisitos

- Docker e Docker Compose

É só isso. Nenhuma chave de API é necessária para analisar repositórios.

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

# Provedor de IA (OPCIONAL — deixe em branco e a análise funciona igual;
# habilita apenas sugestões, correções, README e explicações)
AI_PROVIDER=
AI_API_KEY=
AI_MODEL=
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
│       ├── engine/           # CodeInsight Engine — o motor de análise
│       │   ├── acquisition.py # Download e extração segura do tarball
│       │   ├── scanner.py     # Inventário de arquivos
│       │   ├── analyzers/     # Um por dimensão (8)
│       │   ├── rules/         # Detectores e catálogos de regras
│       │   ├── scoring.py     # Score por dimensão e nível de risco
│       │   └── pipeline.py    # Orquestração da análise
│       ├── api/routes/       # Endpoints REST
│       ├── core/              # Config, segurança, banco
│       ├── models/            # Modelos SQLAlchemy
│       ├── schemas/           # Schemas Pydantic
│       ├── repositories/      # Acesso a dados (Repository pattern)
│       ├── services/          # Lógica de negócio
│       ├── ai/                 # Interface AIProvider (OPCIONAL) + factory
│       ├── tasks/              # Execução em segundo plano
│       └── prompts/            # Templates de prompt (caminho de IA)
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
- Rate limiting nos endpoints mais sensíveis (criação de análise, correções) e nos dois
  abertos ao público (login 10/min/IP, cadastro 5/min/IP)
- O login não vaza quem tem conta: o tempo de resposta é o mesmo para e-mail cadastrado
  e desconhecido
- CORS restrito ao domínio do frontend
- **Nenhum código do repositório analisado é executado.** Não há `subprocess`, `shell`,
  `eval`, `exec`, importação dinâmica, execução de gerenciador de pacotes, script de
  instalação ou Makefile. A análise de Python usa a AST da biblioteca padrão, que faz
  parsing sem avaliar; a de JS/TS é textual
- O tarball baixado é tratado como hostil: limite de bytes durante o download, recusa de
  caminhos que escapam do destino, symlinks descartados, teto de arquivos e de tamanho
  descomprimido, e allowlist de hosts **e de esquema** (só https) para evitar SSRF e
  evitar que a credencial do download saia em texto claro
- Conteúdo de arquivo sensível nunca é lido nem reportado: o achado traz o caminho, que é
  o que se precisa para agir
- Evidência de credencial já vem mascarada do detector — o valor real não chega ao banco

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
