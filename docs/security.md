# Segurança — detalhes técnicos

Para a política de divulgação de vulnerabilidades, veja [`SECURITY.md`](../SECURITY.md)
na raiz. Esta página documenta as decisões técnicas.

## Senhas

- Hash com `bcrypt` via `passlib` (`app/core/security.py::hash_password`/`verify_password`).
- Senha mínima de 8 caracteres, validada no schema `UserCreate`.
- Nunca logadas, nunca retornadas em nenhuma resposta da API.

## Tokens (JWT)

- Assinados com `JWT_SECRET` (HS256), expiram em `JWT_EXPIRE_MINUTES` (padrão 24h).
- Transportados via header `Authorization: Bearer <token>` — nunca em query string.
- Guardados no `localStorage` do frontend. **Trade-off consciente**: `localStorage` é
  acessível via XSS (diferente de um cookie `httpOnly`), mas evita a complexidade de
  CSRF que cookies exigem e é o padrão para APIs REST com login e-mail/senha. Mitigação
  principal: o frontend não injeta HTML não sanitizado (React escapa por padrão) e o
  `ReactMarkdown` usado para exibir o README gerado não executa scripts.
- Logout é stateless — não há blocklist de tokens revogados no servidor (ver Roadmap).

## Credenciais do GitHub (PAT)

- Nunca obrigatório — repositórios públicos funcionam sem nenhum token do usuário.
- Quando conectado, o PAT é criptografado em repouso com Fernet (`ENCRYPTION_KEY`)
  antes de ser salvo em `github_credentials.token_encrypted`.
- Descriptografado só em memória, no momento de fazer a chamada à GitHub API — nunca
  logado, nunca retornado pela API (o endpoint `GET /settings/github-token` retorna
  só `{connected: boolean}`).
- Validado contra a GitHub API (`GET /user`) antes de ser salvo, para rejeitar tokens
  inválidos cedo.

## Chaves de provedores de IA

- `AI_API_KEY` é uma variável de ambiente do servidor — nunca exposta ao frontend, nunca
  por usuário (todos os usuários compartilham a mesma chave/orçamento configurados
  pelo operador do servidor).

## Execução de código enviado pelo usuário

O CodeInsight AI **nunca executa** código de repositórios analisados. Todo o conteúdo
coletado (arquivos, commits, etc.) é tratado como texto puro — lido, incluído em um
prompt, e enviado ao provedor de IA como texto. Não há `eval`, `exec`, subprocess sobre
conteúdo do repositório, nem clonagem real do repositório (o conteúdo é buscado via
chamadas de leitura à GitHub Contents API).

## CORS

`allow_origins` restrito a `FRONTEND_URL` (não `*`). `allow_credentials=False` — não é
necessário, já que a autenticação não usa cookies.

## Rate limiting

`slowapi` limita `POST /analysis` (10/min/IP) e `POST /analysis/{id}/fix` (20/min/IP) —
os dois endpoints que disparam chamadas custosas (e potencialmente caras) ao provedor
de IA.

O limitador usa `key_style="endpoint"`. O padrão do `slowapi` é `"url"`, que põe o
**caminho concreto** no balde: numa rota com id variável isso dá um orçamento inteiro por
recurso. Medido antes da correção, 23 chamadas a `/fix` com ids diferentes não disparavam
o limite de 20.

**A contagem vive na memória do processo.** Com mais de uma instância, cada uma tem seu
próprio balde e o limite efetivo é multiplicado pelo número de réplicas. Corrigir exigiria
armazenamento compartilhado.

## Validação de entrada

Todo body de request é validado via Pydantic antes de chegar à lógica de negócio.
Referências de repositório (`owner/repo` ou URL) passam por uma regex estrita
(`github_service.resolve_repo_full_name`) antes de qualquer chamada à GitHub API.

## Isolamento entre usuários

Toda rota que acessa um recurso específico (repositório, análise) verifica
`resource.user_id == current_user.id` antes de retornar dados — implementado nos
métodos `get_owned*` de `app/repositories/`.
