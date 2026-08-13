import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIProvider
from app.ai.factory import get_ai_provider
from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import decrypt_secret
from app.models.analysis import Analysis
from app.models.enums import AnalysisStatus
from app.models.fix_suggestion import FixSuggestion
from app.models.user import User
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.repo_repository import RepoRepository
from app.schemas.analysis import (
    AnalysisCreateRequest,
    AnalysisDetailRead,
    AnalysisRead,
    FixRequest,
    FixSuggestionRead,
)
from app.services import analysis_service, github_service
from app.tasks.analysis_tasks import run_repository_analysis

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("", response_model=AnalysisRead, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")
async def create_analysis(
    request: Request,
    payload: AnalysisCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Analysis:
    repo = await RepoRepository(db).get_owned(payload.repository_id, current_user.id)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repositório não encontrado")

    analysis = await AnalysisRepository(db).create(repository_id=payload.repository_id)
    await db.commit()
    await db.refresh(analysis)

    background_tasks.add_task(run_repository_analysis, analysis.id)
    return analysis


@router.get("", response_model=list[AnalysisRead])
async def list_analyses(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Analysis]:
    repo = await RepoRepository(db).get_owned(repository_id, current_user.id)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repositório não encontrado")
    return await AnalysisRepository(db).list_by_repository(repository_id)


@router.get("/{analysis_id}", response_model=AnalysisDetailRead)
async def get_analysis(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    analysis = await AnalysisRepository(db).get_owned_detail(analysis_id, current_user.id)
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análise não encontrada")
    return {
        **AnalysisRead.model_validate(analysis).model_dump(),
        "results": analysis.results,
        "suggestions": analysis.suggestions,
        "fix_suggestions": analysis.fix_suggestions,
        "has_readme": analysis.readme is not None,
    }


async def _get_done_analysis_with_access_token(
    db: AsyncSession, analysis_id: uuid.UUID, user: User
) -> tuple[Analysis, str | None]:
    analysis = await AnalysisRepository(db).get_owned_detail(analysis_id, user.id)
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análise não encontrada")
    if analysis.status != AnalysisStatus.DONE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A análise ainda não foi concluída")

    credential = analysis.repository.user.github_credential
    user_token = decrypt_secret(credential.token_encrypted) if credential else None
    access_token = github_service.resolve_access_token(user_token)
    return analysis, access_token


@router.post("/{analysis_id}/readme")
async def generate_readme(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai_provider: AIProvider = Depends(get_ai_provider),
) -> dict:
    analysis, access_token = await _get_done_analysis_with_access_token(
        db, analysis_id, current_user
    )
    repository = analysis.repository

    files = await github_service.collect_repository_context(
        access_token, repository.full_name, repository.default_branch
    )

    readme = await analysis_service.generate_and_persist_readme(
        db, analysis, repository.full_name, files, ai_provider
    )
    await db.commit()
    return {"content": readme.content}


@router.get("/{analysis_id}/readme")
async def get_readme(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    analysis = await AnalysisRepository(db).get_owned_detail(analysis_id, current_user.id)
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análise não encontrada")
    if analysis.readme is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "README ainda não foi gerado para esta análise"
        )
    return {"content": analysis.readme.content}


@router.post(
    "/{analysis_id}/fix", response_model=FixSuggestionRead, status_code=status.HTTP_201_CREATED
)
@limiter.limit("20/minute")
async def request_finding_fix(
    request: Request,
    analysis_id: uuid.UUID,
    payload: FixRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ai_provider: AIProvider = Depends(get_ai_provider),
) -> FixSuggestion:
    """Gera uma correção sob demanda para UM achado específico. Nunca escreve
    de volta no repositório — o resultado é só exibido para o usuário decidir."""
    analysis, access_token = await _get_done_analysis_with_access_token(
        db, analysis_id, current_user
    )

    file_content = None
    if payload.file_path:
        file_content = await github_service.get_file_content(
            access_token, analysis.repository.full_name, payload.file_path
        )

    fix_row = await analysis_service.generate_and_persist_fix(
        db,
        analysis,
        title=payload.title,
        description=payload.description,
        file_path=payload.file_path,
        line=payload.line,
        file_content=file_content,
        ai_provider=ai_provider,
    )
    await db.commit()
    await db.refresh(fix_row)
    return fix_row
