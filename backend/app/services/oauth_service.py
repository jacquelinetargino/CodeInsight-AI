"""Login social com Google (OpenID Connect) e GitHub (OAuth 2.0).

Fluxo, nos dois provedores — Authorization Code com PKCE, tudo no backend:

1. `GET /auth/oauth/{p}/start` sorteia `state`, `code_verifier` (PKCE) e, no
   Google, `nonce`. Os três vão num cookie assinado, HttpOnly, SameSite=Lax,
   restrito ao caminho do OAuth; o navegador segue para o provedor.
2. O provedor devolve o navegador para `/auth/oauth/{p}/callback?code&state`.
   O `state` precisa bater com o do cookie (CSRF de login); o `code` é trocado
   por token com o client secret E o verifier; no Google, o `id_token` é
   validado (assinatura pelo JWKS, `iss`, `aud`, `exp`, `nonce`).
3. Nada é decidido no callback. Ele só cifra "quem é a pessoa" num código de
   troca de vida curta e manda o navegador para `{front}/auth/callback#code=…`
   — no fragmento, que não vai para servidor nenhum nem para o Referer.
4. O frontend troca esse código em `POST /auth/oauth/exchange`. É ali que a
   conta é encontrada, criada ou vinculada, e o JWT de sempre é emitido. A
   sessão continua igual à do login por senha: Bearer no header.

Por que a decisão fica na troca (passo 4) e não no callback: vincular uma
identidade a uma conta exige provar que o navegador que voltou do provedor é
o da pessoa logada. Só a troca enxerga o Bearer do frontend; o callback é uma
navegação comum, sem ele. Ver `link_identity`.

Nenhum token do provedor é guardado. O do GitHub, em particular, não tem
relação com o PAT usado para analisar repositórios.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, URLSafeTimedSerializer
from jose import JWTError
from jose import jwt as jose_jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User
from app.repositories.oauth_identity_repository import OAuthIdentityRepository
from app.repositories.user_repository import UserRepository

Provider = Literal["google", "github"]
Intent = Literal["login", "link"]
PROVIDERS: tuple[Provider, ...] = ("google", "github")

TIMEOUT_SECONDS = 10.0
LINK_TICKET_MAX_AGE = 120
EXCHANGE_CODE_MAX_AGE = 120

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
# `openid email profile`: identidade, e-mail e nome. Nada de Drive, Gmail etc.
GOOGLE_SCOPES = "openid email profile"

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
# Só leitura do perfil e dos e-mails. Nenhum acesso a repositório: analisar
# repositórios privados continua sendo pelo PAT das configurações.
GITHUB_SCOPES = "read:user user:email"


class OAuthError(Exception):
    """Falha esperada do fluxo. `code` vai para a URL do frontend, que o traduz
    numa mensagem; nunca carrega detalhe do provedor nem segredo."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ProviderProfile:
    provider: str
    subject: str
    email: str | None
    email_verified: bool
    name: str | None


def is_configured(provider: str) -> bool:
    settings = get_settings()
    if provider == "google":
        return settings.google_oauth_configured
    if provider == "github":
        return settings.github_oauth_configured
    return False


# --- PKCE e assinaturas ----------------------------------------------------------


def new_pkce_pair() -> tuple[str, str]:
    """`(verifier, challenge)` com S256 (RFC 7636). 64 bytes de entropia viram
    86 caracteres, dentro do intervalo 43–128 exigido."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _serializer(salt: str) -> URLSafeTimedSerializer:
    # Um salt por finalidade: um valor assinado para ser cookie de state não
    # serve como ticket de vínculo, nem como token de redefinição de senha.
    return URLSafeTimedSerializer(get_settings().jwt_secret, salt=salt)


def dump_state(data: dict[str, Any]) -> str:
    return _serializer("oauth-state").dumps(data)


def load_state(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        data = _serializer("oauth-state").loads(
            raw, max_age=get_settings().oauth_state_max_age_seconds
        )
    except BadSignature:
        return None
    return data if isinstance(data, dict) else None


def create_link_ticket(user_id: uuid.UUID, provider: str) -> str:
    """Autoriza UM início de vínculo para este usuário e provedor, por dois
    minutos. Existe porque o `start` é uma navegação e não leva o Bearer."""
    return _serializer("oauth-link-ticket").dumps({"u": str(user_id), "p": provider})


def read_link_ticket(ticket: str, provider: str) -> str | None:
    try:
        data = _serializer("oauth-link-ticket").loads(ticket, max_age=LINK_TICKET_MAX_AGE)
    except BadSignature:
        return None
    if (
        not isinstance(data, dict)
        or data.get("p") != provider
        or not isinstance(data.get("u"), str)
    ):
        return None
    return data["u"]


def _exchange_fernet() -> Fernet:
    # Chave derivada do JWT_SECRET e separada da ENCRYPTION_KEY dos PATs: um
    # vazamento de um uso não abre o outro.
    raw = hashlib.sha256(b"codeinsight-oauth-exchange|" + get_settings().jwt_secret.encode())
    return Fernet(base64.urlsafe_b64encode(raw.digest()))


# Códigos de troca já usados (jti -> instante de expiração). Em memória, como o
# limitador: dentro de um processo, o mesmo código não serve duas vezes.
_codigos_usados: dict[str, float] = {}


def create_exchange_code(profile: ProviderProfile, intent: Intent, link_user_id: str | None) -> str:
    """Cifrado, não só assinado: leva e-mail e nome, e passa pela URL do
    navegador. Fernet autentica e carimba a hora — o prazo é checado na
    leitura."""
    payload = {"j": secrets.token_urlsafe(16), "i": intent, "u": link_user_id, **asdict(profile)}
    return _exchange_fernet().encrypt(json.dumps(payload).encode()).decode()


def consume_exchange_code(code: str) -> tuple[ProviderProfile, Intent, str | None] | None:
    try:
        raw = _exchange_fernet().decrypt(code.encode(), ttl=EXCHANGE_CODE_MAX_AGE)
        data = json.loads(raw)
    except (InvalidToken, ValueError):
        return None

    agora = time.time()
    for jti, expira in list(_codigos_usados.items()):
        if expira < agora:
            del _codigos_usados[jti]
    jti = data.get("j")
    if not isinstance(jti, str) or jti in _codigos_usados:
        return None
    _codigos_usados[jti] = agora + EXCHANGE_CODE_MAX_AGE

    profile = ProviderProfile(
        provider=data["provider"],
        subject=data["subject"],
        email=data.get("email"),
        email_verified=bool(data.get("email_verified")),
        name=data.get("name"),
    )
    return profile, data["i"], data.get("u")


# --- Ida ao provedor ---------------------------------------------------------------


def build_authorize_url(provider: str, *, state: str, code_challenge: str, nonce: str) -> str:
    settings = get_settings()
    redirect_uri = settings.oauth_callback_url(provider)
    if provider == "google":
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"
    params = {
        "client_id": settings.github_oauth_client_id,
        "redirect_uri": redirect_uri,
        "scope": GITHUB_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "allow_signup": "true",
    }
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


# --- Volta do provedor ---------------------------------------------------------------

_jwks_cache: tuple[float, dict[str, Any]] | None = None
JWKS_TTL_SECONDS = 3600


async def _google_jwks(client: httpx.AsyncClient, *, refresh: bool = False) -> dict[str, Any]:
    global _jwks_cache
    if (
        not refresh
        and _jwks_cache is not None
        and time.monotonic() - _jwks_cache[0] < JWKS_TTL_SECONDS
    ):
        return _jwks_cache[1]
    response = await client.get(GOOGLE_JWKS_URL)
    if response.status_code != 200:
        raise OAuthError("provider_error")
    jwks = response.json()
    _jwks_cache = (time.monotonic(), jwks)
    return jwks


def _decode_google_id_token(
    id_token: str, jwks: dict[str, Any], access_token: str | None
) -> dict[str, Any]:
    return jose_jwt.decode(
        id_token,
        jwks,
        algorithms=["RS256"],
        audience=get_settings().google_client_id,
        issuer=GOOGLE_ISSUERS,
        access_token=access_token,
    )


async def _google_profile(code: str, verifier: str, nonce: str) -> ProviderProfile:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        try:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.oauth_callback_url("google"),
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
            )
            if token_response.status_code != 200:
                raise OAuthError("provider_error")
            tokens = token_response.json()
            id_token = tokens.get("id_token")
            if not isinstance(id_token, str):
                raise OAuthError("provider_error")

            jwks = await _google_jwks(client)
            try:
                claims = _decode_google_id_token(id_token, jwks, tokens.get("access_token"))
            except JWTError:
                # O Google gira as chaves; uma `kid` nova pode ainda não estar
                # no cache. Uma única nova tentativa com o JWKS recarregado.
                jwks = await _google_jwks(client, refresh=True)
                try:
                    claims = _decode_google_id_token(id_token, jwks, tokens.get("access_token"))
                except JWTError as exc:
                    raise OAuthError("invalid_token") from exc
        except httpx.HTTPError as exc:
            raise OAuthError("provider_error") from exc

    # O nonce amarra o id_token a ESTE início de login: um id_token capturado
    # de outra sessão não passa.
    if not secrets.compare_digest(str(claims.get("nonce", "")).encode(), nonce.encode()):
        raise OAuthError("invalid_token")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise OAuthError("invalid_token")
    email_verified = claims.get("email_verified") in (True, "true")
    email = claims.get("email") if isinstance(claims.get("email"), str) else None
    return ProviderProfile(
        provider="google",
        subject=subject,
        email=email,
        email_verified=email_verified and email is not None,
        name=claims.get("name") if isinstance(claims.get("name"), str) else None,
    )


async def _github_profile(code: str, verifier: str) -> ProviderProfile:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        try:
            token_response = await client.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": settings.github_oauth_client_id,
                    "client_secret": settings.github_oauth_client_secret,
                    "code": code,
                    "redirect_uri": settings.oauth_callback_url("github"),
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
            )
            # O GitHub responde 200 mesmo para código inválido, com `error` no corpo.
            tokens = token_response.json() if token_response.status_code == 200 else {}
            access_token = tokens.get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise OAuthError("provider_error")

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            user_response = await client.get(GITHUB_USER_URL, headers=headers)
            if user_response.status_code != 200:
                raise OAuthError("provider_error")
            user = user_response.json()

            emails_response = await client.get(GITHUB_EMAILS_URL, headers=headers)
            emails = emails_response.json() if emails_response.status_code == 200 else []
        except (httpx.HTTPError, ValueError) as exc:
            raise OAuthError("provider_error") from exc

    github_id = user.get("id")
    if not isinstance(github_id, int):
        raise OAuthError("provider_error")

    # O e-mail público do perfil pode não ser verificado nem existir. Vale só o
    # que a lista de e-mails marca como verificado — o principal, de preferência.
    verificados = [
        e
        for e in emails
        if isinstance(e, dict) and e.get("verified") and isinstance(e.get("email"), str)
    ]
    principal = next((e for e in verificados if e.get("primary")), None)
    escolhido = principal or (verificados[0] if verificados else None)

    return ProviderProfile(
        provider="github",
        # O id numérico é estável; o `login` (nome de usuário) pode ser trocado.
        subject=str(github_id),
        email=escolhido["email"] if escolhido else None,
        email_verified=escolhido is not None,
        name=(user.get("name") or user.get("login")) if isinstance(user, dict) else None,
    )


async def fetch_profile(provider: str, *, code: str, verifier: str, nonce: str) -> ProviderProfile:
    if provider == "google":
        return await _google_profile(code, verifier, nonce)
    return await _github_profile(code, verifier)


# --- Conta no CodeInsight ----------------------------------------------------------------


class AccountResolutionError(Exception):
    """Recusa com mensagem para a pessoa. `status` é o HTTP da resposta."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


PROVIDER_LABEL = {"google": "Google", "github": "GitHub"}


def _username_for(profile: ProviderProfile) -> str:
    candidato = (profile.name or "").strip()
    if len(candidato) < 2 and profile.email:
        candidato = profile.email.split("@", 1)[0]
    if len(candidato) < 2:
        candidato = f"usuario-{PROVIDER_LABEL.get(profile.provider, 'oauth').lower()}"
    return candidato[:255]


async def login_with_profile(db: AsyncSession, profile: ProviderProfile) -> User:
    """Encontra pela identidade do provedor, ou cria conta nova.

    NUNCA vincula a uma conta existente só porque o e-mail é igual. O e-mail
    verificado pelo provedor prova que a pessoa controla a caixa HOJE, mas a
    conta local pode ter sido criada por outra pessoa com aquele endereço — ou
    o endereço pode ter sido reatribuído. Vincular é decisão de quem já está
    logado na conta (ver `link_identity`).
    """
    identities = OAuthIdentityRepository(db)
    users = UserRepository(db)
    label = PROVIDER_LABEL[profile.provider]

    identity = await identities.get_by_subject(profile.provider, profile.subject)
    if identity is not None:
        user = await users.get_by_id(identity.user_id)
        if user is None or not user.is_active:
            raise AccountResolutionError(403, "Usuário desativado.")
        identity.last_login_at = datetime.now(UTC)
        await db.commit()
        return user

    if not profile.email or not profile.email_verified:
        raise AccountResolutionError(
            400,
            f"Sua conta {label} não tem um e-mail verificado. Verifique um e-mail no {label} "
            "ou crie a conta com e-mail e senha.",
        )

    if await users.email_taken(profile.email):
        raise AccountResolutionError(
            409,
            f"Já existe uma conta com o e-mail da sua conta {label}. Entre com e-mail e senha e "
            f"conecte o {label} em Configurações — ou use “Esqueceu sua senha?”.",
        )

    try:
        user = await users.create(
            email=profile.email, hashed_password=None, username=_username_for(profile)
        )
        new_identity = await identities.create(
            user_id=user.id,
            provider=profile.provider,
            provider_user_id=profile.subject,
            email=profile.email,
            email_verified=True,
        )
        new_identity.last_login_at = datetime.now(UTC)
        await db.commit()
    except IntegrityError as exc:
        # Duas trocas simultâneas para a mesma pessoa: a segunda perde a corrida.
        await db.rollback()
        raise AccountResolutionError(
            409, "A conta acabou de ser criada. Tente entrar de novo."
        ) from exc
    await db.refresh(user)
    return user


async def link_identity(
    db: AsyncSession, profile: ProviderProfile, *, link_user_id: str, current_user: User | None
) -> None:
    """Vincula a identidade à conta que pediu o vínculo.

    Exige que o navegador que faz a troca esteja logado NA MESMA conta que
    iniciou o vínculo. Sem isso, um atacante iniciaria um vínculo na conta
    dele, mandaria o link do provedor para a vítima, e a conta Google da
    vítima ficaria ligada à conta do atacante — o próximo "Continuar com
    Google" da vítima cairia na conta dele.
    """
    label = PROVIDER_LABEL[profile.provider]
    if current_user is None or str(current_user.id) != link_user_id:
        raise AccountResolutionError(
            403, "Entre na sua conta neste navegador e tente conectar de novo."
        )

    identities = OAuthIdentityRepository(db)
    existente = await identities.get_by_subject(profile.provider, profile.subject)
    if existente is not None:
        if existente.user_id == current_user.id:
            return
        raise AccountResolutionError(
            409, f"Esta conta {label} já está conectada a outro usuário do CodeInsight AI."
        )
    if await identities.get_for_user(current_user.id, profile.provider) is not None:
        raise AccountResolutionError(
            409, f"Você já tem uma conta {label} conectada. Desconecte-a antes de trocar."
        )

    try:
        await identities.create(
            user_id=current_user.id,
            provider=profile.provider,
            provider_user_id=profile.subject,
            email=profile.email,
            email_verified=profile.email_verified,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AccountResolutionError(
            409, f"Esta conta {label} já está conectada a outro usuário do CodeInsight AI."
        ) from exc
