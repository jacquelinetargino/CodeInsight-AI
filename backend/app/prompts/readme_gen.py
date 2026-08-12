from app.prompts.context import format_repo_context

SYSTEM_PROMPT = """Você é um redator técnico sênior. Gere um README.md completo e profissional
para o repositório fornecido, em português, seguindo boas práticas de open source:
título, badges (placeholders), descrição, principais funcionalidades, stack tecnológica,
instruções de instalação/execução, estrutura de pastas, como contribuir e licença.
Baseie-se apenas no que puder inferir do código/arquivos fornecidos — não invente
funcionalidades que não existem. Responda APENAS com o conteúdo em markdown do README,
sem comentários adicionais fora dele."""


def build_user_prompt(full_name: str, files: dict[str, str]) -> str:
    context = format_repo_context(full_name, files)
    return f"Gere um README.md para este repositório.\n\n{context}"
