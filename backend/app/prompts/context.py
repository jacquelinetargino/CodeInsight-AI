"""Monta o bloco de contexto do repositório (árvore de arquivos + conteúdo)
compartilhado por todos os prompts de análise."""

MAX_CONTEXT_CHARS = 100_000

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
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n\n[...contexto truncado...]"
    return context


JSON_OUTPUT_INSTRUCTIONS = """
Responda APENAS com um JSON válido (sem texto adicional, sem markdown fora do bloco de código),
no seguinte formato:

{
  "score": <inteiro de 0 a 100>,
  "summary": "<resumo objetivo em 2-4 frases, em português>",
  "findings": [
    {
      "title": "<título curto do achado>",
      "description": "<descrição detalhada e acionável>",
      "suggestion": "<sugestão objetiva de como corrigir, ou null>",
      "severity": "<low|medium|high|critical>",
      "file_path": "<caminho do arquivo relacionado, ou null>",
      "line": <número da linha relacionada, ou null se não for possível determinar>
    }
  ]
}

Liste no máximo 8 achados, priorizando os mais relevantes. Se não houver problemas
relevantes na dimensão avaliada, retorne "findings" vazio e um score alto.
"""
