"""Login social (Google e GitHub), vínculo de contas e as interações com a senha.

Nenhum teste fala com o Google nem com o GitHub: o transporte HTTP do serviço é
trocado por um `MockTransport`. O `id_token` do Google é assinado de verdade,
com uma chave RSA gerada aqui, e o JWKS falso publica a parte pública — então
a validação de assinatura, `aud`, `iss`, `exp` e `nonce` roda inteira.
"""

import base64
import hashlib
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk
from jose import jwt as jose_jwt
from sqlalchemy import func, select

from app.api.routes import auth as auth_routes
from app.api.routes.oauth import STATE_COOKIE
from app.core.config import get_settings
from app.core.security import create_password_reset_token, hash_password
from app.models.oauth_identity import OAuthIdentity
from app.models.user import User
from app.services import oauth_service

PREFIX = get_settings().api_v1_prefix
GOOGLE_ID = "google-client-id-de-teste.apps.googleusercontent.com"
FRONT = "https://app.exemplo.com"

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_PEM = _PRIVATE_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
_PUBLIC_JWK = {
    **jwk.construct(
        _PRIVATE_KEY.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode(),
        "RS256",
    ).to_dict(),
    "kid": "chave-1",
    "use": "sig",
}


@pytest.fixture(autouse=True)
def estado_do_oauth_zerado():
    oauth_service._jwks_cache = None
    oauth_service._codigos_usados.clear()
    auth_routes._ultimo_envio_de_reset.clear()
    yield
    oauth_service._jwks_cache = None
    oauth_service._codigos_usados.clear()
    auth_routes._ultimo_envio_de_reset.clear()


@pytest.fixture
def oauth_configurado(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", GOOGLE_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "segredo-google-ficticio")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "github-client-id-ficticio")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "segredo-github-ficticio")
    monkeypatch.setenv("FRONTEND_URL", f"{FRONT},http://localhost:5173")
    monkeypatch.setenv("BACKEND_URL", "http://localhost:8000")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def oauth_desligado(monkeypatch):
    for nome in (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GITHUB_OAUTH_CLIENT_ID",
        "GITHUB_OAUTH_CLIENT_SECRET",
    ):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("FRONTEND_URL", FRONT)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- provedores falsos ------------------------------------------------------------------


class FakeProviders:
    """Responde como Google e GitHub. Cada atributo muda um comportamento."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.google_claims: dict = {}
        self.google_token_status = 200
        self.google_nonce_override: str | None = None
        self.github_token_body: dict = {"access_token": "gho_ficticio", "token_type": "bearer"}
        self.github_user: dict = {"id": 4242, "login": "octo-ana", "name": "Ana Octo"}
        self.github_emails: list = [
            {"email": "secundario@exemplo.com", "primary": False, "verified": True},
            {"email": "ana@exemplo.com", "primary": True, "verified": True},
        ]
        self.expected_nonce: str | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url == oauth_service.GOOGLE_TOKEN_URL:
            if self.google_token_status != 200:
                return httpx.Response(self.google_token_status, json={"error": "invalid_grant"})
            claims = {
                "iss": "https://accounts.google.com",
                "aud": GOOGLE_ID,
                "sub": "google-sub-123",
                "email": "ana@exemplo.com",
                "email_verified": True,
                "name": "Ana Google",
                "iat": int(time.time()),
                "exp": int(time.time()) + 300,
                "nonce": self.google_nonce_override or self.expected_nonce,
                **self.google_claims,
            }
            id_token = jose_jwt.encode(
                claims,
                _PRIVATE_PEM,
                algorithm="RS256",
                headers={"kid": "chave-1"},
                access_token="ya29.ficticio",
            )
            return httpx.Response(200, json={"access_token": "ya29.ficticio", "id_token": id_token})
        if url == oauth_service.GOOGLE_JWKS_URL:
            return httpx.Response(200, json={"keys": [_PUBLIC_JWK]})
        if url == oauth_service.GITHUB_TOKEN_URL:
            return httpx.Response(200, json=self.github_token_body)
        if url == oauth_service.GITHUB_USER_URL:
            return httpx.Response(200, json=self.github_user)
        if url == oauth_service.GITHUB_EMAILS_URL:
            return httpx.Response(200, json=self.github_emails)
        return httpx.Response(404)


@pytest.fixture
def provedores(monkeypatch) -> FakeProviders:
    fake = FakeProviders()
    original = httpx.AsyncClient

    def fake_client(**kwargs):
        return original(transport=httpx.MockTransport(fake.handler), **kwargs)

    monkeypatch.setattr(oauth_service.httpx, "AsyncClient", fake_client)
    return fake


# --- helpers do fluxo ------------------------------------------------------------------


async def _start(client, provider: str, **params):
    response = await client.get(f"{PREFIX}/auth/oauth/{provider}/start", params=params)
    assert response.status_code == 302
    return response


def _query(location: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}


async def _ida_e_volta(client, provedores: FakeProviders, provider: str, **start_params):
    """start -> provedor (simulado) -> callback. Devolve a resposta do callback."""
    start = await _start(client, provider, **start_params)
    params = _query(start.headers["location"])
    provedores.expected_nonce = params.get("nonce")
    return await client.get(
        f"{PREFIX}/auth/oauth/{provider}/callback",
        params={"code": "codigo-do-provedor", "state": params["state"]},
    )


def _exchange_code(callback) -> str:
    location = callback.headers["location"]
    assert location.startswith(f"{FRONT}/auth/callback#"), location
    return parse_qs(urlsplit(location).fragment)["code"][0]


async def _login_social(client, provedores, provider: str):
    callback = await _ida_e_volta(client, provedores, provider)
    return await client.post(
        f"{PREFIX}/auth/oauth/exchange", json={"code": _exchange_code(callback)}
    )


async def _contar(db_session, model) -> int:
    return (await db_session.execute(select(func.count()).select_from(model))).scalar_one()


# --- configuração --------------------------------------------------------------------------


async def test_providers_reflete_a_configuracao(client, oauth_configurado):
    response = await client.get(f"{PREFIX}/auth/providers")
    assert response.status_code == 200
    body = response.json()
    assert body["google"] is True and body["github"] is True
    assert "password_reset" in body


async def test_provedor_sem_credencial_volta_para_o_login_com_erro(client, oauth_desligado):
    response = await _start(client, "google")
    assert response.headers["location"] == f"{FRONT}/login?oauth_error=unavailable"


async def test_provedor_desconhecido_e_recusado(client, oauth_configurado):
    response = await client.get(f"{PREFIX}/auth/oauth/facebook/start")
    assert response.status_code == 422


def test_callback_url_e_a_registrada_nos_provedores(oauth_configurado):
    assert (
        get_settings().oauth_callback_url("google")
        == "http://localhost:8000/api/v1/auth/oauth/google/callback"
    )


# --- ida ao provedor ------------------------------------------------------------------------


async def test_start_google_usa_pkce_state_nonce_e_cookie_protegido(client, oauth_configurado):
    response = await _start(client, "google")
    location = response.headers["location"]
    assert location.startswith(oauth_service.GOOGLE_AUTHORIZE_URL)
    params = _query(location)
    assert params["client_id"] == GOOGLE_ID
    assert params["redirect_uri"] == get_settings().oauth_callback_url("google")
    assert params["response_type"] == "code"
    assert params["scope"] == "openid email profile"
    assert params["code_challenge_method"] == "S256"
    assert len(params["state"]) >= 32 and len(params["nonce"]) >= 32

    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{STATE_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert f"Path={PREFIX}/auth/oauth" in cookie
    # Nada do segredo nem do verifier na URL que vai para o provedor.
    assert "segredo-google" not in location
    assert "code_verifier" not in location


async def test_start_github_pede_so_escopos_de_identidade(client, oauth_configurado):
    params = _query((await _start(client, "github")).headers["location"])
    assert params["scope"] == "read:user user:email"
    assert "repo" not in params["scope"].split()
    assert params["code_challenge_method"] == "S256"


# --- volta do provedor ------------------------------------------------------------------------


async def test_cancelamento_no_provedor(client, oauth_configurado, provedores):
    await _start(client, "google")
    response = await client.get(
        f"{PREFIX}/auth/oauth/google/callback", params={"error": "access_denied", "state": "x"}
    )
    assert response.headers["location"] == f"{FRONT}/login?oauth_error=cancelled"
    assert provedores.requests == []


async def test_state_diferente_e_recusado_sem_chamar_o_provedor(
    client, oauth_configurado, provedores
):
    await _start(client, "google")
    response = await client.get(
        f"{PREFIX}/auth/oauth/google/callback", params={"code": "c", "state": "forjado"}
    )
    assert response.headers["location"] == f"{FRONT}/login?oauth_error=state_mismatch"
    assert provedores.requests == []


async def test_callback_sem_cookie_e_recusado(client, oauth_configurado, provedores):
    """O cenário de CSRF de login: um link de callback com o código do atacante
    aberto no navegador da vítima, que nunca iniciou o fluxo."""
    response = await client.get(
        f"{PREFIX}/auth/oauth/google/callback", params={"code": "c", "state": "s"}
    )
    assert response.headers["location"] == f"{FRONT}/login?oauth_error=state_mismatch"
    assert provedores.requests == []


async def test_state_de_um_provedor_nao_serve_para_outro(client, oauth_configurado, provedores):
    params = _query((await _start(client, "google")).headers["location"])
    response = await client.get(
        f"{PREFIX}/auth/oauth/github/callback", params={"code": "c", "state": params["state"]}
    )
    assert "oauth_error=state_mismatch" in response.headers["location"]


async def test_state_e_de_uso_unico(client, oauth_configurado, provedores):
    callback = await _ida_e_volta(client, provedores, "google")
    assert "max-age=0" in callback.headers["set-cookie"].lower()
    # O cookie foi apagado; repetir o callback não acha state nenhum.
    response = await client.get(
        f"{PREFIX}/auth/oauth/google/callback", params={"code": "c", "state": "qualquer"}
    )
    assert "oauth_error=state_mismatch" in response.headers["location"]


async def test_pkce_o_verifier_enviado_confere_com_o_challenge(
    client, oauth_configurado, provedores
):
    start = await _start(client, "google")
    params = _query(start.headers["location"])
    provedores.expected_nonce = params["nonce"]
    await client.get(
        f"{PREFIX}/auth/oauth/google/callback",
        params={"code": "codigo", "state": params["state"]},
    )

    token_request = next(
        r for r in provedores.requests if str(r.url) == oauth_service.GOOGLE_TOKEN_URL
    )
    form = {k: v[0] for k, v in parse_qs(token_request.read().decode()).items()}
    digest = hashlib.sha256(form["code_verifier"].encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == params["code_challenge"]
    assert form["client_secret"] == "segredo-google-ficticio"
    assert form["redirect_uri"] == params["redirect_uri"]


# --- Google ----------------------------------------------------------------------------------


async def test_login_google_cria_conta_sem_senha(client, db_session, oauth_configurado, provedores):
    response = await _login_social(client, provedores, "google")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "login" and body["provider"] == "google"
    assert body["user"]["email"] == "ana@exemplo.com"
    assert body["user"]["username"] == "Ana Google"

    me = await client.get(
        f"{PREFIX}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200

    user = (await db_session.execute(select(User))).scalar_one()
    assert user.hashed_password is None
    identity = (await db_session.execute(select(OAuthIdentity))).scalar_one()
    assert (identity.provider, identity.provider_user_id) == ("google", "google-sub-123")
    assert identity.user_id == user.id


async def test_segundo_login_google_nao_duplica(client, db_session, oauth_configurado, provedores):
    primeiro = await _login_social(client, provedores, "google")
    segundo = await _login_social(client, provedores, "google")

    assert segundo.status_code == 200
    assert segundo.json()["user"]["id"] == primeiro.json()["user"]["id"]
    assert await _contar(db_session, User) == 1
    assert await _contar(db_session, OAuthIdentity) == 1


async def test_identidade_e_pelo_sub_nao_pelo_email(
    client, db_session, oauth_configurado, provedores
):
    """O e-mail da conta Google mudou: continua sendo a mesma pessoa."""
    primeiro = await _login_social(client, provedores, "google")
    provedores.google_claims = {"email": "novo-endereco@exemplo.com"}
    segundo = await _login_social(client, provedores, "google")

    assert segundo.json()["user"]["id"] == primeiro.json()["user"]["id"]


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "outro-client-id"},
        {"iss": "https://accounts.google.com.atacante.com"},
        {"exp": int(time.time()) - 60},
    ],
    ids=["aud-errado", "iss-errado", "expirado"],
)
async def test_id_token_invalido_e_recusado(client, oauth_configurado, provedores, claims):
    provedores.google_claims = claims
    callback = await _ida_e_volta(client, provedores, "google")
    assert callback.headers["location"] == f"{FRONT}/login?oauth_error=invalid_token"


async def test_id_token_de_outra_sessao_nonce_errado(client, oauth_configurado, provedores):
    provedores.google_nonce_override = "nonce-de-outra-sessao"
    callback = await _ida_e_volta(client, provedores, "google")
    assert callback.headers["location"] == f"{FRONT}/login?oauth_error=invalid_token"


async def test_erro_na_troca_do_codigo_google(client, oauth_configurado, provedores):
    provedores.google_token_status = 400
    callback = await _ida_e_volta(client, provedores, "google")
    assert callback.headers["location"] == f"{FRONT}/login?oauth_error=provider_error"


async def test_google_sem_email_verificado_nao_cria_conta(
    client, db_session, oauth_configurado, provedores
):
    provedores.google_claims = {"email_verified": False}
    response = await _login_social(client, provedores, "google")

    assert response.status_code == 400
    assert "verificado" in response.json()["detail"]
    assert await _contar(db_session, User) == 0


async def test_email_igual_a_conta_existente_nao_vincula_sozinho(
    client, db_session, oauth_configurado, provedores
):
    """Regra central: e-mail igual NÃO basta para entrar numa conta existente."""
    db_session.add(
        User(email="Ana@Exemplo.com", hashed_password=hash_password("senha-dela-123"), username="a")
    )
    await db_session.commit()

    response = await _login_social(client, provedores, "google")

    assert response.status_code == 409
    assert "Configurações" in response.json()["detail"]
    assert "access_token" not in response.json()
    assert await _contar(db_session, User) == 1
    assert await _contar(db_session, OAuthIdentity) == 0


async def test_codigo_de_troca_e_de_uso_unico(client, oauth_configurado, provedores):
    callback = await _ida_e_volta(client, provedores, "google")
    code = _exchange_code(callback)

    primeira = await client.post(f"{PREFIX}/auth/oauth/exchange", json={"code": code})
    segunda = await client.post(f"{PREFIX}/auth/oauth/exchange", json={"code": code})

    assert primeira.status_code == 200
    assert segunda.status_code == 400


async def test_codigo_de_troca_vencido(client, oauth_configurado, provedores, monkeypatch):
    callback = await _ida_e_volta(client, provedores, "google")
    monkeypatch.setattr(oauth_service, "EXCHANGE_CODE_MAX_AGE", -1)
    response = await client.post(
        f"{PREFIX}/auth/oauth/exchange", json={"code": _exchange_code(callback)}
    )
    assert response.status_code == 400


async def test_codigo_de_troca_adulterado(client, oauth_configurado):
    response = await client.post(f"{PREFIX}/auth/oauth/exchange", json={"code": "gAAAAAlixo"})
    assert response.status_code == 400


async def test_codigo_de_troca_nao_expoe_o_email_na_url(client, oauth_configurado, provedores):
    callback = await _ida_e_volta(client, provedores, "google")
    location = callback.headers["location"]
    assert "ana@exemplo.com" not in location
    assert "ana%40exemplo.com" not in location
    assert "ya29" not in location


# --- GitHub ----------------------------------------------------------------------------------


async def test_login_github_usa_id_numerico_e_email_principal_verificado(
    client, db_session, oauth_configurado, provedores
):
    response = await _login_social(client, provedores, "github")

    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == "ana@exemplo.com"
    assert response.json()["user"]["username"] == "Ana Octo"
    identity = (await db_session.execute(select(OAuthIdentity))).scalar_one()
    assert (identity.provider, identity.provider_user_id) == ("github", "4242")


async def test_login_github_nao_guarda_o_token_do_github(
    client, db_session, oauth_configurado, provedores
):
    """O token do login não pode virar o PAT de análise de repositórios."""
    from app.models.github_credential import GithubCredential

    await _login_social(client, provedores, "github")
    assert await _contar(db_session, GithubCredential) == 0


async def test_github_sem_email_verificado(client, db_session, oauth_configurado, provedores):
    provedores.github_emails = [{"email": "x@exemplo.com", "primary": True, "verified": False}]
    response = await _login_social(client, provedores, "github")
    assert response.status_code == 400
    assert await _contar(db_session, User) == 0


async def test_github_codigo_invalido(client, oauth_configurado, provedores):
    provedores.github_token_body = {"error": "bad_verification_code"}
    callback = await _ida_e_volta(client, provedores, "github")
    assert callback.headers["location"] == f"{FRONT}/login?oauth_error=provider_error"


# --- vínculo ------------------------------------------------------------------------------------


async def _iniciar_vinculo(client, headers, provider="google") -> dict[str, str]:
    response = await client.post(f"{PREFIX}/auth/oauth/{provider}/link", headers=headers)
    assert response.status_code == 200, response.text
    return _query(response.json()["url"])


async def test_vincular_google_a_conta_logada(
    client, db_session, test_user, authed_client_factory, oauth_configurado, provedores
):
    headers = authed_client_factory(test_user.id)
    ticket = (await _iniciar_vinculo(client, headers))["link_ticket"]

    callback = await _ida_e_volta(client, provedores, "google", link_ticket=ticket)
    response = await client.post(
        f"{PREFIX}/auth/oauth/exchange", json={"code": _exchange_code(callback)}, headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "intent": "link",
        "provider": "google",
        "access_token": None,
        "token_type": "bearer",
        "user": None,
    }
    identidades = await client.get(f"{PREFIX}/auth/identities", headers=headers)
    assert [i["provider"] for i in identidades.json()["identities"]] == ["google"]
    assert identidades.json()["has_password"] is True

    # E agora "Continuar com Google" entra NESTA conta.
    login = await _login_social(client, provedores, "google")
    assert login.json()["user"]["id"] == str(test_user.id)


async def test_vinculo_terminado_em_outro_navegador_e_recusado(
    client, db_session, test_user, authed_client_factory, oauth_configurado, provedores
):
    """O ataque: o atacante inicia o vínculo na conta DELE e faz a vítima
    concluir a ida ao Google. A troca chega sem a sessão do atacante."""
    headers = authed_client_factory(test_user.id)
    ticket = (await _iniciar_vinculo(client, headers))["link_ticket"]
    callback = await _ida_e_volta(client, provedores, "google", link_ticket=ticket)

    sem_sessao = await client.post(
        f"{PREFIX}/auth/oauth/exchange", json={"code": _exchange_code(callback)}
    )

    assert sem_sessao.status_code == 403
    assert await _contar(db_session, OAuthIdentity) == 0


async def test_vinculo_com_sessao_de_outra_conta_e_recusado(
    client, db_session, test_user, authed_client_factory, oauth_configurado, provedores
):
    outro = User(email="outro@exemplo.com", hashed_password=hash_password("x" * 10), username="ou")
    db_session.add(outro)
    await db_session.commit()

    ticket = (await _iniciar_vinculo(client, authed_client_factory(test_user.id)))["link_ticket"]
    callback = await _ida_e_volta(client, provedores, "google", link_ticket=ticket)
    response = await client.post(
        f"{PREFIX}/auth/oauth/exchange",
        json={"code": _exchange_code(callback)},
        headers=authed_client_factory(outro.id),
    )

    assert response.status_code == 403
    assert await _contar(db_session, OAuthIdentity) == 0


async def test_conta_google_ja_usada_por_outro_usuario(
    client, db_session, test_user, authed_client_factory, oauth_configurado, provedores
):
    provedores.google_claims = {"email": "dona-do-google@exemplo.com"}
    await _login_social(client, provedores, "google")  # cria a conta da dona

    headers = authed_client_factory(test_user.id)
    ticket = (await _iniciar_vinculo(client, headers))["link_ticket"]
    callback = await _ida_e_volta(client, provedores, "google", link_ticket=ticket)
    response = await client.post(
        f"{PREFIX}/auth/oauth/exchange", json={"code": _exchange_code(callback)}, headers=headers
    )

    assert response.status_code == 409
    assert await _contar(db_session, OAuthIdentity) == 1


async def test_ticket_de_vinculo_nao_serve_para_outro_provedor(
    client, test_user, authed_client_factory, oauth_configurado
):
    ticket = (await _iniciar_vinculo(client, authed_client_factory(test_user.id)))["link_ticket"]
    response = await _start(client, "github", link_ticket=ticket)
    assert response.headers["location"] == f"{FRONT}/settings?oauth_error=link_expired"


async def test_iniciar_vinculo_exige_login(client, oauth_configurado):
    response = await client.post(f"{PREFIX}/auth/oauth/google/link")
    assert response.status_code == 401


async def test_cancelar_vinculo_volta_para_configuracoes(
    client, test_user, authed_client_factory, oauth_configurado, provedores
):
    ticket = (await _iniciar_vinculo(client, authed_client_factory(test_user.id)))["link_ticket"]
    await _start(client, "google", link_ticket=ticket)
    response = await client.get(
        f"{PREFIX}/auth/oauth/google/callback", params={"error": "access_denied"}
    )
    assert response.headers["location"] == f"{FRONT}/settings?oauth_error=cancelled"


# --- desvincular e senha ------------------------------------------------------------------------


async def test_nao_desvincula_o_unico_meio_de_entrar(client, oauth_configurado, provedores):
    login = (await _login_social(client, provedores, "google")).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    response = await client.delete(f"{PREFIX}/auth/identities/google", headers=headers)

    assert response.status_code == 409
    identidades = await client.get(f"{PREFIX}/auth/identities", headers=headers)
    assert identidades.json()["has_password"] is False
    assert len(identidades.json()["identities"]) == 1


async def test_desvincula_quando_ha_senha(
    client, test_user, authed_client_factory, oauth_configurado, provedores
):
    headers = authed_client_factory(test_user.id)
    ticket = (await _iniciar_vinculo(client, headers))["link_ticket"]
    callback = await _ida_e_volta(client, provedores, "google", link_ticket=ticket)
    await client.post(
        f"{PREFIX}/auth/oauth/exchange", json={"code": _exchange_code(callback)}, headers=headers
    )

    response = await client.delete(f"{PREFIX}/auth/identities/google", headers=headers)

    assert response.status_code == 200
    assert response.json()["identities"] == []


async def test_conta_sem_senha_nao_entra_por_senha(client, oauth_configurado, provedores):
    await _login_social(client, provedores, "google")
    response = await client.post(
        f"{PREFIX}/auth/login", json={"email": "ana@exemplo.com", "password": "qualquer-coisa"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "E-mail ou senha inválidos"


async def test_conta_sem_senha_define_senha_pelo_esqueci_a_senha(
    client, db_session, oauth_configurado, provedores
):
    await _login_social(client, provedores, "google")
    user = (await db_session.execute(select(User))).scalar_one()

    token = create_password_reset_token(str(user.id), user.hashed_password)
    reset = await client.post(
        f"{PREFIX}/auth/reset-password", json={"token": token, "new_password": "senha-nova-456"}
    )
    assert reset.status_code == 200

    login = await client.post(
        f"{PREFIX}/auth/login", json={"email": "ana@exemplo.com", "password": "senha-nova-456"}
    )
    assert login.status_code == 200
    # E o link já não serve de novo.
    reuso = await client.post(
        f"{PREFIX}/auth/reset-password", json={"token": token, "new_password": "outra-senha-789"}
    )
    assert reuso.status_code == 400


async def test_cadastro_recusa_email_com_outra_caixa(client, test_user):
    response = await client.post(
        f"{PREFIX}/auth/register",
        json={"email": test_user.email.upper(), "password": "senha-valida-1", "username": "dup"},
    )
    assert response.status_code == 409
