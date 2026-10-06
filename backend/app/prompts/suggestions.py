import json

from app.core.config import get_settings

SYSTEM_PROMPT = """Você é um engenheiro de software sênior responsável por transformar achados
de uma análise automatizada em um plano de ação priorizado. Para cada achado relevante,
proponha uma sugestão de melhoria clara e, quando fizer sentido (bugs, problemas de segurança,
más práticas pontuais), um "code_fix" no formato de diff unificado (```diff) mostrando a
correção sugerida para o trecho relevante. Não é necessário propor code_fix para sugestões
arquiteturais amplas.

Responda APENAS com um JSON válido no formato:
{
  "suggestions": [
    {
      "title": "<título curto>",
      "description": "<explicação da melhoria e por que ela importa>",
      "severity": "<low|medium|high|critical>",
      "file_path": "<arquivo relacionado ou null>",
      "code_fix": "<diff unificado em texto, ou null>"
    }
  ]
}

Priorize no máximo 10 sugestões, das mais impactantes para as menos impactantes.
"""


def build_user_prompt(full_name: str, dimension_findings: dict[str, list[dict]]) -> str:
    findings_json = json.dumps(dimension_findings, ensure_ascii=False, indent=2)
    # Mesmo teto do contexto de repositório (ver `context.py`): um repositório
    # com centenas de achados gerava um prompt sem limite, que planos com teto
    # de tokens por minuto (ex.: Groq gratuito) recusam inteiro.
    max_chars = get_settings().ai_max_context_chars
    if len(findings_json) > max_chars:
        findings_json = findings_json[:max_chars] + "\n\n[...achados truncados...]"
    return (
        f"Repositório: {full_name}\n\n"
        f"Achados consolidados por dimensão (segurança, qualidade, arquitetura, documentação):\n"
        f"{findings_json}\n\n"
        "Gere as sugestões de melhoria priorizadas conforme instruído."
    )
