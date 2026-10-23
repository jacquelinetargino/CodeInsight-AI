"""Recuperação de senha: token assinado de uso único + envio pela API do Brevo.

Nenhum teste fala com o Brevo de verdade — o transporte HTTP é simulado.
"""

import httpx
import pytest

from app.api.routes import auth as auth_routes
from app.core import security
from app.core.config import get_settings
from app.core.security import (
    create_password_reset_token,
    hash_password,
    password_fingerprint_matches,
    read_password_reset_token,
)
from app.services import email_service

PREFIX = get_settings().api_v1_prefix


@pytest.fixture
def email_configurado(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "brevo")
    monkeypatch.setenv("BREVO_API_KEY", "chave-ficticia-de-teste")
    monkeypatch.setenv("EMAIL_FROM", "nao-responda@exemplo.com")
    monkeypatch.setenv("FRONTEND_URL", "https://app.exemplo.com,http://localhost:5173")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def email_desligado(monkeypatch):
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- token ---------------------------------------------------------------------


def test_token_ida_e_volta():
    h = hash_password("senha-original-123")
    token = create_password_reset_token("id-do-usuario", h)

    lido = read_password_reset_token(token)

    assert lido is not None
    user_id, fingerprint = lido
    assert user_id == "id-do-usuario"
    assert password_fingerprint_matches(fingerprint, h)


def test_token_adulterado_e_recusado():
    token = create_password_reset_token("id", hash_password("x" * 10))
    assert read_password_reset_token(token[:-2] + "xx") is None
    assert read_password_reset_token("lixo") is None


def test_token_vencido_e_recusado(monkeypatch):
    token = create_password_reset_token("id", hash_password("x" * 10))
    monkeypatch.setattr(security.settings, "password_reset_expire_minutes", -1)
    assert read_password_reset_token(token) is None


def test_token_deixa_de_valer_quando_a_senha_muda():
    """É o que faz o link ser de uso único sem tabela no banco."""
    antigo = hash_password("senha-antiga-123")
    _, fingerprint = read_password_reset_token(create_password_reset_token("id", antigo))
    assert not password_fingerprint_matches(fingerprint, hash_password("senha-nova-456"))


# --- configuração ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "key", "sender", "esperado"),
    [
        ("brevo", "k", "a@b.com", True),
        ("BREVO", "k", "a@b.com", True),
        ("brevo", None, "a@b.com", False),
        ("brevo", "k", None, False),
        (None, "k", "a@b.com", False),
        ("smtp", "k", "a@b.com", False),
    ],
)
def test_email_configured(provider, key, sender, esperado):
    settings = get_settings().model_copy(
        update={"email_provider": provider, "brevo_api_key": key, "email_from": sender}
    )
    assert settings.email_configured is esperado


def test_link_usa_a_primeira_origem_de_frontend_url(email_configurado):
    assert get_settings().public_frontend_url == "https://app.exemplo.com"


# --- e-mail ------------------------------------------------------------------------


def test_corpo_do_email_escapa_o_nome_e_inclui_o_link():
    _, html_body, text_body = email_service.build_password_reset_email(
        "<script>x</script>", "https://app/reset-password?token=abc", 30
    )
    assert "<script>" not in html_body
    assert "&lt;script&gt;" in html_body
    assert "https://app/reset-password?token=abc" in text_body
    assert "30 minutos" in text_body


def _transporte(monkeypatch, handler):
    original = httpx.AsyncClient

    def fake_client(**kwargs):
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(email_service.httpx, "AsyncClient", fake_client)


async def test_send_email_chama_a_api_do_brevo(monkeypatch, email_configurado):
    pedidos = []

    def handler(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        return httpx.Response(201, json={"messageId": "x"})

    _transporte(monkeypatch, handler)
    await email_service.send_email(
        to="pessoa@exemplo.com", subject="Assunto", html_body="<p>oi</p>", text_body="oi"
    )

    (pedido,) = pedidos
    assert str(pedido.url) == email_service.BREVO_SEND_URL
    assert pedido.headers["api-key"] == "chave-ficticia-de-teste"
    corpo = pedido.read().decode()
    assert "pessoa@exemplo.com" in corpo
    assert "nao-responda@exemplo.com" in corpo


async def test_erro_do_brevo_nao_ecoa_a_chave(monkeypatch, email_configurado):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Key not found: chave-ficticia-de-teste"})

    _transporte(monkeypatch, handler)
    with pytest.raises(email_service.EmailDeliveryError) as exc:
        await email_service.send_email(to="a@b.com", subject="s", html_body="h", text_body="t")
    assert "401" in str(exc.value)
    assert "chave-ficticia" not in str(exc.value)


async def test_falha_no_envio_em_segundo_plano_nao_propaga(monkeypatch, email_configurado):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem rede", request=request)

    _transporte(monkeypatch, handler)
    # Não levanta: a resposta ao usuário já saiu e não pode depender do envio.
    await email_service.send_password_reset_email(
        to="a@b.com", username="a", reset_url="https://app/reset-password?token=t"
    )


# --- rotas ---------------------------------------------------------------------------


async def test_esqueci_a_senha_sem_provedor_responde_503(client, email_desligado):
    response = await client.post(
        f"{PREFIX}/auth/forgot-password", json={"email": "alguem@exemplo.com"}
    )
    assert response.status_code == 503


async def test_esqueci_a_senha_envia_link_para_conta_existente(
    client, test_user, monkeypatch, email_configurado
):
    enviados = []

    async def captura(**kwargs):
        enviados.append(kwargs)

    monkeypatch.setattr(auth_routes, "send_password_reset_email", captura)

    response = await client.post(f"{PREFIX}/auth/forgot-password", json={"email": test_user.email})

    assert response.status_code == 202
    assert response.json() == {"message": auth_routes.FORGOT_PASSWORD_MESSAGE}
    (envio,) = enviados
    assert envio["to"] == test_user.email
    assert envio["reset_url"].startswith("https://app.exemplo.com/reset-password?token=")


async def test_esqueci_a_senha_responde_igual_para_email_desconhecido(
    client, monkeypatch, email_configurado
):
    """Sem diferença na resposta: a rota não pode revelar quem tem conta."""
    enviados = []

    async def captura(**kwargs):
        enviados.append(kwargs)

    monkeypatch.setattr(auth_routes, "send_password_reset_email", captura)

    response = await client.post(
        f"{PREFIX}/auth/forgot-password", json={"email": "ninguem@exemplo.com"}
    )

    assert response.status_code == 202
    assert response.json() == {"message": auth_routes.FORGOT_PASSWORD_MESSAGE}
    assert enviados == []


async def test_redefinir_troca_a_senha_e_o_link_vale_uma_vez(client, test_user):
    token = create_password_reset_token(str(test_user.id), test_user.hashed_password)

    response = await client.post(
        f"{PREFIX}/auth/reset-password", json={"token": token, "new_password": "senha-nova-456"}
    )
    assert response.status_code == 200

    nova = await client.post(
        f"{PREFIX}/auth/login", json={"email": test_user.email, "password": "senha-nova-456"}
    )
    assert nova.status_code == 200
    antiga = await client.post(
        f"{PREFIX}/auth/login",
        json={"email": test_user.email, "password": "correct-horse-battery-staple"},
    )
    assert antiga.status_code == 401

    # O mesmo link de novo: a senha mudou, então a impressão no token não confere.
    reuso = await client.post(
        f"{PREFIX}/auth/reset-password", json={"token": token, "new_password": "outra-senha-789"}
    )
    assert reuso.status_code == 400


async def test_redefinir_com_token_invalido_responde_400(client):
    response = await client.post(
        f"{PREFIX}/auth/reset-password", json={"token": "lixo", "new_password": "senha-nova-456"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == auth_routes.INVALID_RESET_LINK_MESSAGE


async def test_redefinir_aplica_as_regras_de_senha_do_cadastro(client, test_user):
    token = create_password_reset_token(str(test_user.id), test_user.hashed_password)
    curta = await client.post(
        f"{PREFIX}/auth/reset-password", json={"token": token, "new_password": "1234567"}
    )
    assert curta.status_code == 422
    longa = await client.post(
        f"{PREFIX}/auth/reset-password", json={"token": token, "new_password": "é" * 40}
    )
    assert longa.status_code == 422
