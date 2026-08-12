# Contribuindo para o CodeInsight AI

Obrigado pelo interesse em contribuir! Este documento explica como propor mudanças.

## Antes de começar

1. Verifique se já não existe uma issue ou PR abordando a mesma coisa.
2. Para mudanças grandes ou que alterem comportamento existente, abra uma issue
   descrevendo a proposta antes de implementar — evita retrabalho.
3. Bugs de segurança **não** devem ser reportados como issue pública — veja
   [`SECURITY.md`](SECURITY.md).

## Configurando o ambiente de desenvolvimento

Veja [`docs/development.md`](docs/development.md) para o passo a passo completo
(com e sem Docker).

Resumo rápido:

```bash
cp .env.example .env
# preencha AI_API_KEY (e opcionalmente GITHUB_TOKEN) no .env
docker compose up --build
```

## Fluxo de contribuição

1. Faça um fork do repositório e crie uma branch a partir de `main`:
   `git checkout -b feat/minha-mudanca` (ou `fix/`, `docs/`, `chore/`, conforme o caso).
2. Faça as mudanças, seguindo o estilo de código do projeto (veja abaixo).
3. Adicione/atualize testes cobrindo a mudança.
4. Rode lint e testes localmente antes de abrir o PR:

   ```bash
   # backend
   cd backend && ruff check . && black --check . && pytest --cov=app

   # frontend
   cd frontend && npm run lint && npm run build && npm run test
   ```

5. Escreva mensagens de commit claras, no imperativo (`fix: corrige X`, `feat: adiciona Y`).
6. Abra o Pull Request descrevendo o quê e o porquê da mudança, e como testá-la.

## Estilo de código

- **Backend**: Python 3.12, type hints em tudo, `ruff` + `black` para lint/formatação,
  Pydantic para validação, `async`/`await` em toda a camada de I/O. Regras de acesso a
  dados vivem em `app/repositories/`, lógica de negócio em `app/services/` — evite
  consultas SQL soltas dentro das rotas.
- **Frontend**: TypeScript estrito, componentes funcionais, TanStack Query para dados
  do servidor, Tailwind para estilo (evite CSS solto).
- **IA**: nenhum código fora de `app/ai/` deve importar um SDK de IA específico
  (`anthropic`, `openai`, `google.generativeai`) diretamente — sempre passe pela
  interface `AIProvider`. Veja [`docs/ai-providers.md`](docs/ai-providers.md).

## Testes

- Testes de backend não devem depender de credenciais reais de IA/GitHub — use os
  helpers de mock já existentes em `tests/conftest.py` (`ScriptedAIProvider`,
  `monkeypatch` no `github_service`).
- PRs que adicionam um endpoint novo devem incluir pelo menos um teste de integração
  cobrindo o caminho feliz e um caso de erro (404/401/400, conforme aplicável).

## Dúvidas

Abra uma issue com a tag `question` ou comece uma discussão no repositório.
