"""Rotas do login social e das contas vinculadas. A lógica está em
`app.services.oauth_service`; o docstring de lá descreve o fluxo inteiro."""

import logging
import secrets
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_optional_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import create_access_token
from app.models.user import User
from app.repositories.oauth_identity_repository import OAuthIdentityRepository
from app.schemas.user import (
    AuthProvidersRead,
    IdentitiesRead,
    OAuthExchangeRequest,
    OAuthExchangeResponse,
    OAuthIdentityRead,
    OAuthLinkStart,
    UserRead,
)
from app.services import oauth_service
from app.services.oauth_service import AccountResolutionError, Intent, OAuthError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

ProviderParam = Literal["google", "github"]
STATE_COOKIE = "ci_oauth_state"


def _cookie_path() -> str:
    # Restrito ao OAuth: o cookie não acompanha nenhuma outra requisição à API.
    return f"{get_settings().api_v1_prefix}/auth/oauth"


def _front_redirect(
    path: str, *, query: dict[str, str] | None = None, fragment: str = ""
) -> RedirectResponse:
    """Redireciona SEMPRE para o frontend configurado. Nenhum destino vem da
    requisição — não há parâmetro `redirect`/`next` para virar open redirect."""
    url = f"{get_settings().public_frontend_url}{path}"
    if query:
        url += f"?{urlencode(query)}"
    if fragment:
        url += f"#{fragment}"
    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _error_redirect(intent: str, code: str) -> RedirectResponse:
    # Erro de um vínculo volta para as configurações, onde ele foi pedido.
    path = "/settings" if intent == "link" else "/login"
    return _front_redirect(path, query={"oauth_error": code})


def _clear_state_cookie(response: RedirectResponse) -> None:
    settings = get_settings()
    response.delete_cookie(
        STATE_COOKIE,
        path=_cookie_path(),
        secure=settings.cookies_secure,
        httponly=True,
        samesite="lax",
    )


@router.get("/providers", response_model=AuthProvidersRead)
async def providers() -> AuthProvidersRead:
    settings = get_settings()
    return AuthProvidersRead(
        google=settings.google_oauth_configured,
        github=settings.github_oauth_configured,
        password_reset=settings.email_configured,
    )


@router.get("/oauth/{provider}/start", include_in_schema=True)
@limiter.limit("20/minute")
async def oauth_start(
    request: Request, provider: ProviderParam, link_ticket: str | None = None
) -> RedirectResponse:
    intent = "link" if link_ticket else "login"
    if not oauth_service.is_configured(provider):
        return _error_redirect(intent, "unavailable")

    link_user_id: str | None = None
    if link_ticket:
        link_user_id = oauth_service.read_link_ticket(link_ticket, provider)
        if link_user_id is None:
            return _error_redirect("link", "link_expired")

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier, challenge = oauth_service.new_pkce_pair()

    response = RedirectResponse(
        oauth_service.build_authorize_url(
            provider, state=state, code_challenge=challenge, nonce=nonce
        ),
        status_code=status.HTTP_302_FOUND,
    )
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    response.set_cookie(
        STATE_COOKIE,
        oauth_service.dump_state(
            {"p": provider, "s": state, "v": verifier, "n": nonce, "i": intent, "u": link_user_id}
        ),
        max_age=settings.oauth_state_max_age_seconds,
        path=_cookie_path(),
        secure=settings.cookies_secure,
        httponly=True,
        # Lax e não Strict: a volta do provedor é uma navegação de outro site, e
        # Strict faria o navegador não mandar o cookie justamente no callback.
        samesite="lax",
    )
    return response


@router.get("/oauth/{provider}/callback")
@limiter.limit("20/minute")
async def oauth_callback(
    request: Request,
    provider: ProviderParam,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    saved = oauth_service.load_state(request.cookies.get(STATE_COOKIE))
    intent: Intent = "link" if saved and saved.get("i") == "link" else "login"

    response: RedirectResponse
    if error:
        # `access_denied` é a pessoa clicando em "Cancelar" no provedor.
        response = _error_redirect(
            intent, "cancelled" if error == "access_denied" else "provider_error"
        )
    elif (
        saved is None
        or saved.get("p") != provider
        or not state
        or not secrets.compare_digest(str(saved.get("s", "")).encode(), state.encode())
    ):
        # Sem cookie, cookie de outro provedor, ou state diferente: ou a sessão
        # expirou, ou alguém tentou injetar um código de outra pessoa (CSRF).
        response = _error_redirect(intent, "state_mismatch")
    elif not code:
        response = _error_redirect(intent, "provider_error")
    else:
        try:
            profile = await oauth_service.fetch_profile(
                provider, code=code, verifier=saved["v"], nonce=saved["n"]
            )
        except OAuthError as exc:
            # Só o código e o provedor no log: nada de token, e-mail ou corpo.
            logger.warning("Login social falhou (%s): %s", provider, exc.code)
            response = _error_redirect(intent, exc.code)
        else:
            exchange_code = oauth_service.create_exchange_code(profile, intent, saved.get("u"))
            response = _front_redirect(
                "/auth/callback", fragment=urlencode({"code": exchange_code})
            )

    # O state é de uso único: some na volta, com sucesso ou não.
    _clear_state_cookie(response)
    return response


@router.post("/oauth/{provider}/link", response_model=OAuthLinkStart)
@limiter.limit("10/minute")
async def oauth_link(
    request: Request, provider: ProviderParam, current_user: User = Depends(get_current_user)
) -> OAuthLinkStart:
    if not oauth_service.is_configured(provider):
        label = oauth_service.PROVIDER_LABEL[provider]
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"O login com {label} não está configurado neste servidor.",
        )
    settings = get_settings()
    ticket = oauth_service.create_link_ticket(current_user.id, provider)
    base = f"{settings.backend_url.rstrip('/')}{settings.api_v1_prefix}"
    return OAuthLinkStart(
        url=f"{base}/auth/oauth/{provider}/start?{urlencode({'link_ticket': ticket})}"
    )


@router.post("/oauth/exchange", response_model=OAuthExchangeResponse)
@limiter.limit("10/minute")
async def oauth_exchange(
    request: Request,
    payload: OAuthExchangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> OAuthExchangeResponse:
    lido = oauth_service.consume_exchange_code(payload.code)
    if lido is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Este link de login expirou ou já foi usado. Tente de novo.",
        )
    profile, intent, link_user_id = lido

    try:
        if intent == "link":
            await oauth_service.link_identity(
                db, profile, link_user_id=link_user_id or "", current_user=current_user
            )
            return OAuthExchangeResponse(intent="link", provider=profile.provider)

        user = await oauth_service.login_with_profile(db, profile)
    except AccountResolutionError as exc:
        raise HTTPException(exc.status, exc.message) from exc

    return OAuthExchangeResponse(
        intent="login",
        provider=profile.provider,
        access_token=create_access_token(str(user.id)),
        user=UserRead.model_validate(user),
    )


async def _identities(db: AsyncSession, user: User) -> IdentitiesRead:
    items = await OAuthIdentityRepository(db).list_for_user(user.id)
    return IdentitiesRead(
        has_password=user.hashed_password is not None,
        identities=[OAuthIdentityRead.model_validate(i) for i in items],
    )


@router.get("/identities", response_model=IdentitiesRead)
async def list_identities(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> IdentitiesRead:
    return await _identities(db, current_user)


@router.delete("/identities/{provider}", response_model=IdentitiesRead)
async def unlink_identity(
    provider: ProviderParam,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IdentitiesRead:
    repo = OAuthIdentityRepository(db)
    identity = await repo.get_for_user(current_user.id, provider)
    if identity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esta conta não está conectada.")

    restantes = [i for i in await repo.list_for_user(current_user.id) if i.provider != provider]
    if current_user.hashed_password is None and not restantes:
        # Desvincular o único meio de entrar trancaria a pessoa fora da conta.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Esta é a única forma de entrar na sua conta. Defina uma senha antes "
            "(em “Esqueceu sua senha?” na tela de login) ou conecte outra conta.",
        )

    await repo.delete(identity)
    await db.commit()
    return await _identities(db, current_user)
