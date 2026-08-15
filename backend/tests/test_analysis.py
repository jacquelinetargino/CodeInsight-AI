import uuid

import pytest
from fastapi import HTTPException

from app.ai.factory import get_ai_provider
from app.api.routes.analysis import require_ai_provider
from app.core.config import get_settings
from app.models.analysis import Analysis
from app.models.enums import AnalysisStatus

settings = get_settings()
PREFIX = settings.api_v1_prefix


async def _noop_run_repository_analysis(analysis_id) -> None:
    pass


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

    async def fake_run_repository_analysis(analysis_id):
        calls.append(str(analysis_id))

    monkeypatch.setattr(
        "app.api.routes.analysis.run_repository_analysis", fake_run_repository_analysis
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
        "app.api.routes.analysis.run_repository_analysis", _noop_run_repository_analysis
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
    client, test_user, authed_client_factory, monkeypatch, override_ai_provider
):
    # Com provedor disponível, para o 400 vir da regra de negócio (análise não
    # concluída) e não do 503 de recurso de IA indisponível.
    override_ai_provider(json_responses=[{}])
    monkeypatch.setattr(
        "app.api.routes.analysis.run_repository_analysis", _noop_run_repository_analysis
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
        "app.api.routes.analysis.run_repository_analysis", _noop_run_repository_analysis
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


async def test_legacy_ai_endpoints_return_503_without_provider(
    client, db_session, test_user, authed_client_factory, monkeypatch
):
    """Sem provedor configurado os recursos LEGACY ficam indisponíveis — 503,
    não 500: a instalação está saudável, o recurso é que é opcional."""
    monkeypatch.delenv("AI_API_KEY", raising=False)
    get_settings.cache_clear()
    get_ai_provider.cache_clear()

    monkeypatch.setattr(
        "app.api.routes.analysis.run_repository_analysis", _noop_run_repository_analysis
    )
    headers = authed_client_factory(test_user.id)
    repo_id = await _add_repo(client, headers, monkeypatch)
    create = await client.post(
        f"{PREFIX}/analysis", json={"repository_id": repo_id}, headers=headers
    )
    analysis_id = create.json()["id"]
    await _mark_analysis_done(db_session, analysis_id)

    readme = await client.post(f"{PREFIX}/analysis/{analysis_id}/readme", headers=headers)
    assert readme.status_code == 503
    assert "opcional" in readme.json()["detail"].lower()

    fix = await client.post(
        f"{PREFIX}/analysis/{analysis_id}/fix",
        json={"title": "t", "description": "d"},
        headers=headers,
    )
    assert fix.status_code == 503


def test_require_ai_provider_maps_missing_config_to_503(monkeypatch):
    """Unitário da dependência, sem banco: garante a tradução do erro tipado
    em 503 mesmo quando a suíte roda sem Postgres."""
    monkeypatch.delenv("AI_API_KEY", raising=False)
    get_settings.cache_clear()
    get_ai_provider.cache_clear()

    with pytest.raises(HTTPException) as exc:
        require_ai_provider()
    assert exc.value.status_code == 503
    assert "opcional" in exc.value.detail.lower()


def test_require_ai_provider_returns_provider_when_configured(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "claude")
    monkeypatch.setenv("AI_API_KEY", "chave-de-teste")
    get_settings.cache_clear()
    get_ai_provider.cache_clear()

    assert require_ai_provider() is not None
