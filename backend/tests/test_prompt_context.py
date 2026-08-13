import pytest

from app.core.config import get_settings
from app.prompts.context import format_repo_context


@pytest.fixture
def context_limit(monkeypatch):
    """Ajusta AI_MAX_CONTEXT_CHARS limpando o cache do get_settings, que é
    lru_cached e devolveria o valor lido antes do monkeypatch."""

    def _set(chars: int) -> None:
        monkeypatch.setenv("AI_MAX_CONTEXT_CHARS", str(chars))
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


def _files() -> dict[str, str]:
    return {"__file_tree__": "grande.py", "grande.py": "x" * 5_000}


def test_context_is_truncated_at_configured_limit(context_limit):
    context_limit(500)
    context = format_repo_context("dono/repo", _files())

    assert "[...contexto truncado...]" in context
    # O texto do aviso é somado depois do corte, então o total passa um pouco.
    assert len(context) < 600


def test_context_is_not_truncated_when_it_fits(context_limit):
    context_limit(100_000)
    context = format_repo_context("dono/repo", _files())

    assert "[...contexto truncado...]" not in context
    assert "x" * 5_000 in context


def test_reserved_keys_are_not_rendered_as_files(context_limit):
    context_limit(100_000)
    files = {"__file_tree__": "a.py", "__git_activity__": "commits recentes", "a.py": "print(1)"}
    context = format_repo_context("dono/repo", files)

    assert "--- __file_tree__ ---" not in context
    assert "--- __git_activity__ ---" not in context
    assert "--- a.py ---" in context
