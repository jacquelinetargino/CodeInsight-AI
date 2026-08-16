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
(`ENGINE_MAX_ANALYSIS_SECONDS`, padrão 120s) impede que um repositório patológico segure
o worker indefinidamente.

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
prompts/      → templates de prompt por dimensão (caminho de IA)
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
médio 5, baixo 1.5) e a contagem entra pela raiz quadrada. O retorno decrescente evita
que um repositório grande seja punido só por ser grande — o décimo aviso de estilo diz
muito menos sobre o projeto do que o primeiro. A confiança de cada achado escala a
contagem: heurística incerta não derruba o score como uma certeza derrubaria.

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
