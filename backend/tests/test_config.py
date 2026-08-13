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
