SYSTEM_PROMPT = """Você é um engenheiro de software sênior. Dado um problema específico
identificado numa análise de código e o conteúdo do arquivo relacionado (quando disponível),
produza uma correção concreta e mínima para esse problema específico — não refatore o
arquivo inteiro.

Responda APENAS com um JSON válido no formato:
{
  "current_code": "<trecho atual relevante, o mais próximo possível do original>",
  "suggested_code": "<trecho corrigido, pronto para substituir o atual>",
  "explanation": "<explicação objetiva da mudança e por que ela resolve o problema, em português>"
}

Se o conteúdo do arquivo não for suficiente para localizar o trecho exato, baseie
"current_code" na melhor evidência disponível e deixe isso claro na explicação. Nunca
inclua marcações de diff (+/-) — apenas o código em si.
"""


def build_user_prompt(
    title: str, description: str, file_path: str | None, line: int | None, file_content: str | None
) -> str:
    parts = [f"Problema: {title}", f"Descrição: {description}"]
    if file_path:
        parts.append(f"Arquivo: {file_path}")
    if line:
        parts.append(f"Linha aproximada: {line}")

    if file_content:
        parts.append(f"\nConteúdo atual do arquivo:\n{file_content[:20_000]}")
    else:
        parts.append("\n(Conteúdo do arquivo não disponível — baseie-se na descrição do problema.)")

    return "\n".join(parts)
