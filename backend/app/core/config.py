from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "CodeInsight AI"
    api_v1_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    database_url: str
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Criptografa PATs do GitHub em repouso (Fernet).
    encryption_key: str

    # Token opcional do servidor, usado como fallback para repositórios públicos
    # quando o usuário não conectou seu próprio PAT (evita o rate limit de 60/h
    # de requisições não autenticadas na GitHub API).
    github_token: str | None = None

    # --- Provedor de IA (abstrato) ---
    ai_provider: str = "claude"  # claude | openai | gemini | local
    ai_api_key: str
    ai_model: str = "claude-sonnet-5"
    # Necessário para "local" (ex.: http://localhost:11434/v1 no Ollama) e
    # opcional para apontar OpenAI/Gemini para um endpoint compatível custom.
    ai_base_url: str | None = None

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
