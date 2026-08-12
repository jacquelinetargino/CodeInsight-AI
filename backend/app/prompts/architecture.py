from app.prompts.context import JSON_OUTPUT_INSTRUCTIONS, format_repo_context

SYSTEM_PROMPT = (
    """Você é um arquiteto de software experiente.
Avalie a organização de pastas/módulos, separação de responsabilidades, acoplamento entre
camadas, uso de padrões arquiteturais apropriados, escalabilidade da estrutura e consistência
entre os componentes do projeto (frontend/backend/infra, quando aplicável)."""
    + JSON_OUTPUT_INSTRUCTIONS
)


def build_user_prompt(full_name: str, files: dict[str, str]) -> str:
    context = format_repo_context(full_name, files)
    return f"Analise a ARQUITETURA do repositório a seguir.\n\n{context}"
