"""Monta o bloco de contexto do repositório (árvore de arquivos + conteúdo)
compartilhado por todos os prompts de análise."""

from app.core.config import get_settings

# Chaves reservadas em `files` que não são conteúdo de arquivo (ex.: a própria
# árvore de arquivos, ou dados de atividade git usados só pelo prompt de git).
RESERVED_KEYS = {"__file_tree__", "__git_activity__"}


def format_repo_context(full_name: str, files: dict[str, str]) -> str:
    file_tree = files.get("__file_tree__", "")
    parts = [
        f"Repositório: {full_name}",
        "",
        "Árvore de arquivos:",
        file_tree,
        "",
        "Conteúdo dos arquivos:",
    ]

    for path, content in files.items():
        if path in RESERVED_KEYS:
            continue
        parts.append(f"\n--- {path} ---\n{content}")

    context = "\n".join(parts)
    max_chars = get_settings().ai_max_context_chars
    if len(context) > max_chars:
        context = context[:max_chars] + "\n\n[...contexto truncado...]"
    return context
