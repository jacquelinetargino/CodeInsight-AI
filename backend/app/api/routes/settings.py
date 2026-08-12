import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import encrypt_secret
from app.models.user import User
from app.repositories.github_credential_repository import GithubCredentialRepository
from app.schemas.settings import GithubTokenStatus, GithubTokenUpdateRequest
from app.services import github_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/github-token", response_model=GithubTokenStatus)
async def get_github_token_status(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> GithubTokenStatus:
    credential = await GithubCredentialRepository(db).get_by_user_id(current_user.id)
    return GithubTokenStatus(connected=credential is not None)


@router.put("/github-token", response_model=GithubTokenStatus)
async def set_github_token(
    payload: GithubTokenUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GithubTokenStatus:
    try:
        await github_service.get_authenticated_user(payload.token)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Token do GitHub inválido ou sem permissão"
        ) from exc

    await GithubCredentialRepository(db).upsert(
        user_id=current_user.id, token_encrypted=encrypt_secret(payload.token)
    )
    await db.commit()
    return GithubTokenStatus(connected=True)


@router.delete("/github-token", response_model=GithubTokenStatus)
async def delete_github_token(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> GithubTokenStatus:
    await GithubCredentialRepository(db).delete(current_user.id)
    await db.commit()
    return GithubTokenStatus(connected=False)
