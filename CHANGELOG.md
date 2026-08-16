# Changelog

Todas as mudanças notáveis deste projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

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
