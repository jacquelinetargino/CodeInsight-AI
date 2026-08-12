"""Client fino para a GitHub API (REST v3).

Não há fluxo OAuth: repositórios públicos podem ser analisados sem nenhum
token; um Personal Access Token (PAT) do próprio usuário é opcional e só é
usado quando presente (repositórios privados, rate limit maior). Veja
`resolve_access_token`.
"""

import asyncio
import base64
import re
from typing import Any

import httpx

from app.core.config import get_settings

GITHUB_API_BASE = "https://api.github.com"

# Arquivos priorizados na coleta de contexto para a IA (manifestos, configs, docs
# e também indícios de testes, usados pela dimensão "tests").
KEY_FILE_CANDIDATES = [
    "README.md",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "Dockerfile",
    "docker-compose.yml",
    ".github/workflows",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "composer.json",
    "Gemfile",
    ".env.example",
    "tsconfig.json",
    "SECURITY.md",
    "LICENSE",
    "tests/",
    "test/",
    "__tests__/",
    "spec/",
    "pytest.ini",
    "jest.config",
    "vitest.config",
    ".coveragerc",
    "tox.ini",
]
MAX_FILES_FETCHED = 25
MAX_FILE_SIZE_BYTES = 60_000

_REPO_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$"
)
_OWNER_REPO_RE = re.compile(r"^(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?$")


class GithubAPIError(Exception):
    pass


class InvalidRepositoryReferenceError(GithubAPIError):
    pass


def resolve_repo_full_name(repo_input: str) -> str:
    """Aceita 'owner/repo' ou uma URL do GitHub e retorna sempre 'owner/repo'."""
    value = repo_input.strip()
    match = _REPO_URL_RE.match(value) or _OWNER_REPO_RE.match(value)
    if not match:
        raise InvalidRepositoryReferenceError(
            f"'{repo_input}' não parece um repositório válido do GitHub "
            "(use 'owner/repo' ou a URL)."
        )
    return f"{match.group('owner')}/{match.group('repo')}"


def resolve_access_token(user_token: str | None) -> str | None:
    """PAT do usuário se existir; senão o token opcional do servidor; senão None
    (acesso não autenticado — só funciona para repositórios públicos)."""
    if user_token:
        return user_token
    return get_settings().github_token or None


def _headers(access_token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


async def _get(
    path: str, access_token: str | None, params: dict[str, Any] | None = None
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=20) as client:
        return await client.get(
            f"{GITHUB_API_BASE}{path}", headers=_headers(access_token), params=params
        )


async def get_authenticated_user(access_token: str) -> dict[str, Any]:
    resp = await _get("/user", access_token)
    resp.raise_for_status()
    return resp.json()


async def list_user_repositories(
    access_token: str, page: int = 1, per_page: int = 30
) -> list[dict[str, Any]]:
    resp = await _get(
        "/user/repos",
        access_token,
        params={
            "sort": "updated",
            "per_page": per_page,
            "page": page,
            "affiliation": "owner,collaborator",
        },
    )
    resp.raise_for_status()
    return resp.json()


async def get_repository(access_token: str | None, full_name: str) -> dict[str, Any]:
    resp = await _get(f"/repos/{full_name}", access_token)
    resp.raise_for_status()
    return resp.json()


async def get_languages(access_token: str | None, full_name: str) -> dict[str, int]:
    resp = await _get(f"/repos/{full_name}/languages", access_token)
    resp.raise_for_status()
    return resp.json()


async def list_branches(
    access_token: str | None, full_name: str, limit: int = 20
) -> list[dict[str, Any]]:
    resp = await _get(f"/repos/{full_name}/branches", access_token, params={"per_page": limit})
    resp.raise_for_status()
    return resp.json()


async def list_commits(
    access_token: str | None, full_name: str, limit: int = 20
) -> list[dict[str, Any]]:
    resp = await _get(f"/repos/{full_name}/commits", access_token, params={"per_page": limit})
    resp.raise_for_status()
    return resp.json()


async def list_issues(
    access_token: str | None, full_name: str, limit: int = 20
) -> list[dict[str, Any]]:
    """A rota /issues do GitHub retorna issues E pull requests juntos — filtramos
    fora os PRs (identificáveis pela presença da chave "pull_request")."""
    resp = await _get(
        f"/repos/{full_name}/issues", access_token, params={"state": "all", "per_page": limit}
    )
    resp.raise_for_status()
    return [item for item in resp.json() if "pull_request" not in item]


async def list_pull_requests(
    access_token: str | None, full_name: str, limit: int = 20
) -> list[dict[str, Any]]:
    resp = await _get(
        f"/repos/{full_name}/pulls", access_token, params={"state": "all", "per_page": limit}
    )
    resp.raise_for_status()
    return resp.json()


async def list_contributors(
    access_token: str | None, full_name: str, limit: int = 20
) -> list[dict[str, Any]]:
    resp = await _get(f"/repos/{full_name}/contributors", access_token, params={"per_page": limit})
    if resp.status_code == 204:  # repositório sem commits ainda
        return []
    resp.raise_for_status()
    return resp.json()


async def get_file_tree(
    access_token: str | None, full_name: str, branch: str
) -> list[dict[str, Any]]:
    resp = await _get(
        f"/repos/{full_name}/git/trees/{branch}", access_token, params={"recursive": "1"}
    )
    resp.raise_for_status()
    return resp.json().get("tree", [])


async def get_file_content(access_token: str | None, full_name: str, path: str) -> str | None:
    resp = await _get(f"/repos/{full_name}/contents/{path}", access_token)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if data.get("encoding") != "base64" or "content" not in data:
        return None
    try:
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    except (ValueError, UnicodeDecodeError):
        return None


async def collect_repository_context(
    access_token: str | None, full_name: str, branch: str
) -> dict[str, str]:
    """Coleta a árvore de arquivos + conteúdo dos arquivos mais relevantes,
    respeitando limites de quantidade/tamanho para manter o prompt enxuto."""
    tree = await get_file_tree(access_token, full_name, branch)
    file_paths = [item["path"] for item in tree if item.get("type") == "blob"]

    prioritized = [
        p for p in file_paths if any(p == c or p.startswith(c) for c in KEY_FILE_CANDIDATES)
    ]
    remaining = [p for p in file_paths if p not in prioritized]
    selected = (prioritized + remaining)[:MAX_FILES_FETCHED]

    contents: dict[str, str] = {}
    for path in selected:
        content = await get_file_content(access_token, full_name, path)
        if content is not None:
            contents[path] = content[:MAX_FILE_SIZE_BYTES]

    contents["__file_tree__"] = "\n".join(file_paths[:500])
    return contents


async def collect_git_activity_summary(access_token: str | None, full_name: str) -> str:
    """Resume branches, PRs e últimos commits em texto — usado só pelo prompt
    da dimensão "git" (ver app/prompts/git_health.py)."""
    branches, pulls, commits = await asyncio.gather(
        list_branches(access_token, full_name, limit=30),
        list_pull_requests(access_token, full_name, limit=20),
        list_commits(access_token, full_name, limit=30),
    )

    merged_prs = sum(1 for p in pulls if p.get("merged_at"))
    lines = [
        "Branches: " + (", ".join(b["name"] for b in branches) or "(nenhuma encontrada)"),
        f"Pull requests recentes: {len(pulls)} (mergeados: {merged_prs})",
        "Últimos commits:",
    ]
    for commit in commits:
        message = commit["commit"]["message"].splitlines()[0]
        author = (commit.get("author") or {}).get("login") or commit["commit"]["author"]["name"]
        lines.append(f"- {message} (por {author})")

    return "\n".join(lines)
