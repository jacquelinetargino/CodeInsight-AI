# Changelog

Todas as mudanças notáveis deste projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

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
