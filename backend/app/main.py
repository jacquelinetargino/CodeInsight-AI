import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app import __version__
from app.api.routes import analysis, auth, dashboard, diagnostics, oauth, reports, repos
from app.api.routes import settings as settings_routes
from app.core.config import get_settings
from app.core.limiter import limiter

settings = get_settings()

# Configuração que falta não pode ficar silenciosa: foi exatamente assim que o
# "esqueci a senha" passou a responder 503 em produção sem nenhum aviso nos logs.
_logger = logging.getLogger("app.startup")
if not settings.email_configured:
    _logger.warning(
        "E-mail não configurado (EMAIL_PROVIDER/BREVO_API_KEY/EMAIL_FROM): "
        "'esqueci a senha' vai responder 503."
    )
for _nome, _ok, _id_preenchido, _id_valido, _dica in (
    (
        "Google",
        settings.google_oauth_configured,
        bool(settings.google_client_id),
        settings.google_client_id_valid,
        "deve terminar em .apps.googleusercontent.com",
    ),
    (
        "GitHub",
        settings.github_oauth_configured,
        bool(settings.github_oauth_client_id),
        settings.github_client_id_valid,
        "não pode ser URL nem ter espaços",
    ),
):
    if _id_preenchido and not _id_valido:
        # WARNING e não INFO: é configuração errada, não ausente. O valor nunca
        # vai para o log — só o que está errado nele.
        _logger.warning(
            "Login com %s DESABILITADO: o client ID configurado não é válido (%s).",
            _nome,
            _dica,
        )
    elif not _ok:
        _logger.info("Login com %s desabilitado (credenciais OAuth ausentes).", _nome)

app = FastAPI(title=settings.app_name, version=__version__)
app.state.limiter = limiter
# O handler do slowapi recebe `RateLimitExceeded`; o Starlette tipa o parâmetro
# como `Exception`. É incompatibilidade entre as duas bibliotecas, não erro
# nosso: o Starlette só chama este handler para a exceção registrada ao lado.
# O ignore é pontual de propósito — desligar `arg-type` no arquivo esconderia
# erro de verdade.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Auth é via header "Authorization: Bearer" (não cookie), então não
    # precisamos de allow_credentials para o fluxo de login funcionar.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(oauth.router, prefix=settings.api_v1_prefix)
app.include_router(repos.router, prefix=settings.api_v1_prefix)
app.include_router(analysis.router, prefix=settings.api_v1_prefix)
app.include_router(reports.router, prefix=settings.api_v1_prefix)
app.include_router(settings_routes.router, prefix=settings.api_v1_prefix)
app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
# Fora do prefixo da API, junto de /health: é operação, não produto.
app.include_router(diagnostics.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
