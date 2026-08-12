from app.prompts.context import JSON_OUTPUT_INSTRUCTIONS, format_repo_context

SYSTEM_PROMPT = """Você é um engenheiro de software sênior especializado em qualidade de código.
Avalie legibilidade, complexidade, duplicação, convenções de nomenclatura, tratamento de erros,
cobertura de testes aparente e aderência a boas práticas da linguagem/framework usados.
Seja específico e cite arquivos reais do contexto fornecido.""" + JSON_OUTPUT_INSTRUCTIONS


def build_user_prompt(full_name: str, files: dict[str, str]) -> str:
    context = format_repo_context(full_name, files)
    return f"Analise a QUALIDADE DE CÓDIGO do repositório a seguir.\n\n{context}"
