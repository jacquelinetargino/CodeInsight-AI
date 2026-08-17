"""O PAT do GitHub é criptografado em repouso e nunca volta pela API.

Três documentos prometem isso:

    README.md          "PATs do GitHub sempre criptografados em repouso (Fernet)"
    docs/security.md   "Descriptografado só em memória, no momento da chamada"
    SECURITY.md        "criptografados em repouso (Fernet), nunca logados"

**Nada verificava.** `test_security.py` cobre as primitivas `encrypt_secret` e
`decrypt_secret`, mas nenhum teste ligava a rota ao que fica gravado. Verificado
por mutação: trocando `encrypt_secret(payload.token)` por `payload.token` na
rota, os 723 testes continuavam passando e o PAT ia para o banco em texto puro.

Os tokens aqui são sintéticos e montados para parecer o formato real — nenhum
deles é credencial de lugar nenhum.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.models.github_credential import GithubCredential

settings = get_settings()
PREFIX = settings.api_v1_prefix

# Formato de PAT clássico do GitHub, com corpo inventado.
TOKEN_SINTETICO = "ghp_0123456789abcdefghijABCDEFGHIJ0123"


@pytest.fixture
def github_aceita_o_token(monkeypatch):
    """A rota valida o PAT contra a API do GitHub antes de gravar. Nenhum teste
    toca a rede: o que está sendo verificado é o armazenamento."""

    async def fake_get_authenticated_user(token: str):
        return {"login": "dono", "id": 1}

    monkeypatch.setattr(
        "app.api.routes.settings.github_service.get_authenticated_user",
        fake_get_authenticated_user,
    )


async def _guardar_token(client, headers, token=TOKEN_SINTETICO):
    return await client.put(
        f"{PREFIX}/settings/github-token", json={"token": token}, headers=headers
    )


async def _linha_gravada(db_session, user_id) -> GithubCredential:
    resultado = await db_session.execute(
        select(GithubCredential).where(GithubCredential.user_id == user_id)
    )
    return resultado.scalar_one()


# --- a garantia central ------------------------------------------------------


@pytest.mark.asyncio
async def test_o_token_nao_fica_em_texto_puro_no_banco(
    client: AsyncClient, test_user, authed_client_factory, db_session, github_aceita_o_token
):
    """A afirmação que os três documentos fazem, verificada na linha gravada."""
    headers = authed_client_factory(test_user.id)
    assert (await _guardar_token(client, headers)).status_code == 200

    credencial = await _linha_gravada(db_session, test_user.id)

    assert credencial.token_encrypted != TOKEN_SINTETICO
    # Nem como substring: um formato "prefixo + token" também vazaria.
    assert TOKEN_SINTETICO not in credencial.token_encrypted


@pytest.mark.asyncio
async def test_o_token_gravado_volta_intacto_ao_ser_descriptografado(
    client: AsyncClient, test_user, authed_client_factory, db_session, github_aceita_o_token
):
    """A trava do outro lado: gravar lixo também passaria no teste acima."""
    headers = authed_client_factory(test_user.id)
    await _guardar_token(client, headers)

    credencial = await _linha_gravada(db_session, test_user.id)
    assert decrypt_secret(credencial.token_encrypted) == TOKEN_SINTETICO


@pytest.mark.asyncio
async def test_duas_gravacoes_do_mesmo_token_produzem_cifras_diferentes(
    client: AsyncClient, test_user, authed_client_factory, db_session, github_aceita_o_token
):
    """Fernet inclui IV e timestamp, então a mesma entrada não produz a mesma
    saída. Cifra determinística permitiria comparar dois usuários e descobrir
    que usam o mesmo token."""
    headers = authed_client_factory(test_user.id)

    await _guardar_token(client, headers)
    primeira = (await _linha_gravada(db_session, test_user.id)).token_encrypted

    await _guardar_token(client, headers)
    await db_session.refresh(await _linha_gravada(db_session, test_user.id))
    segunda = (await _linha_gravada(db_session, test_user.id)).token_encrypted

    assert primeira != segunda
    assert decrypt_secret(primeira) == decrypt_secret(segunda) == TOKEN_SINTETICO


# --- o token nunca volta pela API --------------------------------------------


@pytest.mark.asyncio
async def test_nenhuma_rota_de_settings_devolve_o_token(
    client: AsyncClient, test_user, authed_client_factory, github_aceita_o_token
):
    """O status diz apenas se há conexão. Devolver o token — mesmo mascarado —
    daria a quem roubasse a sessão o que ele ainda não tem."""
    headers = authed_client_factory(test_user.id)

    respostas = [
        await _guardar_token(client, headers),
        await client.get(f"{PREFIX}/settings/github-token", headers=headers),
        await client.delete(f"{PREFIX}/settings/github-token", headers=headers),
    ]

    for resposta in respostas:
        assert TOKEN_SINTETICO not in resposta.text
        assert "token_encrypted" not in resposta.text


@pytest.mark.asyncio
async def test_o_status_reflete_a_conexao_sem_expor_nada(
    client: AsyncClient, test_user, authed_client_factory, github_aceita_o_token
):
    headers = authed_client_factory(test_user.id)

    assert (await client.get(f"{PREFIX}/settings/github-token", headers=headers)).json() == {
        "connected": False
    }

    await _guardar_token(client, headers)
    assert (await client.get(f"{PREFIX}/settings/github-token", headers=headers)).json() == {
        "connected": True
    }

    await client.delete(f"{PREFIX}/settings/github-token", headers=headers)
    assert (await client.get(f"{PREFIX}/settings/github-token", headers=headers)).json() == {
        "connected": False
    }


@pytest.mark.asyncio
async def test_apagar_remove_a_linha_e_nao_so_marca(
    client: AsyncClient, test_user, authed_client_factory, db_session, github_aceita_o_token
):
    """Marcar como desconectado deixaria a cifra no banco. Quem pede para
    desconectar quer o token fora de lá."""
    headers = authed_client_factory(test_user.id)
    await _guardar_token(client, headers)
    await client.delete(f"{PREFIX}/settings/github-token", headers=headers)

    resultado = await db_session.execute(
        select(GithubCredential).where(GithubCredential.user_id == test_user.id)
    )
    assert resultado.scalar_one_or_none() is None


# --- validação antes de gravar ------------------------------------------------


@pytest.mark.asyncio
async def test_token_recusado_pelo_github_nao_e_gravado(
    client: AsyncClient, test_user, authed_client_factory, db_session, monkeypatch
):
    """Gravar um token inválido criptografado seria guardar lixo cifrado."""
    import httpx

    async def recusa(token: str):
        raise httpx.HTTPStatusError(
            "401",
            request=httpx.Request("GET", "https://api.github.com/user"),
            response=httpx.Response(401),
        )

    monkeypatch.setattr("app.api.routes.settings.github_service.get_authenticated_user", recusa)
    headers = authed_client_factory(test_user.id)

    resposta = await _guardar_token(client, headers, token="ghp_invalido")
    assert resposta.status_code == 400

    resultado = await db_session.execute(
        select(GithubCredential).where(GithubCredential.user_id == test_user.id)
    )
    assert resultado.scalar_one_or_none() is None
