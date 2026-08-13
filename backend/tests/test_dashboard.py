import uuid

from app.core.config import get_settings
from app.models.analysis import Analysis
from app.models.enums import AnalysisStatus

settings = get_settings()
PREFIX = settings.api_v1_prefix


async def _noop_run_repository_analysis(analysis_id) -> None:
    pass


async def test_dashboard_requires_auth(client):
    response = await client.get(f"{PREFIX}/dashboard/summary")
    assert response.status_code == 401


async def test_dashboard_summary_empty_for_new_user(client, test_user, authed_client_factory):
    headers = authed_client_factory(test_user.id)
    response = await client.get(f"{PREFIX}/dashboard/summary", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "repositories_analyzed": 0,
        "total_analyses": 0,
        "average_score": None,
        "total_findings": 0,
        "total_suggestions": 0,
        "recent_history": [],
    }


async def test_dashboard_summary_reflects_completed_analyses(
    client, db_session, test_user, authed_client_factory, monkeypatch
):
    async def fake_get_repository(access_token, resolved_full_name):
        return {
            "id": 42,
            "full_name": resolved_full_name,
            "description": None,
            "default_branch": "main",
            "private": False,
        }

    monkeypatch.setattr("app.api.routes.repos.github_service.get_repository", fake_get_repository)
    monkeypatch.setattr(
        "app.api.routes.analysis.run_repository_analysis", _noop_run_repository_analysis
    )

    headers = authed_client_factory(test_user.id)
    repo_response = await client.post(
        f"{PREFIX}/repos", json={"repo": "octocat/dashboard-demo"}, headers=headers
    )
    repo_id = repo_response.json()["id"]

    analysis_response = await client.post(
        f"{PREFIX}/analysis", json={"repository_id": repo_id}, headers=headers
    )
    analysis_id = analysis_response.json()["id"]

    analysis = await db_session.get(Analysis, uuid.UUID(analysis_id))
    analysis.status = AnalysisStatus.DONE
    analysis.overall_score = 88.0
    await db_session.commit()

    response = await client.get(f"{PREFIX}/dashboard/summary", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["repositories_analyzed"] == 1
    assert body["total_analyses"] == 1
    assert body["average_score"] == 88.0
    assert len(body["recent_history"]) == 1
    assert body["recent_history"][0]["repository_full_name"] == "octocat/dashboard-demo"
