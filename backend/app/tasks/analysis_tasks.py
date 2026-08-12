import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.ai.factory import get_ai_provider
from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_secret
from app.models.analysis import Analysis
from app.models.enums import AnalysisStatus, Dimension
from app.models.repository import Repository
from app.services import analysis_service, github_service
from app.services.analysis_service import DIMENSION_MODULES

logger = logging.getLogger(__name__)


@celery_app.task(name="run_repository_analysis", bind=True, max_retries=1)
def run_repository_analysis(self, analysis_id: str) -> None:
    asyncio.run(_run_repository_analysis(uuid.UUID(analysis_id)))


async def _run_repository_analysis(analysis_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        analysis = await db.get(Analysis, analysis_id)
        if analysis is None:
            logger.error("Analysis %s não encontrada", analysis_id)
            return

        try:
            repository = await db.get(Repository, analysis.repository_id)
            await db.refresh(repository, attribute_names=["user"])
            await db.refresh(repository.user, attribute_names=["github_credential"])

            credential = repository.user.github_credential
            user_token = decrypt_secret(credential.token_encrypted) if credential else None
            access_token = github_service.resolve_access_token(user_token)

            analysis.status = AnalysisStatus.RUNNING
            await db.commit()

            files = await github_service.collect_repository_context(
                access_token, repository.full_name, repository.default_branch
            )
            files["__git_activity__"] = await github_service.collect_git_activity_summary(
                access_token, repository.full_name
            )

            ai_provider = get_ai_provider()
            scores: dict[Dimension, int] = {}
            findings_by_dimension: dict[str, list[dict]] = {}

            for dimension in DIMENSION_MODULES:
                result = await analysis_service.run_dimension_analysis(
                    dimension, repository.full_name, files, ai_provider
                )
                await analysis_service.persist_dimension_result(db, analysis, dimension, result)
                scores[dimension] = int(result.get("score", 0))
                findings_by_dimension[dimension.value] = result.get("findings", [])

            await analysis_service.generate_and_persist_suggestions(
                db, analysis, repository.full_name, findings_by_dimension, ai_provider
            )

            analysis.overall_score = analysis_service.compute_overall_score(scores)
            analysis.status = AnalysisStatus.DONE
            analysis.finished_at = datetime.now(timezone.utc)
            repository.last_synced_at = datetime.now(timezone.utc)
            await db.commit()

        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha ao analisar repositório %s", analysis_id)
            analysis.status = AnalysisStatus.FAILED
            analysis.error_message = str(exc)[:2000]
            analysis.finished_at = datetime.now(timezone.utc)
            await db.commit()
