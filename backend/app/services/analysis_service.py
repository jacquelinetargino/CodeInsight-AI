"""Orquestra o pipeline de análise: coleta de contexto do GitHub, chamadas ao
provedor de IA configurado para cada dimensão, agregação de score e
persistência dos resultados.

Este módulo depende só da interface `AIProvider` (injetada pelo chamador,
tipicamente via `app.ai.factory.get_ai_provider()`) — nunca de um SDK de IA
específico.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIProvider
from app.engine.scoring import DIMENSION_WEIGHTS as ENGINE_DIMENSION_WEIGHTS
from app.models.analysis import Analysis, AnalysisResult
from app.models.enums import Dimension
from app.models.fix_suggestion import FixSuggestion
from app.models.readme import GeneratedReadme
from app.models.suggestion import Suggestion
from app.prompts import architecture, documentation, fix, git_health, quality, readme_gen, security
from app.prompts import suggestions as suggestions_prompt
from app.prompts import tests as tests_prompt

# Caminho LEGADO: as dimensões que um provedor de IA sabe analisar por prompt.
# É um subconjunto de `Dimension` — `dependencies` e `configuration` existem só
# no motor, que não usa IA. Não é lacuna: é o motor cobrindo mais que os prompts.
DIMENSION_MODULES = {
    Dimension.QUALITY: quality,
    Dimension.SECURITY: security,
    Dimension.ARCHITECTURE: architecture,
    Dimension.DOCUMENTATION: documentation,
    Dimension.TESTING: tests_prompt,
    Dimension.GIT: git_health,
}

# Fonte única dos pesos: o motor. Duplicar a tabela aqui deixaria os dois
# caminhos discordando sobre o mesmo repositório sem ninguém perceber.
DIMENSION_WEIGHTS = {
    Dimension(categoria.value): peso for categoria, peso in ENGINE_DIMENSION_WEIGHTS.items()
}


async def run_dimension_analysis(
    dimension: Dimension, full_name: str, files: dict[str, str], ai_provider: AIProvider
) -> dict:
    module = DIMENSION_MODULES[dimension]
    user_prompt = module.build_user_prompt(full_name, files)
    result = await ai_provider.generate_json(module.SYSTEM_PROMPT, user_prompt)
    if not isinstance(result, dict):
        raise ValueError(f"Resposta inesperada do provedor de IA para dimensão {dimension}")
    return result


def compute_overall_score(scores: dict[Dimension, int]) -> float:
    total_weight = sum(DIMENSION_WEIGHTS[d] for d in scores)
    weighted = sum(scores[d] * DIMENSION_WEIGHTS[d] for d in scores)
    return round(weighted / total_weight, 1) if total_weight else 0.0


async def persist_dimension_result(
    db: AsyncSession, analysis: Analysis, dimension: Dimension, result: dict
) -> AnalysisResult:
    row = AnalysisResult(
        analysis_id=analysis.id,
        dimension=dimension,
        score=int(result.get("score", 0)),
        summary=result.get("summary", ""),
        findings=result.get("findings", []),
    )
    db.add(row)
    return row


async def generate_and_persist_suggestions(
    db: AsyncSession,
    analysis: Analysis,
    full_name: str,
    findings_by_dimension: dict[str, list[dict]],
    ai_provider: AIProvider,
) -> list[Suggestion]:
    user_prompt = suggestions_prompt.build_user_prompt(full_name, findings_by_dimension)
    result = await ai_provider.generate_json(
        suggestions_prompt.SYSTEM_PROMPT, user_prompt, max_tokens=6000
    )
    items = result.get("suggestions", []) if isinstance(result, dict) else []

    rows = []
    for item in items:
        row = Suggestion(
            analysis_id=analysis.id,
            title=item.get("title", "Sugestão"),
            description=item.get("description", ""),
            severity=item.get("severity", "medium"),
            file_path=item.get("file_path"),
            code_fix=item.get("code_fix"),
        )
        db.add(row)
        rows.append(row)
    return rows


async def generate_and_persist_readme(
    db: AsyncSession,
    analysis: Analysis,
    full_name: str,
    files: dict[str, str],
    ai_provider: AIProvider,
) -> GeneratedReadme:
    user_prompt = readme_gen.build_user_prompt(full_name, files)
    content = await ai_provider.generate_text(
        readme_gen.SYSTEM_PROMPT, user_prompt, max_tokens=6000
    )

    readme = GeneratedReadme(analysis_id=analysis.id, content=content.strip())
    db.add(readme)
    return readme


async def generate_and_persist_fix(
    db: AsyncSession,
    analysis: Analysis,
    *,
    title: str,
    description: str,
    file_path: str | None,
    line: int | None,
    file_content: str | None,
    ai_provider: AIProvider,
) -> FixSuggestion:
    """Gera uma correção para UM achado específico, sob demanda. Nunca é
    aplicada no repositório — só fica disponível para o usuário revisar."""
    user_prompt = fix.build_user_prompt(title, description, file_path, line, file_content)
    result = await ai_provider.generate_json(fix.SYSTEM_PROMPT, user_prompt, max_tokens=3000)
    if not isinstance(result, dict):
        raise ValueError("Resposta inesperada do provedor de IA ao gerar a correção")

    fix_row = FixSuggestion(
        analysis_id=analysis.id,
        file_path=file_path,
        line=line,
        current_code=result.get("current_code", ""),
        suggested_code=result.get("suggested_code", ""),
        explanation=result.get("explanation", ""),
    )
    db.add(fix_row)
    return fix_row
