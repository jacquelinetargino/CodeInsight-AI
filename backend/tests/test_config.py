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
    settings = _settings(frontend_url=frontend_url, PUBLIC_FRONTEND_URL=None)
    assert settings.cors_origins == expected


def test_cors_ignora_barra_final() -> None:
    """O navegador manda `Origin: https://site.com`, sem barra. Com a barra na
    variável, o CORS recusaria tudo vindo desse site."""
    settings = _settings(frontend_url="https://site.com/,https://b.com", PUBLIC_FRONTEND_URL=None)
    assert settings.cors_origins == ["https://site.com", "https://b.com"]


def test_cors_libera_o_dominio_publico_mesmo_fora_de_frontend_url() -> None:
    """Regressão: com o domínio próprio em PUBLIC_FRONTEND_URL e FRONTEND_URL
    ainda só com o domínio antigo, o site novo não conseguia chamar a API e o
    "esqueci a senha" falhava com "Tente novamente"."""
    settings = _settings(
        frontend_url="https://antigo.vercel.app",
        PUBLIC_FRONTEND_URL="https://www.codeinsight.app.br/",
    )
    assert settings.cors_origins == ["https://antigo.vercel.app", "https://www.codeinsight.app.br"]
    # O link do e-mail continua indo para o domínio público.
    assert settings.public_frontend_url == "https://www.codeinsight.app.br"


def test_dominio_publico_ja_listado_nao_duplica() -> None:
    settings = _settings(
        frontend_url="https://www.codeinsight.app.br,https://antigo.vercel.app",
        PUBLIC_FRONTEND_URL="https://www.codeinsight.app.br",
    )
    assert settings.cors_origins == ["https://www.codeinsight.app.br", "https://antigo.vercel.app"]


def test_cors_usa_so_a_origem_do_dominio_publico() -> None:
    settings = _settings(
        frontend_url="http://localhost:5173", PUBLIC_FRONTEND_URL="https://app.com/x/"
    )
    assert settings.cors_origins == ["http://localhost:5173", "https://app.com"]


def test_sem_dominio_publico_o_link_usa_a_primeira_origem() -> None:
    settings = _settings(frontend_url="https://a.com/,https://b.com", PUBLIC_FRONTEND_URL=None)
    assert settings.public_frontend_url == "https://a.com"


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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Connection string do Neon: o asyncpg não aceita sslmode nem channel_binding.
        (
            "postgresql://u:p@h/db?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://u:p@h/db?ssl=require",
        ),
        ("postgresql://u:p@h/db?sslmode=require", "postgresql+asyncpg://u:p@h/db?ssl=require"),
        ("postgresql+asyncpg://u:p@h/db?ssl=require", "postgresql+asyncpg://u:p@h/db?ssl=require"),
    ],
)
def test_database_url_translates_libpq_params(raw: str, expected: str) -> None:
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
