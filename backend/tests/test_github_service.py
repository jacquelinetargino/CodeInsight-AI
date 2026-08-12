import pytest

from app.services.github_service import (
    InvalidRepositoryReferenceError,
    resolve_access_token,
    resolve_repo_full_name,
)


@pytest.mark.parametrize(
    "raw_input",
    [
        "octocat/hello-world",
        "https://github.com/octocat/hello-world",
        "http://github.com/octocat/hello-world",
        "https://www.github.com/octocat/hello-world",
        "github.com/octocat/hello-world",
        "https://github.com/octocat/hello-world.git",
        "https://github.com/octocat/hello-world/",
    ],
)
def test_resolve_repo_full_name_accepts_valid_references(raw_input):
    assert resolve_repo_full_name(raw_input) == "octocat/hello-world"


@pytest.mark.parametrize("raw_input", ["not a repo", "just-one-segment", "", "   ", "https://gitlab.com/a/b"])
def test_resolve_repo_full_name_rejects_invalid_references(raw_input):
    with pytest.raises(InvalidRepositoryReferenceError):
        resolve_repo_full_name(raw_input)


def test_resolve_access_token_prefers_user_token():
    assert resolve_access_token("user-pat-123") == "user-pat-123"


def test_resolve_access_token_falls_back_to_server_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "server-token-456")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        assert resolve_access_token(None) == "server-token-456"
    finally:
        get_settings.cache_clear()


def test_resolve_access_token_returns_none_when_fully_unauthenticated(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        assert resolve_access_token(None) is None
    finally:
        get_settings.cache_clear()
