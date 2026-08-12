# Changelog

Todas as mudanças notáveis deste projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

## [0.2.0] — Refatoração para arquitetura multi-provedor

### Adicionado
- Autenticação própria por e-mail/senha (cadastro, login, logout, JWT Bearer),
  substituindo o login via GitHub OAuth.
- Camada de abstração `AIProvider` (`app/ai/`), com implementações para Claude, OpenAI,
  Gemini e qualquer servidor local compatível com a API da OpenAI, selecionável via
  `AI_PROVIDER`/`AI_API_KEY`/`AI_MODEL`/`AI_BASE_URL`.
- Acesso ao GitHub sem OAuth App: repositórios adicionados por `owner/repo` ou URL;
  Personal Access Token opcional (criptografado) para repositórios privados.
- Dados ricos do repositório: linguagens, branches, commits, issues, pull requests e
  contribuidores (buscados ao vivo).
- Duas novas dimensões de análise: **Testes** e **Git** (6 dimensões no total).
- Achados agora incluem `line` (linha) e `suggestion` (sugestão objetiva).
- Correção sob demanda por achado (`POST /analysis/{id}/fix`): retorna código
  atual/sugerido/explicação — nunca aplica a mudança automaticamente.
- Dashboard de agregados (`GET /dashboard/summary`): repositórios analisados, total de
  análises, score médio, achados totais, sugestões totais, histórico recente.
- Camada `app/repositories/` (Repository pattern) para acesso a dados.
- Documentação completa em `docs/`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `SECURITY.md`.

### Alterado
- Autenticação passou de cookie de sessão para JWT via header `Authorization: Bearer`.
- `GithubConnection` renomeado para `GithubCredential` (agora opcional, PAT em vez de OAuth).
- Pesos das dimensões recalibrados para as 6 dimensões atuais.

### Removido
- Fluxo de login via GitHub OAuth2 (`/auth/github/login`, `/auth/github/callback`).
- Dependência direta do SDK da Anthropic fora da camada `app/ai/`.

## [0.1.0] — MVP inicial

### Adicionado
- Login via GitHub OAuth2.
- Integração com a GitHub API para listar e importar repositórios.
- Motor de análise com 4 dimensões (segurança, qualidade, arquitetura, documentação)
  via Claude, com score agregado ponderado.
- Geração automática de README e sugestões de melhoria priorizadas.
- Histórico de análises e exportação de relatório em PDF.
- Estrutura Docker (backend, frontend, worker, Postgres, Redis) e CI no GitHub Actions.
