# Changelog

Todas as mudanças notáveis deste projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

## [0.3.4] — Autenticação, mensagens de erro e a terceira porta do mesmo escape

### Corrigido

- **O teste que garante que o relatório não avalia template dava alarme falso.** Ele
  procura no documento inteiro o resultado que o payload produziria se fosse executado,
  e a sentinela de `{{ 7*7 }}` era `"49"` — que também é o minuto da data de geração
  carimbada no rodapé. Às 22:49 a suíte reprovou a main acusando avaliação de template
  que não houve. `"Config"`, sentinela de `{{ config }}`, tinha o mesmo defeito latente:
  é prefixo de "Configuração", o rótulo da dimensão CONFIGURATION, e só passava porque o
  relatório de teste tem uma dimensão só. As sentinelas passaram a ser valores que nada
  mais no relatório produz, e dois testes novos impedem a repetição. A capacidade de
  detecção não mudou: reintroduzindo a avaliação de propósito, os três payloads
  continuam sendo pegos.

- **O download do tarball aceitava redirecionamento para `http://`.** A allowlist conferia
  o host e não o esquema, então `http://codeload.github.com/...` passava — e a requisição
  leva `Authorization: Bearer` em todos os saltos, medido saindo em texto claro. Quem
  controla esse redirecionamento é o GitHub, então não era alcançável por um usuário da
  aplicação; era a checagem que faltava para a garantia ser a que o módulo diz ter. O
  caminho da URL do tarball também passou a ser conferido: é o terceiro lugar onde `..`
  num segmento trocaria o endpoint chamado (ver PRs 35 e 38). Nenhuma entrada chega lá
  com `..` hoje, e a guarda existe porque nos dois casos anteriores o que faltava era
  exatamente ela.

### Registrado como pendência

- **O `Authorization` é reenviado em todos os saltos do download**, ao contrário do que o
  httpx faz sozinho ao trocar de origem. Não foi alterado: os três hosts permitidos são
  do GitHub, e verificar se o `codeload` precisa do token para entregar tarball de
  repositório privado exige um repositório privado de teste. Mudar sem medir arriscaria
  quebrar a análise de repositório privado.

- **`file_path` de `POST /analysis/{id}/fix` escapava do repositório.** Mesma classe do
  PR 35, por outra porta: o campo entra no caminho de uma URL da GitHub API e o httpx
  normaliza `..` ao construir a URL. Medido, interceptando a requisição real,
  `../../../vitima/repo-privado/contents/.env` virava
  `https://api.github.com/repos/vitima/repo-privado/contents/.env` — com o PAT do
  usuário ou, na falta dele, o `GITHUB_TOKEN` do servidor. O conteúdo volta em base64, é
  decodificado e segue para o provedor de IA como contexto da correção, que o usuário
  lê: com token de servidor configurado, qualquer usuário autenticado lia qualquer
  repositório que aquele token alcança, inclusive privado. `?` escapava por outro
  caminho, encerrando o segmento e virando query string. Corrigido com validação na
  entrada e, abaixo dela, uma rede em `_get` que recusa qualquer caminho reescrito ao
  montar a URL — porque validar só a entrada de hoje foi o que deixou este caso passar
  depois do PR 35.

- **A análise falhada devolvia a exceção crua ao usuário.** `Analysis.error_message`
  recebia `str(exc)` de qualquer exceção e é renderizado na página da análise. Medido:
  um `FileNotFoundError` do motor entregava `C:\Users\<conta>\AppData\Local\Temp\codeinsight-a1b2c3\src\...`
  — caminho do diretório temporário e nome da conta que roda o servidor; um `KeyError`
  chegava como `'chave_que_nao_existe'`, que não informa nada. E como mensagem de erro
  de sistema de arquivos carrega o nome do arquivo, o repositório analisado (conteúdo
  não confiável) escolhia parte do texto exibido — não era XSS, porque o React escapa,
  mas era um caminho até a interface que ninguém tinha desenhado. Agora só a mensagem
  escrita para o usuário passa; o resto vira texto genérico e o detalhe fica no log. A
  recusa da GitHub API é traduzida por status em vez de escondida: 404 explica que o
  repositório pode ser privado e como conectar um token.

- **As rotas de autenticação não tinham limite de taxa.** Medido: 60 tentativas de senha
  seguidas contra a mesma conta responderam 401 e nenhuma 429 — adivinhar senha era só
  uma questão de tempo. Cada tentativa contra uma conta existente ainda custa ~210 ms de
  CPU do servidor (o bcrypt), então a rota também servia de alavanca de exaustão sem
  exigir credencial nenhuma. `POST /auth/login` passa a 10/min/IP e `POST /auth/register`
  a 5/min/IP. O limite é por IP: um atacante distribuído não é barrado por ele, e isso
  está registrado em `docs/security.md` em vez de subentendido.
- **O tempo de resposta do login dizia quem tem conta.** E-mail cadastrado respondia em
  213 ms e desconhecido em 0,9 ms — 236× de diferença, porque o `or` curto-circuitava
  antes do `verify_password`. A conferência agora roda nos dois casos, contra um hash
  descartável quando o e-mail não existe.
- **O cadastro aceitava senha maior do que o bcrypt usa.** O limite era de 128
  caracteres, mas o algoritmo só considera os primeiros 72 **bytes** e descarta o resto
  em silêncio: `"A"*72 + "sufixo-ignorado"` casa com o hash de `"A"*72`. Quem escolhesse
  uma frase-senha de 100 caracteres tinha 72 protegendo a conta e 28 decorativos. O teto
  passa a ser 72 bytes, com mensagem explicando o porquê. Vale só no cadastro — contas
  antigas com senha mais longa continuam entrando.
- **O 429 chegava ao usuário como "Erro 429".** O `slowapi` responde com
  `{error: ...}` e não com o `detail` do FastAPI, então o frontend não achava mensagem
  nenhuma. Passava despercebido enquanto o limite só existia em rotas caras; com o
  limite no login, quem errasse a senha dez vezes veria só o número.

### Adicionado

- **Conteúdo do repositório analisado não injeta no relatório** (PR 34) — a montagem do
  HTML do PDF foi separada da conversão, e nome, descrição e evidência de achado passam
  por escape verificado por teste.
- **A referência de repositório é validada antes de virar caminho de URL** (PR 35) —
  `../user` escapava do prefixo `/repos` e alcançava `/user` da GitHub API com o token do
  servidor. Corrigido e coberto por teste.
- O limitador é zerado entre testes (`conftest`). A contagem vive na memória do processo
  e sobrevive de um teste para o outro: com o limite de 5/min no cadastro e 4 registros
  já existentes na suíte, o próximo teste a registrar um usuário — em qualquer arquivo —
  passaria a receber 429 sem ter nada a ver com o que testa.


## [0.3.3] — Garantias de segurança viram teste

Auditoria das promessas de `SECURITY.md` contra o que o código realmente garante.
Cada uma foi verificada por **mutação**: quebrar a proteção de propósito e confirmar
que a suíte acusa. Duas passavam despercebidas.

### Corrigido

- **O limite de taxa de `POST /analysis/{id}/fix` valia por análise, não por IP.** O
  `slowapi` usa `key_style="url"` por padrão, o que põe o caminho concreto no balde do
  limite — e a rota tem um id variável. Medido: 23 chamadas com ids diferentes, nenhum
  429, contra um limite anunciado de 20 por minuto. Quem tivesse dez análises fazia
  duzentas chamadas de IA por minuto, justamente as caras. `POST /analysis` não sofria
  disso porque o caminho é fixo, e foi por isso que passou despercebido.
- **`default_limits=["120/minute"]` nunca se aplicou.** O `slowapi` só impõe limite
  padrão pelo `SlowAPIMiddleware`, que a aplicação não registra: 130 chamadas seguidas a
  uma rota sem decorador responderam 200. Removido — configuração que promete o que não
  acontece é pior do que nenhuma.
- **`mypy` não reprovava nada.** Rodava com `continue-on-error: true`, então erro de tipo
  novo entraria sem ninguém notar. Os 19 erros do baseline foram a zero e o check passou
  a gatilhar.
- **O contrato de construção dos providers de IA não estava declarado.** A factory já
  chamava `provider_cls(api_key=..., model=..., base_url=...)`, mas nada verificava se um
  provider novo o respeitava. Declará-lo expôs que `ai_api_key` é `str | None` e ia para
  providers que declaravam `str`.

### Adicionado

- **Isolamento entre usuários, verificado.** As rotas verificam posse em sete pontos e
  nenhum teste garantia isso: trocar `get_owned_detail(id, user_id)` por `get(id)` num
  refactor deixaria os 709 testes passando. Inclui os agregados do dashboard, onde
  remover o filtro de dono mantinha as consultas válidas — só passavam a somar o de todo
  mundo.
- **O PAT é criptografado em repouso, verificado.** Três documentos prometiam; nada
  checava. Trocando `encrypt_secret(payload.token)` por `payload.token`, os 723 testes
  continuavam verdes e o token ia legível para o banco.
- **Nenhuma rota de negócio fica pública.** Uma rota nova sem `Depends(get_current_user)`
  agora quebra o build em vez de entrar em silêncio.
- **Os limites de taxa são exercitados** — disparam na chamada certa, e uso normal não é
  barrado.

### Limitação registrada

O limitador guarda contagem **em memória do processo**. Com mais de uma instância, cada
uma tem seu balde e o limite efetivo é multiplicado pelo número de réplicas. Corrigir
exigiria armazenamento compartilhado, e reintroduzir Redis foi descartado como dívida.

## [0.3.2] — O relatório não afirma mais do que sabe

Auditoria das afirmações que chegam ao usuário e do desempenho em repositório grande.

### Corrigido

- **TST-002 afirmava cobertura que o motor não mede.** A descrição dizia que a proporção
  de arquivos de teste "indica cobertura desigual, com partes do sistema sem verificação".
  A regra conta arquivos e não executa a suíte: poucos arquivos de teste podem exercitar
  muita coisa, e muitos podem exercitar pouca. O texto passa a declarar o que de fato
  observou. TST-005 foi mantida — ela menciona cobertura para dizer que **não** a mediu.
- **`Path.resolve()` da raiz era recalculado a cada arquivo**, o que em `django/django`
  eram 28 032 chamadas a `_getfinalpathname`, metade delas para o mesmo valor.

### Adicionado

- **`detection_method` em cada achado**: `ast`, `text` ou `metadata`. A confiança sozinha
  não separava as coisas — `os.system()` confirmado pela árvore sintática saía com 0.85 e
  um casamento de regex em JavaScript com 0.7, dois números que caíam no mesmo rótulo
  ("detecção provável") e chegavam ao usuário como se fossem a mesma evidência. O motor
  não tem parser de JavaScript, e um teste garante que nenhum achado de JS/TS saia
  marcado como AST.
- A tela mostra o método ("via busca textual"), com a ressalva completa no título.

### Investigado e deliberadamente não feito

`django/django` leva ~113s numa máquina Windows, e o profiler aponta 52% do tempo dentro
de `_io.open`. Medido, o custo é o **primeiro toque** na árvore recém-extraída (6,5 ms por
arquivo) e não a releitura (0,12 ms): a mesma análise sobre a árvore quente leva 26,4s.

- Deduplicar as leituras entre analyzers economizaria menos de 2%.
- Um pré-filtro por alternação no detector de credenciais saiu **mais lento** (78 ms
  contra 65 ms).

Ambos ficam registrados em `docs/architecture.md` e num módulo de teste, para que a
investigação não precise ser repetida.

### Compatibilidade

`detection_method` é opcional em toda a cadeia. Análises gravadas antes dele continuam
legíveis e recebem `metadata` na releitura — afirmar "AST" sobre um achado de origem
desconhecida seria inventar procedência.

## [0.3.1] — Endurecimento pós-release

Auditoria da 0.3.0 contra repositórios públicos reais. Nenhuma funcionalidade nova:
o que mudou foi o produto parar de errar em casos que só aparecem fora do laboratório.

### Corrigido

- **O limite de tamanho recusava repositórios analisáveis.** A porta usava o campo `size`
  da GitHub API, que é o repositório git com todo o histórico. Medido: `pydantic/pydantic`
  declara 424 MB e entrega um tarball de 3,2 MB — 132× menos. A razão vai de 1,6× a 132×
  entre repositórios, então nenhum limiar serve para os dois lados. A porta foi removida;
  as cinco proteções que contam bytes de verdade continuam inteiras, cada uma com teste.
- **O score saturava em zero em qualquer repositório grande.** `numpy/numpy` acumulava
  1929 achados baixos em 2361 arquivos e recebia nota zero — o mesmo veredito de um
  projeto de dez arquivos com trinta problemas graves. Todo repositório grande saía como
  risco crítico. A penalidade passou a ser por densidade acima de 100 arquivos; abaixo
  disso a fórmula é idêntica. Depois: pydantic 45,7 → 70,5, fastapi 52,6 → 87,0.
- **O timeout não tinha margem.** `django/django` leva ~113s contra um teto de 120s. Novo
  padrão: 300s. A análise roda em thread, então esperar mais não bloqueia o event loop.
- **Três reprovações de contraste no tema escuro** — `destructive` 3,53:1, `primary`
  4,30:1 e a borda de campo de formulário 1,43:1, contra mínimos de 4,5:1 e 3:1. A borda
  reprovava também no tema claro, com 1,27:1.
- **Repositório removido entre o enfileiramento e a execução** produzia erro de
  `NoneType` em vez de mensagem útil.
- O branch padrão passa a vir da API, não do banco: o valor gravado é do momento do
  cadastro, e renomear o branch principal fazia a análise pedir um ref inexistente.

### Adicionado

- **Modo escuro funcional.** A infraestrutura já existia — `darkMode: ["class"]` e um
  bloco `.dark` completo — e nada aplicava a classe. São três estados (claro, escuro,
  sistema), com o tema aplicado antes da primeira pintura para não haver lampejo branco.
- **Auditoria de contraste como teste**: lê os tokens do `index.css` e aplica a fórmula
  da WCAG nos dois temas, incluindo os pares preenchimento/texto e a presença de cada
  token em ambos.

### Alterado

- **A credencial do Postgres do CI foi removida, não isentada.** O detector acusava
  `codeinsight:codeinsight@localhost` e estava certo. O container é efêmero e alcançável
  só pelo localhost do runner, então `POSTGRES_HOST_AUTH_METHOD=trust` elimina o segredo.
  Nenhuma exceção foi criada no detector: uma isenção por "host local" ou "arquivo de CI"
  abriria caminho para segredo real passar.
- **O motor deixou de depender da camada de persistência.** Importar o detector de
  credenciais exigia `DATABASE_URL`, `JWT_SECRET` e `ENCRYPTION_KEY` — processar texto
  pedia um Postgres. Os enums passaram para `app/enums.py`; `app.models.enums` continua
  funcionando como reexportação.
- **Cada arquivo Python é parseado uma vez, não duas.** Segurança e qualidade consomem o
  mesmo relatório da AST e cada um o calculava: 248 chamadas para 124 arquivos, 44% do
  tempo. Ganho de 20% onde Python domina; 3% em `django/django`, cujo custo está em outro
  lugar e segue por investigar.

### Removido

- Serviço Redis, variáveis `CELERY_*` e instalação das bibliotecas do WeasyPrint no CI,
  herdados da migração para BackgroundTasks e xhtml2pdf (MIG-007). Verificado antes de
  remover: nenhuma referência no código, nas dependências, no Docker ou nos testes.

## [0.3.0] — O CodeInsight Engine assume a análise

A mudança central desta versão: **analisar um repositório não exige mais chave de API,
crédito nem conexão com nenhum serviço de IA.** A análise passa a ser feita por um motor
de análise estática próprio, escrito em Python, que roda inteiramente no seu servidor.

Provedores de IA continuam suportados e passam a ser **estritamente opcionais**: servem
para gerar sugestões priorizadas, correções sob demanda, README e explicações de achados.
Sem provedor configurado, esses quatro recursos simplesmente não aparecem — a análise, o
score e o nível de risco não mudam.

### Adicionado

- **CodeInsight Engine** (`app/engine/`): aquisição segura do tarball, inventário de
  arquivos, oito analyzers, catálogo de regras e cálculo de score. Nenhuma dependência
  externa de análise — a de Python usa o módulo `ast` da biblioteca padrão.
- Oito dimensões de análise, contra as seis anteriores: **dependências** e
  **configuração** entram; segurança, qualidade, arquitetura, testes, documentação e git
  passam a ser avaliadas sem IA.
- **Nível de risco** do repositório (`risk_level`), derivado do score e dos achados. A
  presença de um achado crítico estabelece um piso: um repositório de resto excelente com
  uma chave privada versionada não é reportado como risco baixo.
- **Dimensões não avaliadas** (`unevaluated_dimensions`) são declaradas explicitamente.
  Dimensão sem resultado recebe "não avaliado", nunca nota cheia.
- Achados passam a trazer **identificador de regra, evidência e confiança**, além dos
  campos anteriores. A confiança existe porque boa parte da análise é heurística, e
  declarar a dúvida é melhor do que afirmar certeza sobre o que foi inferido.
- Aquisição defensiva do repositório: limite de bytes durante o download, recusa de
  caminhos que escapam do destino, symlinks descartados, tetos de arquivos e de tamanho
  descomprimido, allowlist de hosts contra SSRF, e remoção do diretório temporário
  inclusive em erro, timeout e cancelamento.
- Timeout de análise (`ENGINE_MAX_ANALYSIS_SECONDS`) e execução em thread, para que uma
  análise pesada não prenda o event loop que atende as requisições.
- Isolamento por schema para a suíte de testes (`TEST_DB_SCHEMA`), para quem não tem
  permissão `CREATEDB` no ambiente local.
- Testes que executam as migrations de verdade, num schema descartável, comparando o enum
  resultante com o modelo.

### Alterado

- `analysis_dimension` passou de 6 para 8 valores (migration `0002`): `dependencies` e
  `configuration` foram acrescentados e `tests` renomeado para `testing`. Nenhuma linha
  foi reescrita ou removida.
- Pesos das dimensões recalibrados para as oito atuais. Segurança tem o maior peso por
  ser a única cujo pior caso é irreversível.
- O score deixa de vir do provedor de IA e passa a ser determinístico: a mesma entrada
  produz sempre a mesma saída, o que torna duas análises comparáveis.
- A API deixa de descartar os campos que o motor produz — `rule_id`, `evidence` e
  `confidence` chegavam do banco e eram removidos na resposta.
- Interface: nível de risco, regra, evidência e confiança na tela; dimensão não avaliada
  anunciada; textos que prometiam "análise com IA" corrigidos.

### Corrigido

- **Contraste de texto abaixo do mínimo acessível.** Medido no navegador: `success` dava
  3.13:1 e `warning` 2.08:1 como cor de texto, contra o mínimo de 4.5:1. Atingia o score
  de cada dimensão, os badges de severidade e o histórico. As cores vivas seguem em
  preenchimentos e gráficos; para texto entram variantes medidas em 4.69:1 e 4.68:1.
- **Código de teste era tratado como código de produção.** `assert` em pytest e chamadas
  de rede em testes eram reportados como problema — em `psf/requests`, 701 de 753 achados
  de qualidade. Credencial em caminho de teste continua sendo reportada, rebaixada.
- **Repositório renomeado quebrava a análise inteira**: a API do GitHub responde 301 e o
  client não seguia o redirecionamento.
- **Arquivos acima do teto de análise sumiam do inventário**, então uma chave privada
  grande demais para ler era invisível para a análise.
- Repositório removido entre o enfileiramento e a execução produzia `AttributeError` de
  `NoneType` em vez de mensagem útil.

### Removido

- Exigência de provedor de IA para analisar um repositório.
- Celery e Redis: a análise roda como `BackgroundTask` do FastAPI. Um broker a menos para
  instalar, hospedar e monitorar.

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
