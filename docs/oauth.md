# Login com Google e GitHub

> Publicando em produção? A ordem dos passos, o backup antes da migration, como
> reverter e o checklist de testes estão em [`auth-go-live.md`](auth-go-live.md).

Opcional. Cada provedor só aparece habilitado quando **as duas** variáveis dele estão
definidas no backend; sem elas, o botão fica desabilitado na tela de login e o resto da
aplicação não muda.

## Como funciona

Authorization Code com PKCE, inteiro no backend (`app/services/oauth_service.py`):

1. O botão "Continuar com …" navega para `GET /api/v1/auth/oauth/{google|github}/start`.
   O backend sorteia `state`, `code_verifier` (PKCE S256) e, no Google, `nonce`; guarda os
   três num cookie assinado, `HttpOnly`, `SameSite=Lax`, válido por 10 minutos e restrito
   ao caminho `/api/v1/auth/oauth`; e redireciona para o provedor.
2. O provedor devolve o navegador para `/api/v1/auth/oauth/{provider}/callback`. O backend
   confere o `state` contra o cookie (CSRF), troca o `code` por token usando o client
   secret **e** o verifier, e no Google valida o `id_token` (assinatura pelo JWKS, `iss`,
   `aud`, `exp`, `nonce`). No GitHub, busca o perfil e os e-mails verificados.
3. O backend redireciona para `{PUBLIC_FRONTEND_URL}/auth/callback#code=…` — um código de
   troca cifrado, de uso único, válido por 2 minutos, no **fragmento** da URL (não vai
   para servidor nenhum nem para o `Referer`).
4. O frontend troca esse código em `POST /api/v1/auth/oauth/exchange` e recebe o mesmo
   JWT do login por senha. A sessão, o armazenamento e o logout não mudam.

Nenhum destino de redirecionamento vem da requisição: o backend só redireciona para o
provedor oficial ou para `PUBLIC_FRONTEND_URL`. Nenhum token do provedor é guardado.

### Contas e vínculo

- A identidade é o **id estável** do provedor (`sub` do Google, id numérico do GitHub),
  guardado em `oauth_identities`. Trocar o e-mail ou o nome de usuário no provedor não
  muda a conta.
- Primeiro login sem conta → cria a conta (sem senha), **se** o provedor informar um
  e-mail verificado.
- Já existe conta com o mesmo e-mail → **não vincula sozinho**. A pessoa recebe a
  orientação de entrar com e-mail e senha e conectar o provedor em **Configurações →
  Contas conectadas**. Vincular exige estar logado na conta, e a troca final só é aceita
  pelo navegador com a sessão dessa mesma conta.
- Conta sem senha pode criar uma pelo "Esqueceu sua senha?".
- Não é possível desconectar o único meio de entrar na conta.

### Login com GitHub × análise de repositórios

São coisas separadas. O login pede só `read:user user:email` — nenhum acesso a
repositório — e o token é descartado logo após identificar a pessoa. Analisar
repositórios privados continua sendo pelo Personal Access Token colado em Configurações
(e o `GITHUB_TOKEN` do servidor continua sendo só para o rate limit). Por isso o app
OAuth do login tem variáveis próprias (`GITHUB_OAUTH_*`), diferentes de `GITHUB_TOKEN`.

## URLs de callback

São formadas por `BACKEND_URL` + `API_V1_PREFIX` + `/auth/oauth/{provider}/callback` e
precisam ser cadastradas **exatamente** assim no provedor:

| Ambiente | Google | GitHub |
|---|---|---|
| Produção | `https://codeinsight-ai-89se.onrender.com/api/v1/auth/oauth/google/callback` | `https://codeinsight-ai-89se.onrender.com/api/v1/auth/oauth/github/callback` |
| Local | `http://localhost:8000/api/v1/auth/oauth/google/callback` | `http://localhost:8000/api/v1/auth/oauth/github/callback` |

Para isso, `BACKEND_URL` no Render precisa ser `https://codeinsight-ai-89se.onrender.com`
(sem barra no final). Com outro valor, o provedor recusa o login com
`redirect_uri_mismatch`.

## Google Cloud Console

1. Acesse [console.cloud.google.com](https://console.cloud.google.com/) e crie (ou escolha)
   um projeto.
2. **APIs e serviços → Tela de consentimento OAuth** (ou *Google Auth Platform →
   Branding*): tipo **Externo**; preencha nome do app, e-mail de suporte e e-mail do
   desenvolvedor. Em **Público-alvo/Audience**, enquanto o app estiver em *Teste*, só os
   usuários listados em *Usuários de teste* conseguem entrar — publique o app quando for
   liberar para todos.
3. Escopos: só `openid`, `.../auth/userinfo.email` e `.../auth/userinfo.profile`. São
   escopos não sensíveis; não exigem verificação do Google.
4. **Credenciais → Criar credenciais → ID do cliente OAuth**:
   - Tipo de aplicativo: **Aplicativo da Web**
   - Origens JavaScript autorizadas: não são necessárias (o fluxo é todo no servidor)
   - URIs de redirecionamento autorizados: a URL de callback do Google da tabela acima
     (adicione também a local, se for testar na sua máquina)
5. Copie o **ID do cliente** e a **Chave secreta do cliente** para o Render:
   `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET`.

### Publicando o app (sair do modo Teste)

Em **Teste**, só entram as contas listadas em *Público-alvo → Usuários de teste* (até
100). Para liberar qualquer conta Google:

1. **Branding**: preencha *Página inicial do app* com
   `https://code-insight-ai-ashen.vercel.app` e *Link da Política de Privacidade* com
   `https://code-insight-ai-ashen.vercel.app/privacidade` (a página
   [`PrivacyPage.tsx`](../frontend/src/pages/PrivacyPage.tsx)). Em *Domínios
   autorizados*, `code-insight-ai-ashen.vercel.app` e `codeinsight-ai-89se.onrender.com`.
2. **Público-alvo → Publicar app → Confirmar**. Com só `openid`, `email` e `profile`
   (escopos não sensíveis), o Google não exige revisão para publicar.

Mudou o que o sistema coleta ou com quem compartilha? Atualize a política no mesmo PR.

## GitHub Developer Settings

1. Acesse [github.com/settings/developers](https://github.com/settings/developers) →
   **OAuth Apps → New OAuth App** (OAuth App, não GitHub App).
2. Preencha:
   - Application name: `CodeInsight AI`
   - Homepage URL: `https://code-insight-ai-ashen.vercel.app`
   - Authorization callback URL: a URL de callback do GitHub da tabela acima
   - **Enable Device Flow**: deixe desmarcado
3. **Register application → Generate a new client secret**.
4. Copie o **Client ID** e o **Client secret** para o Render:
   `GITHUB_OAUTH_CLIENT_ID` e `GITHUB_OAUTH_CLIENT_SECRET`.

Um OAuth App do GitHub aceita uma única callback URL. Para testar localmente, crie um
segundo OAuth App apontando para `http://localhost:8000/...` e use as credenciais dele
no `.env` local.

## Variáveis

| Variável | Onde | Descrição |
|---|---|---|
| `GOOGLE_CLIENT_ID` | Render | ID do cliente OAuth do Google |
| `GOOGLE_CLIENT_SECRET` | Render | Segredo do cliente do Google — **nunca** na Vercel |
| `GITHUB_OAUTH_CLIENT_ID` | Render | Client ID do OAuth App do GitHub |
| `GITHUB_OAUTH_CLIENT_SECRET` | Render | Client secret do GitHub — **nunca** na Vercel |
| `BACKEND_URL` | Render | URL pública do backend; forma a callback URL |
| `PUBLIC_FRONTEND_URL` | Render | URL do frontend para onde o login volta (padrão: primeira origem de `FRONTEND_URL`) |
| `OAUTH_STATE_MAX_AGE_SECONDS` | Render | Tempo máximo na tela do provedor (padrão `600`) |

Nada novo na Vercel: o frontend só conhece `VITE_API_BASE_URL`.

## Conferindo

- `GET /api/v1/auth/providers` → `{"google": true, "github": true, ...}` depois de
  configurar.
- "Continuar com Google" deve abrir a tela de escolha de conta do Google. Um erro
  `redirect_uri_mismatch` significa que a URL cadastrada não bate com `BACKEND_URL`.
- Cancelar na tela do provedor volta para o login com "Login cancelado".

### Client ID inválido desliga o provedor

Um `GOOGLE_CLIENT_ID` que não termina em `.apps.googleusercontent.com` (ou um
`GITHUB_OAUTH_CLIENT_ID` que seja URL ou tenha espaço) **desliga** aquele login:
`/auth/providers` responde `false`, o botão fica desabilitado e o backend avisa ao subir:

```
Login com Google DESABILITADO: o client ID configurado não é válido (...)
```

Foi o que aconteceu em produção: a variável recebeu a URL de callback no lugar do ID, e
todo login terminava em `invalid_client` na tela do Google.

### Lendo uma recusa do provedor nos logs

Quando a troca do código por token falha, o log do Render mostra **só o código de erro**
do provedor (nunca secret, código de autorização nem a descrição livre):

```
Troca do código OAuth recusada pelo provedor (google): invalid_client
```

| Código | Provedor | Significa |
|---|---|---|
| `invalid_client` | Google | client ID ou **client secret** errados |
| `incorrect_client_credentials` | GitHub | client ID ou **client secret** errados |
| `invalid_grant` | Google | código de autorização vencido, já usado ou inválido |
| `bad_verification_code` | GitHub | idem |
| `redirect_uri_mismatch` | ambos | a callback enviada não é a cadastrada |

Para conferir um secret **sem revelá-lo**, abra no navegador
`/api/v1/auth/oauth/{google|github}/start` e, em vez de entrar na conta, edite a URL de
volta para `/callback?code=teste&state=<o state da URL>`: o provedor recusa o código falso
com `invalid_grant`/`bad_verification_code` se o par id/secret estiver certo, ou com
`invalid_client`/`incorrect_client_credentials` se não estiver.
