# CodeInsight AI — Frontend

SPA em React + TypeScript (Vite) para o CodeInsight AI: login/cadastro, dashboard de
agregados, adicionar repositórios por URL, visualização de análises (score por 6
dimensões, achados com linha, sugestões, correções sob demanda) e geração de README.

## Rodando fora do Docker

```bash
npm install
npm run dev
```

Configure `VITE_API_BASE_URL` (por padrão `http://localhost:8000/api/v1`) via `.env`
na raiz do projeto ou variável de ambiente.

Autenticação usa um token JWT (Bearer) guardado no `localStorage` — não há cookies
nem redirecionamento OAuth envolvidos.

## Estrutura

```
src/
├── pages/          # Login, Register, Dashboard, Settings, RepoAnalysis
├── components/
│   ├── ui/          # Primitivos (Button, Card, Badge, Tabs, Dialog, Input...)
│   ├── layout/       # Navbar, AppShell, ProtectedRoute
│   ├── charts/       # ScoreGauge, DimensionRadar
│   ├── dashboard/     # SummaryCards
│   ├── repos/         # GithubSummaryPanel
│   └── analysis/      # FindingsList, FindingItem (com "solicitar correção"), SuggestionCard, ReadmePreview...
├── hooks/           # useAuth, useRepos, useAnalysis, useSettings, useDashboard (TanStack Query)
├── store/           # Estado global leve (Zustand)
├── lib/             # Cliente HTTP, armazenamento do token, utilitários
└── types/           # Tipos compartilhados com o backend
```

## Scripts

```bash
npm run dev       # servidor de desenvolvimento
npm run build     # type-check + build de produção
npm run lint       # ESLint
npm run test        # Vitest
```
