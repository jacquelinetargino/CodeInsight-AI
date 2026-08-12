# Arquitetura

## Visão geral

```
┌──────────────────┐      Bearer JWT       ┌───────────────────┐
│  React + TS SPA   │ <──────────────────> │   FastAPI backend   │
│  (Tailwind, RQ)    │       REST            │   (async, Python)   │
└──────────────────┘                       └─────────┬──────────┘
                                                        │
                    ┌────────────────────────────────────┼───────────────────────────┐
                    │                                     │                            │
             ┌──────▼──────┐                    ┌─────────▼─────────┐        ┌─────────▼─────────┐
             │ PostgreSQL   │                    │ Redis + Celery     │        │  AIProvider         │
             │ (usuários,   │                    │ worker (jobs de    │        │  (interface)         │
             │ análises)    │                    │ análise async)     │        │  ├─ ClaudeProvider    │
             └──────────────┘                    └─────────┬──────────┘        │  ├─ OpenAIProvider    │
                                                              │                   │  ├─ GeminiProvider    │
                                                    ┌─────────▼─────────┐        │  └─ LocalAIProvider   │
                                                    │   GitHub REST API   │        └───────────────────┘
                                                    │  (pública + PAT opc.)│
                                                    └─────────────────────┘
```

## Por que uma fila assíncrona (Celery + Redis)?

Uma análise completa envolve: várias chamadas à GitHub API (árvore de arquivos,
linguagens, branches, commits, issues, PRs, contribuidores) e 7 chamadas ao provedor
de IA (6 dimensões + sugestões priorizadas). Isso facilmente leva dezenas de segundos
a poucos minutos — inviável para uma requisição HTTP síncrona. O endpoint
`POST /analysis` só cria o registro (`status=queued`) e enfileira uma task Celery; o
frontend faz polling em `GET /analysis/{id}` até o status virar `done`/`failed`.

## Por que JWT via header em vez de cookie de sessão?

Sem fluxo de redirect OAuth, não há necessidade de cookie (que existiria
principalmente para sobreviver a um redirect entre domínios). Usar
`Authorization: Bearer <token>` é o padrão para APIs REST com login e-mail/senha, evita
a complexidade de proteção CSRF que cookies exigem, e funciona identicamente em
qualquer cliente (SPA, mobile, CLI). O token é stateless — "logout" é o cliente
descartar o token; não há blocklist no servidor (ver Roadmap no README).

## Camadas do backend

```
api/routes/   → HTTP: validação de entrada (Pydantic), autenticação, chamadas a services/repositories
services/     → lógica de negócio (orquestração da análise, geração de PDF, dashboard)
repositories/ → acesso a dados (SQLAlchemy) — sem lógica de negócio
ai/           → interface AIProvider + providers concretos + factory
models/       → modelos SQLAlchemy (schema do banco)
schemas/      → schemas Pydantic (contrato da API)
prompts/      → templates de prompt por dimensão (texto puro, sem dependência de IA)
tasks/        → tasks Celery (orquestra services/repositories fora do ciclo request/response)
```

Essa separação existe para que, por exemplo, trocar de provedor de IA não exija tocar
em `services/`, e para que trocar a forma de consultar o banco (`repositories/`) não
exija tocar nas rotas.

## Por que dados do GitHub não são espelhados no banco?

Linguagens, branches, commits, issues, PRs e contribuidores são buscados **ao vivo** a
cada consulta (`GET /repos/{id}/github-summary`), não persistidos. Persistir esses
dados exigiria um mecanismo de sincronização (o que acontece se o usuário fizer push
depois?) — buscar ao vivo é mais simples e sempre reflete o estado atual do
repositório. O único dado do GitHub persistido é o necessário para a análise em si
(conteúdo dos arquivos coletados no momento da análise), que não é salvo após o
processamento — só os *resultados* da análise (score, achados) são persistidos.

## Modelo de dados

| Tabela | Descrição |
|---|---|
| `users` | Conta do usuário (e-mail, hash da senha, username) |
| `github_credentials` | PAT opcional do usuário, criptografado (1:1 com `users`) |
| `repositories` | Repositório do GitHub adicionado por um usuário |
| `analyses` | Uma execução de análise sobre um repositório |
| `analysis_results` | Resultado de UMA dimensão dentro de uma análise (score, achados) |
| `suggestions` | Sugestões de melhoria priorizadas, geradas em lote ao final da análise |
| `fix_suggestions` | Correção gerada sob demanda para UM achado específico |
| `generated_readmes` | README gerado para uma análise (1:1) |

## Score

Cada dimensão recebe um score de 0 a 100 pelo provedor de IA. O score geral é a média
ponderada:

| Dimensão | Peso |
|---|---|
| Segurança | 25% |
| Qualidade | 25% |
| Arquitetura | 15% |
| Documentação | 15% |
| Testes | 10% |
| Git | 10% |

Segurança e qualidade têm o maior peso por serem os fatores mais diretamente ligados a
risco e manutenibilidade; testes e git entram como sinais complementares.

## Sistema de provedores de IA

Veja [`ai-providers.md`](ai-providers.md) para o detalhamento completo da interface
`AIProvider`, como cada provider é implementado e como adicionar um novo.
