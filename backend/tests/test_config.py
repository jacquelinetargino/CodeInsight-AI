import pytest

from app.core.config import Settings

_REQUIRED = {
    "database_url": "postgresql+asyncpg://u:p@localhost:5432/db",
    "jwt_secret": "s",
    "encryption_key": "k",
    "ai_api_key": "a",
}


def _settings(**overrides) -> Settings:
    return Settings(**{**_REQUIRED, **overrides})


@pytest.mark.parametrize(
    ("frontend_url", "expected"),
    [
        ("http://localhost:5173", ["http://localhost:5173"]),
        (
            "https://app.exemplo.com,http://localhost:5173",
            ["https://app.exemplo.com", "http://localhost:5173"],
        ),
        # Espaços em volta das vírgulas são comuns quando a variável é editada
        # à mão num dashboard — não podem virar origem inválida.
        (" https://a.com , https://b.com ", ["https://a.com", "https://b.com"]),
        ("https://a.com,,https://b.com", ["https://a.com", "https://b.com"]),
    ],
)
def test_cors_origins_parsing(frontend_url: str, expected: list[str]) -> None:
    assert _settings(frontend_url=frontend_url).cors_origins == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        ("postgresql://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        # Já explícito: não pode ganhar um segundo "+asyncpg".
        ("postgresql+asyncpg://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
    ],
)
def test_database_url_gets_asyncpg_driver(raw: str, expected: str) -> None:
    assert _settings(database_url=raw).database_url == expected


def test_settings_loads_without_ai_api_key(monkeypatch):
    """MIG-004: a aplicação precisa subir sem nenhuma credencial de IA."""
    monkeypatch.delenv("AI_API_KEY", raising=False)
    settings = Settings(**{k: v for k, v in _REQUIRED.items() if k != "ai_api_key"})
    assert settings.ai_api_key is None
    assert settings.ai_configured is False


@pytest.mark.parametrize(
    ("provider", "api_key", "base_url", "esperado"),
    [
        ("claude", "sk-abc", None, True),
        ("claude", None, None, False),
        # Para `local` o que habilita é o endpoint, não a chave.
        ("local", None, "http://localhost:11434/v1", True),
        ("local", "irrelevante", None, False),
    ],
)
def test_ai_configured(provider, api_key, base_url, esperado):
    settings = _settings(ai_provider=provider, ai_api_key=api_key, ai_base_url=base_url)
    assert settings.ai_configured is esperado
