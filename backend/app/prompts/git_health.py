from app.prompts.context import JSON_OUTPUT_INSTRUCTIONS, format_repo_context

SYSTEM_PROMPT = """Você é um engenheiro sênior avaliando a saúde do histórico Git de um
repositório. Avalie a qualidade das mensagens de commit (clareza, padrão como Conventional
Commits, tamanho/atomicidade), a organização de branches, o uso de Pull Requests como
fluxo de trabalho, e a consistência geral da atividade. Baseie-se apenas na atividade git
fornecida (branches, PRs e últimos commits) — não invente histórico que não foi
listado.""" + JSON_OUTPUT_INSTRUCTIONS


def build_user_prompt(full_name: str, files: dict[str, str]) -> str:
    context = format_repo_context(full_name, files)
    git_activity = files.get("__git_activity__", "(sem dados de atividade git disponíveis)")
    return (
        f"Analise a SAÚDE DO HISTÓRICO GIT do repositório a seguir.\n\n"
        f"Atividade git recente:\n{git_activity}\n\n{context}"
    )
