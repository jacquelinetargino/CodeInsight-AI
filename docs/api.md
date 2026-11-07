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
| POST | `/auth/forgot-password` | `{email}`. Envia o link de redefinição se a conta existir; responde `202` com a **mesma** mensagem em qualquer caso. `503` sem provedor de e-mail |
| POST | `/auth/reset-password` | `{token, new_password}`. Troca a senha; `400` se o link for inválido, vencido ou já usado |
| 🔒 GET | `/auth/me` | Retorna o usuário autenticado |
| GET | `/auth/providers` | `{google, github, password_reset}` — o que este servidor tem configurado |
| GET | `/auth/oauth/{google\|github}/start` | Navegação: inicia o login social (state + PKCE em cookie HttpOnly) e redireciona ao provedor. Com `?link_ticket=` inicia um vínculo |
| GET | `/auth/oauth/{google\|github}/callback` | Navegação: volta do provedor. Redireciona para `/auth/callback#code=…` no frontend, ou para `/login?oauth_error=…` (`cancelled`, `state_mismatch`, `provider_error`, `invalid_token`, `unavailable`, `link_expired`) |
| POST | `/auth/oauth/exchange` | `{code}`. Troca o código de uso único: `{intent: "login", access_token, user}` ou `{intent: "link", provider}`. `409` se já existe conta com o e-mail (não vincula sozinho) |
| 🔒 POST | `/auth/oauth/{provider}/link` | `{url}` para iniciar o vínculo da conta logada |
| 🔒 GET | `/auth/identities` | `{has_password, identities: [{provider, email, created_at}]}` |
| 🔒 DELETE | `/auth/identities/{provider}` | Desconecta; `409` se for o único meio de entrar |

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

Autenticação: `login` 10/min, `register` e `forgot-password` 5/min, `reset-password`
10/min, `oauth/*/start` e `oauth/*/callback` 20/min, `oauth/exchange` e
`oauth/*/link` 10/min — todos por IP. `forgot-password` também envia no máximo um
e-mail por conta a cada 60 s.
