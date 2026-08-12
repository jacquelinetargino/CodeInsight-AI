from app.prompts.context import JSON_OUTPUT_INSTRUCTIONS, format_repo_context

SYSTEM_PROMPT = (
    """Você é um engenheiro de QA sênior. Avalie a estratégia de testes do
repositório: existência e organização de testes (unitários/integração/e2e), uso de um
framework de testes reconhecível, presença de configuração de cobertura, se os testes
parecem cobrir os caminhos principais (com base nos nomes/estrutura de arquivos e no
conteúdo disponível) e se há integração de testes no CI (ex.: GitHub Actions).
Baseie-se apenas em evidências do contexto fornecido — não presuma cobertura que não
possa ser inferida."""
    + JSON_OUTPUT_INSTRUCTIONS
)


def build_user_prompt(full_name: str, files: dict[str, str]) -> str:
    context = format_repo_context(full_name, files)
    return f"Analise a ESTRATÉGIA DE TESTES do repositório a seguir.\n\n{context}"
