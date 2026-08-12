from app.prompts.context import JSON_OUTPUT_INSTRUCTIONS, format_repo_context

SYSTEM_PROMPT = """Você é um especialista em segurança de aplicações (AppSec).
Avalie o repositório em busca de: credenciais/segredos hardcoded, dependências com
vulnerabilidades conhecidas (pelo nome/versão), padrões inseguros (injeção, XSS, SSRF,
deserialização insegura), configurações inseguras (CORS aberto, containers rodando como
root, falta de validação de entrada) e exposição desnecessária de dados sensíveis.
Baseie-se apenas em evidências do código/arquivos fornecidos.""" + JSON_OUTPUT_INSTRUCTIONS


def build_user_prompt(full_name: str, files: dict[str, str]) -> str:
    context = format_repo_context(full_name, files)
    return f"Analise a SEGURANÇA do repositório a seguir.\n\n{context}"
