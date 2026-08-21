# Arquitetura

## Visão geral

```
┌───────────────────┐     Bearer JWT      ┌──────────────────────┐
│   React + TS SPA   │ <─────────────────> │   FastAPI backend     │
│   (Tailwind, RQ)   │        REST         │   (async, Python)     │
└───────────────────┘                      └──────────┬───────────┘
                                                      │
                 ┌────────────────────────────────────┼────────────────────────┐
                 │                                    │                        │
       ┌─────────▼─────────┐         ┌────────────────▼───────────────┐        │
       │    PostgreSQL      │         │      CodeInsight Engine         │        │
       │ (usuários,         │         │   (BackgroundTask, sem IA)      │        │
       │  análises)         │         │                                 │        │
       └────────────────────┘         │  acquisition → scanner          │        │
                                      │      → 8 analyzers → scoring    │        │
                                      └────────────────┬────────────────┘        │
                                                       │                         │
                                        ┌──────────────▼─────────┐   ┌───────────▼──────────┐
                                        │    GitHub REST API      │   │  AIProvider           │
                                        │ (tarball + metadados;   │   │  OPCIONAL             │
                                        │  pública + PAT opc.)    │   │  só enriquecimento    │
                                        └─────────────────────────┘   └───────────────────────┘
```

O caminho da análise não passa pelo `AIProvider`. Ele fica ao lado e só é acionado
depois que a análise já terminou e foi gravada — uma falha dele não altera o resultado.

## O CodeInsight Engine

O motor é o núcleo do produto. Roda no seu servidor, não faz nenhuma chamada a serviço
de IA e não exige chave de API.

```
acquisition.py  → baixa e extrai o tarball do repositório com segurança
scanner.py      → inventaria os arquivos (linguagem, tamanho, binário)
analyzers/      → um por dimensão; cada um recebe o inventário e devolve achados
rules/          → detectores (AST, regex) e catálogos de regras
scoring.py      → score por dimensão, score geral e nível de risco
pipeline.py     → orquestra tudo e devolve um EngineReport
```

### Por que dois enums de dimensão

`FindingCategory` (motor) e `Dimension` (banco) têm exatamente os mesmos valores e
existem separados de propósito: o motor não deve depender da camada de persistência.
Divergirem seria um bug silencioso — achados de uma categoria sem coluna correspondente
não seriam gravados — então `tests/test_engine_scoring.py` falha se saírem de sincronia.

### Por que não existe limite pelo tamanho declarado pelo GitHub

O campo `size` da API é o repositório git **com todo o histórico**, e não guarda relação
utilizável com o que chega ao disco:

| repositório | `size` da API | tarball | descomprimido |
|---|---|---|---|
| `pydantic/pydantic` | 424 MB | 3,2 MB | 10,7 MB |
| `django/django` | 275 MB | 10,5 MB | 44,6 MB |
| `fastapi/fastapi` | 52 MB | 16,9 MB | 33,1 MB |
| `psf/requests` | 13 MB | 3,2 MB | 4,2 MB |

A razão vai de 1,6× a 132×. Um limiar baixo o bastante para proteger recusa um
repositório de 3 MB; um alto o bastante para não recusar nenhum não protege de nada.
Houve uma porta assim, e ela só produzia falsa recusa.

A proteção é a que conta bytes de verdade: contagem durante o streaming
(`ENGINE_MAX_ARCHIVE_BYTES`), orçamento descomprimido, teto de arquivos, teto por arquivo
e reconferência pós-extração. Cada uma tem teste próprio.

### Por que o repositório analisado nunca é executado

Todo repositório vindo de terceiros é tratado como hostil. Não há `subprocess`, `shell`,
`eval`, `exec`, importação dinâmica, execução de gerenciador de pacotes, script de
instalação ou Makefile em nenhum ponto do motor.

A análise de Python usa o módulo `ast` da biblioteca padrão, que faz *parsing* sem
avaliar. A de JavaScript/TypeScript é textual, por regex — e por isso os achados de JS/TS
têm confiança limitada a 0.7, já que sem parser não dá para distinguir código de string
ou de comentário.

### Por que um analyzer que falha não derruba a análise

Um arquivo inesperado pode quebrar um analyzer. Perder as outras sete dimensões por causa
disso seria pior para quem pediu a análise do que reportar a falha de uma: a exceção vira
nota na dimensão correspondente e as demais seguem.

### Por que a análise roda em thread com timeout

A análise é CPU-bound. Sem `asyncio.to_thread`, ela prenderia o event loop que atende as
requisições — o backend inteiro ficaria sem resposta durante uma análise. O timeout
(`ENGINE_MAX_ANALYSIS_SECONDS`, padrão 300s) impede que um repositório patológico segure
o worker indefinidamente.

### Por que o motor não importa nada de `app.models`

Os enums de domínio vivem em `app/enums.py`, que importa só `enum`. Estavam em
`app/models/enums.py`, e importar qualquer submódulo de `app.models` dispara o `__init__`
do pacote, que carrega os modelos SQLAlchemy e com eles `get_settings()` — o resultado era
que processar texto em busca de segredo exigia `DATABASE_URL` configurada.

`app.models.enums` continua existindo como reexportação.
`tests/test_engine_independente.py` verifica os módulos de fato carregados, não as linhas
de import: um acoplamento reintroduzido por qualquer caminho falha igual.

### Onde o tempo de uma análise grande realmente vai

`django/django` (7008 arquivos) leva ~113s numa máquina de desenvolvimento Windows. O
profiler aponta 57s dentro de `_io.open` — 52% do total — e a leitura óbvia seria "cada
analyzer relê os arquivos, deduplique as leituras". **Medido, essa leitura está errada.**

Passadas sucessivas sobre a mesma árvore recém-extraída:

| passada | tempo | por arquivo |
|---|---|---|
| 1ª (fria) | 34,5s | 6,508 ms |
| 2ª (quente) | 0,6s | 0,120 ms |
| 3ª (quente) | 0,6s | 0,110 ms |

O custo é o **primeiro toque**, não a releitura. É comportamento do sistema de arquivos e
do antivírus sobre arquivos recém-gravados — não desperdício do programa. A mesma análise
sobre a árvore já quente leva **26,4s**, contra 113s na primeira vez.

Consequências práticas:

- Deduplicar as releituras economizaria ~1,2s de 113s, menos de 2%. Não foi feito.
- Um pré-filtro por alternação no detector de credenciais foi medido e saiu **mais lento**
  (78 ms contra 65 ms): 16 padrões numa alternação custam mais para avaliar do que
  curto-circuitar por eles. Não foi feito.
- O que restou de desperdício real era `Path.resolve()` da raiz sendo recalculado por
  arquivo, e isso sim foi corrigido.

O número de 113s é de uma máquina Windows com o repositório recém-extraído. **Não medi em
Linux**, que é onde o serviço roda; o teto de `ENGINE_MAX_ANALYSIS_SECONDS` cobre o pior
caso observado com folga.

### Por que a AST é memoizada

Segurança e qualidade consomem o mesmo relatório de cada arquivo Python — um traduz as
ocorrências de risco, o outro as de manutenibilidade. Cada um chamava `analyze_python` por
conta própria: medido, 248 chamadas para 124 arquivos, 44% do tempo da análise.

O relatório é memoizado pelo digest do conteúdo, com teto de entradas. A chave é o digest
e não o texto porque guardar o fonte custaria dezenas de MB justamente nos repositórios
grandes, onde o cache importa.

## Por que a análise roda em segundo plano

Uma análise envolve baixar e extrair o tarball do repositório e percorrer milhares de
arquivos. Em repositórios grandes isso leva dezenas de segundos — inviável para uma
requisição HTTP síncrona. O endpoint `POST /analysis` só cria o registro
(`status=queued`) e agenda uma `BackgroundTask` do FastAPI; o frontend faz polling em
`GET /analysis/{id}` até o status virar `done`/`failed`.

Não há fila externa (Redis/Celery): o custo operacional de manter um broker não se
justifica para a carga deste produto, e a `BackgroundTask` do próprio FastAPI resolve o
caso com uma dependência a menos para instalar, hospedar e monitorar.

## Por que JWT via header em vez de cookie de sessão

Sem fluxo de redirect OAuth, não há necessidade de cookie (que existiria principalmente
para sobreviver a um redirect entre domínios). Usar `Authorization: Bearer <token>` é o
padrão para APIs REST com login e-mail/senha, evita a complexidade de proteção CSRF que
cookies exigem, e funciona identicamente em qualquer cliente (SPA, mobile, CLI). O token
é stateless — "logout" é o cliente descartar o token; não há blocklist no servidor (ver
Roadmap no README).

## Camadas do backend

```
api/routes/   → HTTP: validação de entrada (Pydantic), autenticação, chamadas a services/repositories
engine/       → CodeInsight Engine: a análise em si (sem banco, sem HTTP, sem IA)
services/     → lógica de negócio (persistência da análise, geração de PDF, dashboard)
repositories/ → acesso a dados (SQLAlchemy) — sem lógica de negócio
ai/           → interface AIProvider + providers concretos + factory (OPCIONAL)
models/       → modelos SQLAlchemy (schema do banco)
schemas/      → schemas Pydantic (contrato da API)
prompts/      → prompts do que a IA faz DEPOIS da análise: sugestões, correção, README
tasks/        → execução em segundo plano (orquestra engine/services fora do ciclo request/response)
```

Essa separação existe para que trocar de provedor de IA não exija tocar em `services/`,
para que trocar a forma de consultar o banco não exija tocar nas rotas, e — o mais
importante depois da migração — para que o motor possa ser testado sem banco, sem rede e
sem provedor nenhum.

## Por que dados do GitHub não são espelhados no banco

Linguagens, branches, commits, issues, PRs e contribuidores são buscados **ao vivo** a
cada consulta (`GET /repos/{id}/github-summary`), não persistidos. Persistir esses dados
exigiria um mecanismo de sincronização (o que acontece se o usuário fizer push depois?) —
buscar ao vivo é mais simples e sempre reflete o estado atual do repositório.

Os arquivos do repositório analisado vivem apenas num diretório temporário durante a
análise, removido ao final — inclusive em erro, timeout e cancelamento. Só os
*resultados* (score, achados) são persistidos.

## Modelo de dados

| Tabela | Descrição |
|---|---|
| `users` | Conta do usuário (e-mail, hash da senha, username) |
| `github_credentials` | PAT opcional do usuário, criptografado (1:1 com `users`) |
| `repositories` | Repositório do GitHub adicionado por um usuário |
| `analyses` | Uma execução de análise sobre um repositório |
| `analysis_results` | Resultado de UMA dimensão dentro de uma análise (score, achados) |
| `suggestions` | Sugestões priorizadas, geradas por IA ao final da análise (opcional) |
| `fix_suggestions` | Correção gerada por IA sob demanda para UM achado (opcional) |
| `generated_readmes` | README gerado por IA para uma análise (opcional, 1:1) |

`risk_level` **não** é coluna: é derivado na serialização, com a mesma função do motor.
Gravá-lo congelaria análises antigas num critério que pode mudar, e duplicar a regra faria
o relatório e a tela discordarem entre si.

## Score

Cada dimensão parte de 100 e desconta uma penalidade calculada a partir dos achados.
Três decisões sustentam o cálculo:

**Severidade domina quantidade.** Cada severidade tem um peso base (crítico 40, alto 15,
médio 5, baixo 1.5) e a contagem entra pela raiz quadrada. A confiança de cada achado
escala a contagem: heurística incerta não derruba o score como uma certeza derrubaria.

**A penalidade é por densidade, não por contagem absoluta.** Acima de 100 arquivos, o que
pesa é a proporção de achados por arquivo. Sem isso, todo repositório grande saturava em
zero: medido, `numpy/numpy` acumulava 1929 achados baixos em 2361 arquivos e recebia o
mesmo veredito de um projeto de dez arquivos com trinta problemas graves. Abaixo de 100
arquivos nada muda — é a faixa em que os pesos de severidade foram calibrados.

**Não avaliado nunca vira nota cheia.** Uma dimensão sem analyzer que a cubra recebe
`None`, não 100, e é listada em `unevaluated_dimensions`. Os pesos são renormalizados
sobre o que foi de fato avaliado. Tratar ausência de informação como ausência de problema
é a forma mais fácil de um relatório mentir.

**Um achado crítico não some na média.** A presença de um crítico estabelece um piso para
o nível de risco: um repositório excelente com uma chave privada versionada continua
sendo um repositório com uma chave privada versionada.

| Dimensão | Peso |
|---|---|
| Segurança | 22% |
| Qualidade | 16% |
| Dependências | 14% |
| Arquitetura | 12% |
| Testes | 12% |
| Configuração | 10% |
| Documentação | 8% |
| Git | 6% |

Segurança tem o maior peso porque é a única dimensão cujo pior caso é irreversível:
código feio se refatora, credencial vazada não se "desvaza".

### Níveis de risco

| Score geral | Nível |
|---|---|
| ≥ 85 | Baixo |
| ≥ 70 | Moderado |
| ≥ 50 | Alto |
| < 50 | Crítico |

Os cortes são redondos de propósito: fingir precisão decimal numa avaliação heurística
seria falsa exatidão.

### Código de teste não é código de produção

`assert` é como se escreve um teste em pytest, e uma chamada de rede num teste vai para um
dublê — reportar os dois ali produziria centenas de achados corretos e inúteis. Medido em
`psf/requests`, eram 701 de 753 achados de qualidade.

Credencial ou certificado em caminho de teste **continua sendo reportado**, rebaixado para
severidade baixa e com a ressalva de confirmar que não é real: fixture é o caso comum, não
o único.

## Sistema de provedores de IA (opcional)

Veja [`ai-providers.md`](ai-providers.md) para o detalhamento da interface `AIProvider`,
o que ela habilita e como adicionar um provider novo.
