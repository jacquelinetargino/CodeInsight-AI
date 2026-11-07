# Autenticação em produção — guia e checklist

Roteiro para publicar a recuperação de senha e o login com Google e GitHub no ambiente
atual (frontend na Vercel, backend no Render, banco no Neon). O funcionamento de cada
peça está em [`oauth.md`](oauth.md) e [`configuration.md`](configuration.md); aqui fica
só o que fazer, em que ordem, e como conferir.

> Digite os valores secretos direto no painel do Render. Não cole chaves, secrets ou
> senhas em chat, issue, PR ou commit.

## URLs de produção

| O quê | URL |
|---|---|
| Frontend (Vercel) | `https://code-insight-ai-ashen.vercel.app` |
| Backend (Render) | `https://codeinsight-ai-89se.onrender.com` |
| Callback do Google | `https://codeinsight-ai-89se.onrender.com/api/v1/auth/oauth/google/callback` |
| Callback do GitHub | `https://codeinsight-ai-89se.onrender.com/api/v1/auth/oauth/github/callback` |
| Volta do login no frontend | `https://code-insight-ai-ashen.vercel.app/auth/callback` (não precisa ser cadastrada em lugar nenhum) |
| Link do e-mail de redefinição | `https://code-insight-ai-ashen.vercel.app/reset-password?token=…` |

Os callbacks são formados por `BACKEND_URL` + `/api/v1/auth/oauth/{provider}/callback`
e precisam ser cadastrados nos provedores exatamente assim. Se o domínio do frontend ou
do backend mudar (domínio próprio, por exemplo), atualize `PUBLIC_FRONTEND_URL`,
`FRONTEND_URL`, `BACKEND_URL` e os callbacks cadastrados.

## Variáveis no Render

**Render → serviço do backend → Environment → Add Environment Variable.**

| Variável | Valor | Funcionalidade |
|---|---|---|
| `EMAIL_PROVIDER` | `brevo` | Recuperação de senha |
| `BREVO_API_KEY` | chave de API do Brevo — **secreta** | Recuperação de senha |
| `EMAIL_FROM` | remetente verificado no Brevo | Recuperação de senha |
| `EMAIL_FROM_NAME` | `CodeInsight AI` (opcional) | Recuperação de senha |
| `PUBLIC_FRONTEND_URL` | `https://code-insight-ai-ashen.vercel.app` | Link do e-mail e volta do login social |
| `BACKEND_URL` | `https://codeinsight-ai-89se.onrender.com` (sem barra no final) | Forma os callbacks |
| `GOOGLE_CLIENT_ID` | ID do cliente OAuth do Google | Login com Google |
| `GOOGLE_CLIENT_SECRET` | chave secreta do cliente — **secreta** | Login com Google |
| `GITHUB_OAUTH_CLIENT_ID` | Client ID do OAuth App | Login com GitHub |
| `GITHUB_OAUTH_CLIENT_SECRET` | Client secret — **secreto** | Login com GitHub |

Confira também as que já existem:

- `APP_ENV=production`.
- `FRONTEND_URL` contém o domínio da Vercel (é o CORS).
- `JWT_SECRET` **não muda**: além das sessões, ele assina o `state`, o ticket de vínculo
  e o código de troca do login social. Trocá-lo desconecta todo mundo.

Cada provedor só fica habilitado com o id **e** o secret dele definidos; sem eles, o
botão aparece desabilitado e o resto do app funciona igual.

## Na Vercel

Nada novo. O frontend só lê `VITE_API_BASE_URL`, que hoje já aponta para
`https://codeinsight-ai-89se.onrender.com/api/v1`. Confira apenas que ela está
definida para **Production** e **Preview**. Nenhum secret vai para a Vercel.

Os deploys de preview usam o backend de produção: o login social só funciona neles
depois que o backend com estas rotas estiver publicado.

## Obtendo as credenciais

### Brevo (recuperação de senha)

1. [app.brevo.com](https://app.brevo.com) → **Senders, Domains & Dedicated IPs →
   Senders** → adicione e verifique o e-mail que será o `EMAIL_FROM`.
2. **SMTP & API → API Keys → Generate a new API key** → copie direto para o Render.
3. **Security → Authorised IPs**: com o bloqueio por IP ativo, o Brevo recusa envios do
   Render — no log aparece `O provedor de e-mail respondeu com erro 401`. Desative o
   bloqueio ou autorize os IPs de saída do Render (aba **Connect → Outbound** do
   serviço).

### Google Cloud Console

1. [console.cloud.google.com](https://console.cloud.google.com/) → crie ou escolha um
   projeto.
2. **Tela de consentimento OAuth** (ou *Google Auth Platform*): tipo **Externo**; nome do
   app, e-mail de suporte, e-mail do desenvolvedor.
3. Escopos: `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile`. Não são
   sensíveis — não exigem verificação do Google.
4. **Status de publicação**: em *Teste*, só as contas listadas em *Usuários de teste*
   conseguem entrar. Para liberar a todos, mude para **Em produção**.
5. **Credenciais → Criar credenciais → ID do cliente OAuth → Aplicativo da Web**:
   - Origens JavaScript autorizadas: vazio (o fluxo é todo no servidor).
   - URIs de redirecionamento autorizados: o callback do Google da tabela acima.
6. Copie **ID do cliente** e **chave secreta** para `GOOGLE_CLIENT_ID` e
   `GOOGLE_CLIENT_SECRET` no Render.

### GitHub

1. [github.com/settings/developers](https://github.com/settings/developers) → **OAuth
   Apps → New OAuth App** (OAuth App, não GitHub App).
2. Application name `CodeInsight AI`; Homepage URL
   `https://code-insight-ai-ashen.vercel.app`; Authorization callback URL: o callback do
   GitHub da tabela acima; **Enable Device Flow** desmarcado.
3. **Register application → Generate a new client secret** → copie Client ID e Client
   secret para `GITHUB_OAUTH_CLIENT_ID` e `GITHUB_OAUTH_CLIENT_SECRET` no Render.

Este OAuth App serve só para o login (escopos `read:user user:email`). Ele não substitui
o `GITHUB_TOKEN` do servidor nem o PAT que cada usuário conecta em Configurações.

## Ordem de publicação

1. **Brevo primeiro.** As três variáveis de e-mail consertam o "esqueci a senha" já no
   código atual, sem merge. Teste antes de seguir (seção "Recuperação de senha" abaixo).
2. **Backup do banco.** O deploy roda `alembic upgrade head` (migration 0004, só
   aditiva). No Neon, crie uma branch do banco como snapshot antes do merge.
3. **OAuth, `PUBLIC_FRONTEND_URL` e `BACKEND_URL`.** O código atual ignora essas
   variáveis, então podem ser cadastradas antes do merge. Salvar variáveis no Render
   dispara um novo deploy.
4. **Merge na `main`.** Confira que o **Auto-Deploy** do Render está ligado para a
   `main`. A Vercel publica em segundos e o Render em alguns minutos — nesse intervalo
   os botões de login social ainda não funcionam.

### Revertendo

Reverter só o código **quebra o deploy**: o banco fica na revisão `0004`, que o código
antigo não conhece, e o `alembic upgrade head` do `start.sh` falha. Antes de reverter,
rode no **Shell** do serviço no Render:

```bash
alembic downgrade 0003
```

O downgrade remove `oauth_identities` e dá às contas sem senha um hash inutilizável — elas
continuam existindo e podem definir senha pelo "esqueci a senha".

## Checklist depois do deploy

### Antes de tudo

- [ ] `GET https://codeinsight-ai-89se.onrender.com/health` → `{"status":"ok",...}`
- [ ] `GET https://codeinsight-ai-89se.onrender.com/api/v1/auth/providers` →
      `{"google": true, "github": true, "password_reset": true}`
- [ ] Log de inicialização do Render **sem** "E-mail não configurado".

### Recuperação de senha

- [ ] Pedir o link para o próprio e-mail → mensagem genérica → e-mail chega (confira o
      spam).
- [ ] O link aponta para `https://code-insight-ai-ashen.vercel.app/reset-password?token=…`.
- [ ] Definir nova senha → login com a nova funciona; com a antiga, "E-mail ou senha
      inválidos".
- [ ] Abrir o mesmo link de novo → "Link inválido ou expirado".
- [ ] E-mail inexistente → exatamente a mesma mensagem, nenhum e-mail enviado.
- [ ] Dois pedidos seguidos para a mesma conta → só um e-mail (intervalo de 60 s).

### Login com Google

- [ ] Conta Google sem cadastro → cria a conta e abre o painel.
- [ ] Logout → "Continuar com Google" de novo → mesma conta, mesmos repositórios.
- [ ] Cancelar na tela do Google → "Login cancelado".
- [ ] Gmail que já tem conta com senha → aviso para entrar com senha e conectar em
      Configurações; **não** entra direto.
- [ ] Entrar com senha → **Configurações → Contas conectadas → Conectar** no Google →
      aparece conectada → depois do logout, "Continuar com Google" entra nessa conta.
- [ ] `redirect_uri_mismatch` → `BACKEND_URL` ou URI cadastrado diferentes.

### Login com GitHub

- [ ] A tela de autorização pede só leitura de perfil e e-mails — **nenhum acesso a
      repositórios**.
- [ ] Conta nova, conta existente com o mesmo e-mail, cancelamento e vínculo: como no
      Google.
- [ ] Análise de repositórios intacta: adicionar um repositório público, rodar a
      análise; o cartão do PAT em Configurações continua igual.

### Sessão e segurança

- [ ] Recarregar a página mantém a sessão; "Sair" leva ao login; `/dashboard` sem sessão
      redireciona para o login.
- [ ] Na volta do provedor, `#code=` some da barra de endereço.
- [ ] DevTools → cookie `ci_oauth_state`: `HttpOnly`, `Secure`, `SameSite=Lax`, caminho
      `/api/v1/auth/oauth`.
- [ ] Logs do Render sem tokens, secrets ou endereços de e-mail.
