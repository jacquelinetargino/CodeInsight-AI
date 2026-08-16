"""Executa a análise de um repositório em segundo plano.

O CodeInsight Engine é o motor: ele produz todos os achados e todo o score, sem
provedor de IA, sem chave de API e sem crédito em serviço externo.

A IA entra depois e é **estritamente opcional** — se houver provedor
configurado, ela gera sugestões a partir dos achados que o motor já encontrou.
Sem provedor, a análise termina completa do mesmo jeito; só as sugestões não
saem. Falha na etapa de IA não invalida a análise.
"""

import logging
import uuid
from datetime import UTC, datetime

from app.ai.factory import get_optional_ai_provider
from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_secret
from app.engine.pipeline import EngineReport, analyze_repository
from app.models.analysis import Analysis, AnalysisResult
from app.models.enums import AnalysisStatus, Dimension
from app.models.repository import Repository
from app.services import analysis_service, github_service

logger = logging.getLogger(__name__)


def _summary(resultado, dimensao: Dimension) -> str:
    """Resumo textual da dimensão, montado a partir dos próprios achados.

    Sem IA: descrever o que foi contado não exige um modelo de linguagem. As
    notas do analyzer entram no resumo porque dizem o que **não** foi avaliado —
    a informação que um resumo omisso esconderia.
    """
    if not resultado.findings:
        base = "Nenhum problema encontrado nesta dimensão."
    else:
        por_severidade: dict[str, int] = {}
        for achado in resultado.findings:
            chave = achado.severity.value
            por_severidade[chave] = por_severidade.get(chave, 0) + 1
        detalhe = ", ".join(
            f"{quantidade} {rotulo}"
            for rotulo, quantidade in (
                ("crítico(s)", por_severidade.get("critical", 0)),
                ("alto(s)", por_severidade.get("high", 0)),
                ("médio(s)", por_severidade.get("medium", 0)),
                ("baixo(s)", por_severidade.get("low", 0)),
            )
            if quantidade
        )
        base = f"{len(resultado.findings)} achado(s): {detalhe}."

    return " ".join([base, *resultado.notes])


async def _persist_report(db, analysis: Analysis, report: EngineReport) -> dict[str, list[dict]]:
    """Grava uma linha por dimensão avaliada e devolve os achados por dimensão.

    Dimensão não avaliada não vira linha com score zero: gravar um veredito que
    o motor não emitiu seria inventar dado.
    """
    achados_por_dimensao: dict[str, list[dict]] = {}

    for resultado in report.results:
        dimensao = Dimension(resultado.category.value)
        pontuacao = report.score.dimension(resultado.category)
        if pontuacao is None or pontuacao.score is None:
            continue

        db.add(
            AnalysisResult(
                analysis_id=analysis.id,
                dimension=dimensao,
                score=pontuacao.score,
                summary=_summary(resultado, dimensao),
                findings=[f.to_legacy_dict() for f in resultado.findings],
            )
        )
        achados_por_dimensao[dimensao.value] = [f.to_legacy_dict() for f in resultado.findings]

    return achados_por_dimensao


async def run_repository_analysis(analysis_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        analysis = await db.get(Analysis, analysis_id)
        if analysis is None:
            logger.error("Analysis %s não encontrada", analysis_id)
            return

        try:
            repository = await db.get(Repository, analysis.repository_id)
            if repository is None:
                # Repositório removido entre o enfileiramento e a execução.
                # Sem isto, a linha seguinte quebraria com AttributeError e o
                # usuário veria "NoneType" em vez do que de fato aconteceu.
                raise RuntimeError(
                    "O repositório desta análise não existe mais. Cadastre-o novamente."
                )

            await db.refresh(repository, attribute_names=["user"])
            await db.refresh(repository.user, attribute_names=["github_credential"])

            credential = repository.user.github_credential
            user_token = decrypt_secret(credential.token_encrypted) if credential else None
            access_token = github_service.resolve_access_token(user_token)

            analysis.status = AnalysisStatus.RUNNING
            await db.commit()

            metadata = await github_service.get_repository(access_token, repository.full_name)
            activity = await github_service.build_git_activity(
                access_token, repository.full_name, repository.default_branch or "main"
            )

            report = await analyze_repository(
                access_token,
                repository.full_name,
                repository.default_branch or "main",
                declared_size_kb=metadata.get("size"),
                activity=activity,
            )

            achados_por_dimensao = await _persist_report(db, analysis, report)

            analysis.overall_score = report.score.overall
            analysis.status = AnalysisStatus.DONE
            analysis.finished_at = datetime.now(UTC)
            repository.last_synced_at = datetime.now(UTC)
            await db.commit()

            await _enrich_with_ai(db, analysis, repository.full_name, achados_por_dimensao)

        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha ao analisar repositório %s", analysis_id)
            analysis.status = AnalysisStatus.FAILED
            analysis.error_message = str(exc)[:2000]
            analysis.finished_at = datetime.now(UTC)
            await db.commit()


async def _enrich_with_ai(
    db, analysis: Analysis, full_name: str, achados_por_dimensao: dict[str, list[dict]]
) -> None:
    """Sugestões geradas por IA, quando houver provedor configurado.

    Roda **depois** de a análise já estar gravada como concluída, e qualquer
    falha aqui é registrada sem alterar o status: a análise do motor está
    completa e não deve ser marcada como falha porque um serviço externo
    recusou uma chamada.
    """
    ai_provider = get_optional_ai_provider()
    if ai_provider is None:
        logger.info("Análise %s concluída sem sugestões: nenhum provedor de IA.", analysis.id)
        return

    try:
        await analysis_service.generate_and_persist_suggestions(
            db, analysis, full_name, achados_por_dimensao, ai_provider
        )
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Sugestões por IA falharam para a análise %s", analysis.id)
        await db.rollback()
