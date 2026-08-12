import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GithubRepoOut(BaseModel):
    """Repositório vindo diretamente da GitHub API (usado na listagem 'meus
    repositórios', disponível só quando o usuário conectou um PAT)."""

    github_repo_id: int
    full_name: str
    description: str | None = None
    default_branch: str = "main"
    private: bool = False
    stargazers_count: int = 0
    language: str | None = None
    updated_at: datetime | None = None


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    github_repo_id: int
    full_name: str
    description: str | None
    default_branch: str
    private: bool
    last_synced_at: datetime | None
    created_at: datetime


class RepositoryAddRequest(BaseModel):
    """Aceita 'owner/repo' ou a URL completa do repositório."""

    repo: str


class CommitSummary(BaseModel):
    sha: str
    message: str
    author: str | None
    date: datetime | None


class IssueSummary(BaseModel):
    number: int
    title: str
    state: str
    created_at: datetime


class PullRequestSummary(BaseModel):
    number: int
    title: str
    state: str
    created_at: datetime
    merged_at: datetime | None = None


class ContributorSummary(BaseModel):
    username: str
    avatar_url: str | None
    contributions: int


class BranchSummary(BaseModel):
    name: str
    protected: bool = False


class GithubRepoSummary(BaseModel):
    """Dados ricos do repositório, buscados ao vivo na GitHub API (não persistidos)."""

    languages: dict[str, int]
    branches: list[BranchSummary]
    recent_commits: list[CommitSummary]
    issues: list[IssueSummary]
    pull_requests: list[PullRequestSummary]
    contributors: list[ContributorSummary]
