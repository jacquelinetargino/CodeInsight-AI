from app.prompts.context import JSON_OUTPUT_INSTRUCTIONS, format_repo_context

SYSTEM_PROMPT = (
    """Você é um redator técnico especializado em documentação de software.
Avalie a qualidade do README (existência, clareza de instalação/uso/exemplos), presença de
comentários úteis no código, documentação de API, CONTRIBUTING/LICENSE, e se um novo
desenvolvedor conseguiria entender e rodar o projeto apenas com a documentação disponível."""
    + JSON_OUTPUT_INSTRUCTIONS
)


def build_user_prompt(full_name: str, files: dict[str, str]) -> str:
    context = format_repo_context(full_name, files)
    return f"Analise a DOCUMENTAÇÃO do repositório a seguir.\n\n{context}"
