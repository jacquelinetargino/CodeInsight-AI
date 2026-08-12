# API

Documentação interativa completa (OpenAPI/Swagger) disponível em `/docs` com o
backend rodando, e o schema bruto em `/openapi.json`. Esta página resume os endpoints
principais — os schemas de request/response completos estão em `app/schemas/`.

Todas as rotas usam o prefixo `/api/v1`. Rotas marcadas como **🔒** exigem o header
`Authorization: Bearer <token>`.

## Autenticação (`/auth`)

| Método | Rota | Descrição |
|---|---|---|
| POST | `/auth/register` | Cria conta (e-mail, senha, username). Retorna `{access_token, token_type, user}` |
| POST | `/auth/login` | Autentica. Retorna `{access_token, token_type, user}` |
| POST | `/auth/logout` | No-op (JWT é stateless) — só para simetria da API |
| 🔒 GET | `/auth/me` | Retorna o usuário autenticado |

## Configurações (`/settings`)

| Método | Rota | Descrição |
|---|---|---|
| 🔒 GET | `/settings/github-token` | `{connected: boolean}` |
| 🔒 PUT | `/settings/github-token` | Salva/atualiza o PAT do GitHub (validado contra a API antes de salvar) |
| 🔒 DELETE | `/settings/github-token` | Remove o PAT conectado |

## Repositórios (`/repos`)

| Método | Rota | Descrição |
|---|---|---|
| 🔒 GET | `/repos/github/mine` | Lista os repositórios do GitHub do usuário (requer PAT conectado) |
| 🔒 GET | `/repos` | Lista os repositórios adicionados pelo usuário |
| 🔒 POST | `/repos` | Adiciona um repositório — body `{repo: "owner/repo"}` (ou URL) |
| 🔒 GET | `/repos/{id}` | Detalhe de um repositório adicionado |
| 🔒 GET | `/repos/{id}/github-summary` | Linguagens, branches, commits, issues, PRs, contribuidores (ao vivo) |

## Análises (`/analysis`)

| Método | Rota | Descrição |
|---|---|---|
| 🔒 POST | `/analysis` | Dispara uma nova análise — body `{repository_id}`. Retorna `202` com status `queued` |
| 🔒 GET | `/analysis?repository_id=...` | Histórico de análises de um repositório |
| 🔒 GET | `/analysis/{id}` | Detalhe: status, score, resultados por dimensão, sugestões, correções, se tem README |
| 🔒 POST | `/analysis/{id}/readme` | Gera (ou regenera) o README a partir da análise |
| 🔒 GET | `/analysis/{id}/readme` | Retorna o README já gerado |
| 🔒 POST | `/analysis/{id}/fix` | Solicita correção de UM achado — body `{title, description, file_path?, line?}` |

## Relatórios (`/reports`)

| Método | Rota | Descrição |
|---|---|---|
| 🔒 GET | `/reports/{analysis_id}/pdf` | Baixa o relatório da análise em PDF |

## Dashboard (`/dashboard`)

| Método | Rota | Descrição |
|---|---|---|
| 🔒 GET | `/dashboard/summary` | Repositórios analisados, total de análises, score médio, achados totais, sugestões totais, histórico recente |

## Erros

Erros seguem o formato padrão do FastAPI: `{"detail": "mensagem"}`, com o status HTTP
apropriado (`400` validação/entrada inválida, `401` não autenticado, `403` proibido,
`404` não encontrado, `409` conflito, `502` falha ao consultar a GitHub API,
`429` rate limit excedido).

## Rate limiting

`POST /analysis` (10/min por IP) e `POST /analysis/{id}/fix` (20/min por IP) têm
limites mais baixos por disparar chamadas custosas ao provedor de IA.
