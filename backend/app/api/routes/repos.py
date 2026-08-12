import asyncio
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import decrypt_secret
from app.models.repository import Repository
from app.models.user import User
from app.repositories.github_credential_repository import GithubCredentialRepository
from app.repositories.repo_repository import RepoRepository
from app.schemas.repository import (
    BranchSummary,
    CommitSummary,
    ContributorSummary,
    GithubRepoOut,
    GithubRepoSummary,
    IssueSummary,
    PullRequestSummary,
    RepositoryAddRequest,
    RepositoryRead,
)
from app.services import github_service

router = APIRouter(prefix="/repos", tags=["repositories"])


async def _get_user_access_token(db: AsyncSession, user: User) -> str | None:
    """PAT do usuário (se conectado) ou o fallback do servidor — nunca exige
    conexão para repositórios públicos."""
    credential = await GithubCredentialRepository(db).get_by_user_id(user.id)
    user_token = decrypt_secret(credential.token_encrypted) if credential else None
    return github_service.resolve_access_token(user_token)


@router.get("/github/mine", response_model=list[GithubRepoOut])
async def list_my_github_repositories(
    page: int = 1,
    per_page: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Lista os repositórios do GitHub do usuário — requer um PAT conectado em Configurações."""
    credential = await GithubCredentialRepository(db).get_by_user_id(current_user.id)
    if credential is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Conecte um Personal Access Token do GitHub em Configurações "
            "para listar seus repositórios.",
        )

    access_token = decrypt_secret(credential.token_encrypted)
    repos = await github_service.list_user_repositories(access_token, page=page, per_page=per_page)
    return [
        {
            "github_repo_id": r["id"],
            "full_name": r["full_name"],
            "description": r.get("description"),
            "default_branch": r.get("default_branch", "main"),
            "private": r.get("private", False),
            "stargazers_count": r.get("stargazers_count", 0),
            "language": r.get("language"),
            "updated_at": r.get("updated_at"),
        }
        for r in repos
    ]


@router.get("", response_model=list[RepositoryRead])
async def list_imported_repositories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Repository]:
    return await RepoRepository(db).list_by_user(current_user.id)


@router.post("", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED)
async def add_repository(
    payload: RepositoryAddRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Repository:
    """Adiciona um repositório informando 'owner/repo' ou a URL do GitHub.
    Não requer PAT — funciona para qualquer repositório público."""
    repos = RepoRepository(db)

    try:
        full_name = github_service.resolve_repo_full_name(payload.repo)
    except github_service.InvalidRepositoryReferenceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    existing = await repos.get_by_full_name(current_user.id, full_name)
    if existing:
        return existing

    access_token = await _get_user_access_token(db, current_user)
    try:
        data = await github_service.get_repository(access_token, full_name)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Repositório '{full_name}' não encontrado (ou é privado e você não tem acesso).",
            ) from exc
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Falha ao consultar a GitHub API") from exc

    repo = await repos.create(
        user_id=current_user.id,
        github_repo_id=data["id"],
        full_name=data["full_name"],
        description=data.get("description"),
        default_branch=data.get("default_branch", "main"),
        private=data.get("private", False),
    )
    await db.commit()
    await db.refresh(repo)
    return repo


@router.get("/{repository_id}", response_model=RepositoryRead)
async def get_repository_detail(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Repository:
    repo = await RepoRepository(db).get_owned(repository_id, current_user.id)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repositório não encontrado")
    return repo


@router.get("/{repository_id}/github-summary", response_model=GithubRepoSummary)
async def get_github_summary(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GithubRepoSummary:
    """Dados ricos do repositório (linguagens, branches, commits, issues, PRs,
    contributors), buscados ao vivo na GitHub API — não são persistidos."""
    repo = await RepoRepository(db).get_owned(repository_id, current_user.id)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repositório não encontrado")

    access_token = await _get_user_access_token(db, current_user)

    try:
        languages, branches, commits, issues, pulls, contributors = await asyncio.gather(
            github_service.get_languages(access_token, repo.full_name),
            github_service.list_branches(access_token, repo.full_name),
            github_service.list_commits(access_token, repo.full_name),
            github_service.list_issues(access_token, repo.full_name),
            github_service.list_pull_requests(access_token, repo.full_name),
            github_service.list_contributors(access_token, repo.full_name),
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Falha ao consultar a GitHub API") from exc

    return GithubRepoSummary(
        languages=languages,
        branches=[
            BranchSummary(name=b["name"], protected=b.get("protected", False)) for b in branches
        ],
        recent_commits=[
            CommitSummary(
                sha=c["sha"][:7],
                message=c["commit"]["message"].splitlines()[0],
                author=(c.get("author") or {}).get("login") or c["commit"]["author"]["name"],
                date=c["commit"]["author"]["date"],
            )
            for c in commits
        ],
        issues=[
            IssueSummary(
                number=i["number"], title=i["title"], state=i["state"], created_at=i["created_at"]
            )
            for i in issues
        ],
        pull_requests=[
            PullRequestSummary(
                number=p["number"],
                title=p["title"],
                state=p["state"],
                created_at=p["created_at"],
                merged_at=p.get("merged_at"),
            )
            for p in pulls
        ],
        contributors=[
            ContributorSummary(
                username=c["login"],
                avatar_url=c.get("avatar_url"),
                contributions=c.get("contributions", 0),
            )
            for c in contributors
        ],
    )
