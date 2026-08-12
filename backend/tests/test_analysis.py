import uuid

from app.core.config import get_settings
from app.models.analysis import Analysis
from app.models.enums import AnalysisStatus

settings = get_settings()
PREFIX = settings.api_v1_prefix


async def _add_repo(client, headers, monkeypatch, full_name: str = "octocat/analyzable") -> str:
    async def fake_get_repository(access_token, resolved_full_name):
        return {
            "id": 111222,
            "full_name": resolved_full_name,
            "description": None,
            "default_branch": "main",
            "private": False,
        }

    monkeypatch.setattr("app.api.routes.repos.github_service.get_repository", fake_get_repository)
    response = await client.post(f"{PREFIX}/repos", json={"repo": full_name}, headers=headers)
    return response.json()["id"]


async def _mark_analysis_done(db_session, analysis_id: str, overall_score: float = 82.0) -> None:
    analysis = await db_session.get(Analysis, uuid.UUID(analysis_id))
    analysis.status = AnalysisStatus.DONE
    analysis.overall_score = overall_score
    await db_session.commit()


async def test_create_analysis_requires_owned_repository(client, test_user, authed_client_factory):
    headers = authed_client_factory(test_user.id)
    response = await client.post(
        f"{PREFIX}/analysis", json={"repository_id": str(uuid.uuid4())}, headers=headers
    )
    assert response.status_code == 404


async def test_create_analysis_enqueues_task(client, test_user, authed_client_factory, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.api.routes.analysis.run_repository_analysis.delay",
        lambda analysis_id: calls.append(analysis_id),
    )

    headers = authed_client_factory(test_user.id)
    repo_id = await _add_repo(client, headers, monkeypatch)

    response = await client.post(
        f"{PREFIX}/analysis", json={"repository_id": repo_id}, headers=headers
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["repository_id"] == repo_id
    assert calls == [body["id"]]


async def test_get_analysis_not_found(client, test_user, authed_client_factory):
    headers = authed_client_factory(test_user.id)
    response = await client.get(f"{PREFIX}/analysis/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404


async def test_list_analysis_history(client, test_user, authed_client_factory, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.analysis.run_repository_analysis.delay", lambda analysis_id: None
    )

    headers = authed_client_factory(test_user.id)
    repo_id = await _add_repo(client, headers, monkeypatch)
    await client.post(f"{PREFIX}/analysis", json={"repository_id": repo_id}, headers=headers)

    response = await client.get(
        f"{PREFIX}/analysis", params={"repository_id": repo_id}, headers=headers
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_request_fix_requires_completed_analysis(
    client, test_user, authed_client_factory, monkeypatch
):
    monkeypatch.setattr(
        "app.api.routes.analysis.run_repository_analysis.delay", lambda analysis_id: None
    )

    headers = authed_client_factory(test_user.id)
    repo_id = await _add_repo(client, headers, monkeypatch)
    create_response = await client.post(
        f"{PREFIX}/analysis", json={"repository_id": repo_id}, headers=headers
    )
    analysis_id = create_response.json()["id"]

    response = await client.post(
        f"{PREFIX}/analysis/{analysis_id}/fix",
        json={"title": "Senha em texto plano", "description": "..."},
        headers=headers,
    )
    assert response.status_code == 400


async def test_request_fix_for_finding_persists_result(
    client, db_session, test_user, authed_client_factory, monkeypatch, override_ai_provider
):
    async def fake_get_file_content(access_token, full_name, path):
        return "PASSWORD = '123456'"

    monkeypatch.setattr(
        "app.api.routes.analysis.run_repository_analysis.delay", lambda analysis_id: None
    )
    monkeypatch.setattr(
        "app.api.routes.analysis.github_service.get_file_content", fake_get_file_content
    )

    headers = authed_client_factory(test_user.id)
    repo_id = await _add_repo(client, headers, monkeypatch)
    create_response = await client.post(
        f"{PREFIX}/analysis", json={"repository_id": repo_id}, headers=headers
    )
    analysis_id = create_response.json()["id"]
    await _mark_analysis_done(db_session, analysis_id)

    override_ai_provider(
        json_responses=[
            {
                "current_code": "PASSWORD = '123456'",
                "suggested_code": "PASSWORD = os.environ['PASSWORD']",
                "explanation": "Evita expor credenciais no código-fonte.",
            }
        ]
    )

    response = await client.post(
        f"{PREFIX}/analysis/{analysis_id}/fix",
        json={
            "title": "Senha em texto plano",
            "description": "Credencial hardcoded",
            "file_path": "config.py",
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["suggested_code"] == "PASSWORD = os.environ['PASSWORD']"
    assert body["file_path"] == "config.py"
