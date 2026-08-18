# Segurança — detalhes técnicos

Para a política de divulgação de vulnerabilidades, veja [`SECURITY.md`](../SECURITY.md)
na raiz. Esta página documenta as decisões técnicas.

## Senhas

- Hash com `bcrypt` via `passlib` (`app/core/security.py::hash_password`/`verify_password`).
- Senha mínima de 8 caracteres, validada no schema `UserCreate`.
- **Máximo de 72 bytes**, também no `UserCreate`. O bcrypt só considera os primeiros
  72 bytes e descarta o resto sem avisar: medido, `"A"*72 + "sufixo-ignorado"` casa com
  o hash de `"A"*72`. O teto anterior era de 128 caracteres, ou seja, prometia uma
  força que o algoritmo não entregava. A contagem é em **bytes**, não em caracteres —
  40 caracteres acentuados passam de 72 bytes em UTF-8.
  O limite vale só no cadastro: contas criadas antes dele continuam entrando, porque a
  conferência trunca do mesmo jeito que o cadastro truncou.
- Nunca logadas, nunca retornadas em nenhuma resposta da API.
- **O tempo de resposta do login não distingue e-mail cadastrado de desconhecido.** A
  conferência do bcrypt roda nos dois casos, contra um hash descartável quando o e-mail
  não existe (`security.dummy_password_hash`). Sem isso o `or` curto-circuitava e o
  login virava um oráculo de "esta pessoa tem conta aqui": medido, 213 ms para e-mail
  cadastrado contra 0,9 ms para desconhecido.
  Isso trata só o canal de tempo. `POST /auth/register` continua respondendo 409 para
  e-mail já cadastrado, o que também identifica quem tem conta — mudar isso exigiria
  confirmação por e-mail, que o projeto não tem.

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

`slowapi` limita:

| Rota | Limite | Por que |
| --- | --- | --- |
| `POST /analysis` | 10/min/IP | dispara chamadas custosas ao provedor de IA |
| `POST /analysis/{id}/fix` | 20/min/IP | idem, uma correção por achado |
| `POST /auth/login` | 10/min/IP | adivinhação de senha |
| `POST /auth/register` | 5/min/IP | criação de contas em massa |

O limite do login não é orçamento de custo. Antes dele, 60 tentativas seguidas contra a
mesma conta responderam 401 e nenhuma 429 — adivinhar senha era só uma questão de tempo.
Cada tentativa contra uma conta existente também custa ~210 ms de CPU do servidor (o
bcrypt), então a rota servia de alavanca de exaustão sem exigir credencial nenhuma.

**O que o limite do login não resolve:** a chave é o IP. Um atacante distribuído continua
tendo 10 tentativas por minuto *por endereço*, e não há bloqueio por conta — isso exigiria
contagem compartilhada, pela mesma razão descrita no parágrafo da memória do processo.

O limitador usa `key_style="endpoint"`. O padrão do `slowapi` é `"url"`, que põe o
**caminho concreto** no balde: numa rota com id variável isso dá um orçamento inteiro por
recurso. Medido antes da correção, 23 chamadas a `/fix` com ids diferentes não disparavam
o limite de 20.

**A contagem vive na memória do processo.** Com mais de uma instância, cada uma tem seu
próprio balde e o limite efetivo é multiplicado pelo número de réplicas. Corrigir exigiria
armazenamento compartilhado.

## Validação de entrada

Todo body de request é validado via Pydantic antes de chegar à lógica de negócio.

**Tudo que vira segmento de caminho de uma URL da GitHub API é validado antes.** É a
mesma classe de defeito duas vezes: a requisição sai com `Authorization: Bearer` — o PAT
do usuário ou, quando ele não conectou nenhum, o `GITHUB_TOKEN` do servidor — e o httpx
normaliza `..` no momento em que constrói a URL, então um segmento a mais troca o
endpoint chamado sem que o código pareça errado.

| entrada | validada por | o que escapava |
| --- | --- | --- |
| referência do repositório | `resolve_repo_full_name` (regex) | `../user` alcançava `/user` |
| `file_path` de `POST /analysis/{id}/fix` | `_validate_repo_file_path` | `../../../vitima/privado/contents/.env` lia outro repositório |

O caso do `file_path` era o mais grave dos dois: o conteúdo volta em base64, é
decodificado e segue para o provedor de IA como contexto da correção, que o usuário lê.
Com `GITHUB_TOKEN` configurado no servidor, qualquer usuário autenticado lia qualquer
repositório que aquele token alcança, inclusive privado.

Abaixo das duas validações há uma rede geral em `github_service._get`: ele recusa
qualquer caminho que a montagem da URL reescreva. Ela existe para a chamada que alguém
acrescentar amanhã sem lembrar deste problema — que foi exatamente como o segundo caso
apareceu depois do primeiro ter sido corrigido.

## Download do tarball

O tarball da GitHub API redireciona para outro host, e o download segue os saltos
manualmente (o httpx roda com `follow_redirects=False` ali). Cada salto passa por
`_assert_destino_permitido`, que confere **host e esquema**:

- host em `{api.github.com, codeload.github.com, objects.githubusercontent.com}`;
- esquema `https`, sempre.

A checagem de esquema foi acrescentada depois. Só o host era conferido, e um
redirecionamento para `http://codeload.github.com/...` passava — medido, o
`Authorization: Bearer` ia junto, em texto claro. Quem controla esse redirecionamento é
o próprio GitHub, então não era um buraco alcançável por um usuário da aplicação; era a
checagem que faltava para a garantia ser a que o módulo diz ter.

**O header de credencial é reenviado em todos os saltos, de propósito, e isso não
mudou.** O httpx, quando segue redirecionamento sozinho, remove o `Authorization` ao
trocar de origem — o laço manual daqui não remove. Manter o comportamento é uma decisão
com razão declarada: os três hosts permitidos são do GitHub, e não dá para verificar sem
um repositório privado de teste se o `codeload` precisa do token para entregar o tarball
de um repositório privado. Remover o header sem essa verificação arriscaria quebrar a
análise de repositório privado para ganhar pouco. Fica registrado como pendência com
critério: **medir primeiro, mudar depois.**

O caminho da URL também é conferido (`_assert_caminho_nao_reescrito`), pela mesma razão
descrita em "Validação de entrada" — é o terceiro lugar em que `..` num segmento trocaria
o endpoint chamado.

## Mensagens de erro

`Analysis.error_message` é devolvido por `GET /analysis/{id}` e mostrado na página da
análise. Ele só recebe mensagem **escrita para ser lida** — na prática, exceção que
herda de `app.core.errors.FalhaVisivelAoUsuario` (aquisição, tamanho, timeout) e recusa
da GitHub API, esta traduzida por status. Qualquer outra exceção vira um texto genérico,
e o detalhe inteiro fica no log via `logger.exception`.

Antes disso o campo recebia `str(exc)` de qualquer exceção. Medido:

| exceção | o que chegava à tela |
| --- | --- |
| `FileNotFoundError` | `[Errno 2] ... 'C:\Users\<conta>\AppData\Local\Temp\codeinsight-a1b2c3\src\repo\x.py'` |
| `KeyError` | `'chave_que_nao_existe'` |
| `HTTPStatusError` | `Client error '404 Not Found' for url 'https://api.github.com/repos/...'` |

Dois problemas juntos: o caminho do diretório temporário e a conta que roda o servidor
saíam para quem pedisse a análise, e — como mensagem de erro de sistema de arquivos
carrega o nome do arquivo — o **repositório analisado**, que é conteúdo não confiável,
escolhia parte do texto exibido. Não chegava a ser XSS (o React escapa na renderização),
mas era conteúdo de terceiro alcançando a interface por um caminho não desenhado.

## Isolamento entre usuários

Toda rota que acessa um recurso específico (repositório, análise) verifica
`resource.user_id == current_user.id` antes de retornar dados — implementado nos
métodos `get_owned*` de `app/repositories/`.
