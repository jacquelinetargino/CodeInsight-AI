import httpx

from app.core.config import get_settings

settings = get_settings()
PREFIX = settings.api_v1_prefix


def _fake_get_repository(github_repo_id: int, full_name: str):
    async def _inner(access_token, resolved_full_name):
        return {
            "id": github_repo_id,
            "full_name": resolved_full_name,
            "description": "Repositório de exemplo",
            "default_branch": "main",
            "private": False,
        }

    return _inner


async def test_list_repos_requires_auth(client):
    response = await client.get(f"{PREFIX}/repos")
    assert response.status_code == 401


async def test_list_repos_empty_for_new_user(client, test_user, authed_client_factory):
    headers = authed_client_factory(test_user.id)
    response = await client.get(f"{PREFIX}/repos", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


async def test_add_repository_by_owner_repo(client, test_user, authed_client_factory, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.repos.github_service.get_repository",
        _fake_get_repository(987654, "octocat/hello-world"),
    )

    headers = authed_client_factory(test_user.id)
    response = await client.post(
        f"{PREFIX}/repos", json={"repo": "octocat/hello-world"}, headers=headers
    )

    assert response.status_code == 201
    created = response.json()
    assert created["full_name"] == "octocat/hello-world"

    list_response = await client.get(f"{PREFIX}/repos", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = await client.get(f"{PREFIX}/repos/{created['id']}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]


async def test_add_repository_accepts_github_url(
    client, test_user, authed_client_factory, monkeypatch
):
    async def fake_get_repository(access_token, resolved_full_name):
        assert resolved_full_name == "octocat/hello-world"
        return {
            "id": 1,
            "full_name": resolved_full_name,
            "description": None,
            "default_branch": "main",
            "private": False,
        }

    monkeypatch.setattr("app.api.routes.repos.github_service.get_repository", fake_get_repository)

    headers = authed_client_factory(test_user.id)
    response = await client.post(
        f"{PREFIX}/repos", json={"repo": "https://github.com/octocat/hello-world"}, headers=headers
    )
    assert response.status_code == 201


async def test_add_repository_rejects_invalid_reference(client, test_user, authed_client_factory):
    headers = authed_client_factory(test_user.id)
    response = await client.post(f"{PREFIX}/repos", json={"repo": "not a repo!!"}, headers=headers)
    assert response.status_code == 400


async def test_add_repository_is_idempotent(client, test_user, authed_client_factory, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.repos.github_service.get_repository",
        _fake_get_repository(555, "octocat/duplicate"),
    )

    headers = authed_client_factory(test_user.id)
    first = await client.post(
        f"{PREFIX}/repos", json={"repo": "octocat/duplicate"}, headers=headers
    )
    second = await client.post(
        f"{PREFIX}/repos", json={"repo": "octocat/duplicate"}, headers=headers
    )

    assert first.json()["id"] == second.json()["id"]


async def test_add_repository_not_found_returns_404(
    client, test_user, authed_client_factory, monkeypatch
):
    async def fake_get_repository(access_token, resolved_full_name):
        request = httpx.Request("GET", "https://api.github.com/repos/octocat/missing")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr("app.api.routes.repos.github_service.get_repository", fake_get_repository)

    headers = authed_client_factory(test_user.id)
    response = await client.post(
        f"{PREFIX}/repos", json={"repo": "octocat/missing"}, headers=headers
    )
    assert response.status_code == 404


async def test_list_my_github_repos_requires_pat(client, test_user, authed_client_factory):
    headers = authed_client_factory(test_user.id)
    response = await client.get(f"{PREFIX}/repos/github/mine", headers=headers)
    assert response.status_code == 400
