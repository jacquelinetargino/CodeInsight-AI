# IP do cliente atrás do proxy do Render

O rate limit precisa saber **quem** fez a requisição. Atrás de proxy, a conexão vem do
proxy, e o IP real só aparece no `X-Forwarded-For`. Esta página explica como validar a
cadeia de proxies do Render **antes** de ativar `TRUSTED_PROXY_HOPS`, sem gravar IP de
ninguém. O porquê técnico está em [`security.md`](security.md#qual-ip-conta-atrás-de-proxy).

## Situação padrão

`TRUSTED_PROXY_HOPS=0`: o cabeçalho é ignorado e a chave é o IP da conexão. No Render,
isso significa que todos os usuários dividem o mesmo limite — o comportamento de sempre,
seguro mas restritivo. **Fique assim enquanto a validação abaixo não for feita.**

## O que se espera do Render

Fontes secundárias (fórum e artigos; o Render não documenta oficialmente) descrevem o
caminho cliente → Cloudflare → proxy do Render → app, com o cabeçalho chegando como:

```
X-Forwarded-For: <o que o cliente forjar, se forjar>, <seu IP real>, <IP do edge da Cloudflare>
```

Se for isso, o valor certo é `TRUSTED_PROXY_HOPS=2`. **Não assuma**: a cadeia pode ter
mais ou menos saltos, e errar para mais deixa o limite burlável. Valide.

## Validação passo a passo

Nada aqui é gravado em log. O endpoint de diagnóstico mostra a **quem chama** só a forma
da própria requisição, com cada IP reduzido à rede (`/24` no IPv4, `/48` no IPv6).

1. **Descubra a rede do seu IP público.** Abra `https://api.ipify.org` e anote só os três
   primeiros blocos (ex.: `198.51.100`). Não precisa anotar nem compartilhar o resto. Se o
   diagnóstico mostrar redes IPv6 (com `:`), use `https://api64.ipify.org` e compare os
   três primeiros grupos (o `/48`).
2. **Ligue o diagnóstico** — Render → backend → **Environment**:
   `PROXY_DIAGNOSTICS_ENABLED=true`, com `TRUSTED_PROXY_HOPS` ausente ou `0`. Salve e
   faça o deploy.
3. **Leitura normal.** Abra no navegador
   `https://codeinsight-ai-89se.onrender.com/health/proxy` e veja `x_forwarded_for`:
   - `total`: quantas entradas chegaram.
   - Em `entradas`, a que tem a `rede` igual à sua (ex.: `198.51.100.0/24`) — o número em
     `posicao_da_direita` dela é o **candidato** a `TRUSTED_PROXY_HOPS`.
   - `conexao.tipo` deve ser `privado` (o proxy interno do Render).
4. **Tentativa de falsificação.** No terminal:

   ```bash
   curl -s -H "X-Forwarded-For: 192.0.2.1" https://codeinsight-ai-89se.onrender.com/health/proxy
   ```

   O esperado: `total` aumenta em **1**, a entrada `192.0.2.0/24` aparece **à esquerda**
   (maior `posicao_da_direita`), e a sua rede **continua na mesma posição** do passo 3.
5. **Outra rede.** Repita o passo 3 de outra conexão (ex.: celular no 4G, fora do Wi-Fi).
   A rede mostrada muda, mas a **posição** e o `total` têm de ser os mesmos.
6. **Repita algumas vezes** os passos 3 e 4, em horários diferentes: o Render pode
   rotear por caminhos diferentes. A posição tem de ser estável em todas.

### Só ative se TODOS estes forem verdade

- [ ] A sua rede aparece em **uma posição fixa** contando da direita, em todas as
      leituras e nas duas redes.
- [ ] No passo 4, o valor forjado ficou **à esquerda** e a sua posição não mudou.
- [ ] Nenhuma leitura teve `total` menor que essa posição.

Se qualquer item falhar ou variar, **não ative**: mantenha `TRUSTED_PROXY_HOPS=0` e abra
um chamado com o suporte do Render perguntando quantas entradas o proxy acrescenta.

## Ativando

1. Render → **Environment**: `TRUSTED_PROXY_HOPS=<a posição validada>` e
   `PROXY_DIAGNOSTICS_ENABLED=false`. Salve e faça o deploy.
2. Confira que `https://codeinsight-ai-89se.onrender.com/health/proxy` voltou a
   responder **404**.
3. **Teste o limite de verdade** (a rota usada não envia e-mail para endereço inexistente):

   ```bash
   for i in 1 2 3 4 5 6; do curl -s -o /dev/null -w "%{http_code} " -X POST -H "Content-Type: application/json" -H "X-Forwarded-For: 192.0.2.$i" -d '{"email":"teste-limite@example.com"}' https://codeinsight-ai-89se.onrender.com/api/v1/auth/forgot-password; done; echo
   ```

   Esperado: cinco respostas normais (`202`) e o sexto `429` — **mesmo trocando o
   cabeçalho forjado a cada pedido**. Logo em seguida, a mesma chamada a partir da outra
   rede (4G) deve responder `202`: é a prova de que cada usuário tem o próprio balde.

## Desfazendo

Basta `TRUSTED_PROXY_HOPS=0` (ou remover a variável) e fazer o deploy: volta o
comportamento anterior, sem nenhuma outra mudança.

## Variáveis

| Variável | Padrão | Descrição |
|---|---|---|
| `TRUSTED_PROXY_HOPS` | `0` | Número de proxies confiáveis que acrescentam ao `X-Forwarded-For`. Aceita de 0 a 5 |
| `PROXY_DIAGNOSTICS_ENABLED` | `false` | Liga `GET /health/proxy`. Ligue só durante a validação |
