"""Envio de e-mail transacional (hoje, só o link de redefinição de senha).

Por API HTTP e não por SMTP: o plano gratuito do Render bloqueia as portas
25/465/587, então um cliente SMTP simplesmente não conecta lá. Sem provedor
configurado (`settings.email_configured`), quem chama decide o que fazer — a
rota de "esqueci a senha" responde 503.
"""

import html
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"
TIMEOUT_SECONDS = 15.0


class EmailDeliveryError(Exception):
    """O provedor recusou ou não respondeu. A mensagem nunca inclui a chave."""


async def send_email(*, to: str, subject: str, html_body: str, text_body: str) -> None:
    settings = get_settings()
    if not settings.email_configured:
        raise EmailDeliveryError("Nenhum provedor de e-mail configurado.")

    payload = {
        "sender": {"email": settings.email_from, "name": settings.email_from_name},
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": text_body,
    }
    headers = {"api-key": settings.brevo_api_key or "", "accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(BREVO_SEND_URL, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise EmailDeliveryError("Não foi possível conectar ao provedor de e-mail.") from exc

    if response.status_code >= 400:
        # Só o status: o corpo de erro do provedor não é repassado nem logado.
        raise EmailDeliveryError(f"O provedor de e-mail respondeu com erro {response.status_code}.")


def build_password_reset_email(
    username: str, reset_url: str, expire_minutes: int
) -> tuple[str, str, str]:
    """`(assunto, html, texto)` do e-mail de redefinição."""
    subject = "Redefinição de senha — CodeInsight AI"
    nome = html.escape(username)
    url = html.escape(reset_url, quote=True)
    html_body = f"""<p>Olá, {nome}.</p>
<p>Recebemos um pedido para redefinir a senha da sua conta no CodeInsight AI.</p>
<p><a href="{url}">Clique aqui para escolher uma nova senha</a>.</p>
<p>O link vale por {expire_minutes} minutos e só pode ser usado uma vez.</p>
<p>Se não foi você, ignore este e-mail — sua senha continua a mesma.</p>"""
    text_body = (
        f"Olá, {username}.\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta no CodeInsight AI.\n\n"
        f"Abra este link para escolher uma nova senha:\n{reset_url}\n\n"
        f"O link vale por {expire_minutes} minutos e só pode ser usado uma vez.\n\n"
        "Se não foi você, ignore este e-mail — sua senha continua a mesma.\n"
    )
    return subject, html_body, text_body


async def send_password_reset_email(*, to: str, username: str, reset_url: str) -> None:
    """Roda em BackgroundTask: falha é registrada, nunca propagada. Quem pediu
    já recebeu a resposta genérica — e ela não pode depender de o e-mail sair,
    senão volta a revelar quem tem conta."""
    settings = get_settings()
    subject, html_body, text_body = build_password_reset_email(
        username, reset_url, settings.password_reset_expire_minutes
    )
    try:
        await send_email(to=to, subject=subject, html_body=html_body, text_body=text_body)
    except EmailDeliveryError as exc:
        # Sem o endereço no log: é dado pessoal, e o erro não depende dele.
        logger.warning("Falha ao enviar e-mail de redefinição de senha: %s", exc)
