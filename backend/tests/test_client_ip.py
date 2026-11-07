"""IP do cliente para o rate limit, atrás de proxies confiáveis.

A cadeia simulada aqui é a descrita para o Render (cliente → Cloudflare →
proxy do Render → app): o `X-Forwarded-For` chega como
`<o que o cliente forjou>, <IP real do cliente>, <IP do edge da Cloudflare>` e a
conexão vem de um IP privado do proxy. Os endereços são de faixas de
documentação (RFC 5737 / RFC 3849) ou privados.
"""

import ipaddress
import logging

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from starlette.requests import Request

from app.core import client_ip
from app.core.client_ip import (
    UNKNOWN_CLIENT,
    forwarded_chain,
    parse_ip,
    rate_limit_key,
    resolve_client_ip,
)
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.main import app

PREFIX = get_settings().api_v1_prefix

PROXY_RENDER = "10.21.157.68"  # a conexão que a app enxerga no Render
EDGE_CLOUDFLARE = "104.16.0.1"
CLIENTE_A = "198.51.100.7"
CLIENTE_B = "203.0.113.9"


def _request(peer: str | None = PROXY_RENDER, xff: list[str] | None = None) -> Request:
    headers = [(b"x-forwarded-for", linha.encode()) for linha in (xff or [])]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": headers,
        "client": (peer, 4321) if peer is not None else None,
    }
    return Request(scope)


@pytest.fixture
def hops(monkeypatch):
    """`hops(2)` configura TRUSTED_PROXY_HOPS=2 para o teste."""

    def _set(valor: int) -> None:
        monkeypatch.setenv("TRUSTED_PROXY_HOPS", str(valor))
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


# --- unidade: qual IP é escolhido ----------------------------------------------


def test_padrao_e_zero_e_ignora_o_cabecalho(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().trusted_proxy_hops == 0
        req = _request(xff=[f"{CLIENTE_A}, {EDGE_CLOUDFLARE}"])
        # Sem configuração, o comportamento é o de antes: IP da conexão.
        assert rate_limit_key(req) == PROXY_RENDER
    finally:
        get_settings.cache_clear()


def test_atras_de_dois_proxies_usa_o_ip_real():
    req = _request(xff=[f"{CLIENTE_A}, {EDGE_CLOUDFLARE}"])
    cliente = resolve_client_ip(req, trusted_hops=2)
    assert str(cliente.ip) == CLIENTE_A
    assert cliente.source == "forwarded"


@pytest.mark.parametrize(
    "forjado",
    [
        "1.1.1.1",
        "1.1.1.1, 2.2.2.2, 3.3.3.3",
        "127.0.0.1",
        "unknown",
        "lixo, , ,",
        "::1",
        ", ".join(f"10.0.0.{i}" for i in range(200)),
    ],
    ids=["um", "varios", "loopback", "texto", "vazios", "ipv6", "duzentos"],
)
def test_entradas_forjadas_pelo_cliente_sao_ignoradas(forjado):
    """O cliente só consegue escrever à ESQUERDA do que os proxies acrescentam."""
    req = _request(xff=[f"{forjado}, {CLIENTE_A}, {EDGE_CLOUDFLARE}"])
    assert str(resolve_client_ip(req, trusted_hops=2).ip) == CLIENTE_A


def test_forjado_em_linha_separada_do_cabecalho_tambem_e_ignorado():
    """Duas linhas de X-Forwarded-For valem como uma lista só, na ordem."""
    req = _request(xff=["6.6.6.6", f"{CLIENTE_A}, {EDGE_CLOUDFLARE}"])
    assert forwarded_chain(req) == ["6.6.6.6", CLIENTE_A, EDGE_CLOUDFLARE]
    assert str(resolve_client_ip(req, trusted_hops=2).ip) == CLIENTE_A


@pytest.mark.parametrize(
    "xff",
    [[], [EDGE_CLOUDFLARE], [""]],
    ids=["sem-cabecalho", "uma-entrada", "vazio"],
)
def test_menos_entradas_que_proxies_volta_para_a_conexao(xff):
    """Não passou pela cadeia esperada: nada no cabeçalho é confiável."""
    cliente = resolve_client_ip(_request(xff=xff), trusted_hops=2)
    assert cliente.source == "peer"
    assert str(cliente.ip) == PROXY_RENDER


@pytest.mark.parametrize("candidato", ["unknown", "999.1.1.1", "1.2.3.4.5", "abc::xyz", "_"])
def test_candidato_invalido_volta_para_a_conexao(candidato):
    cliente = resolve_client_ip(_request(xff=[f"{candidato}, {EDGE_CLOUDFLARE}"]), trusted_hops=2)
    assert cliente.source == "peer"


def test_hops_maior_que_a_cadeia_real_e_o_risco_documentado():
    """Por que o valor precisa ser validado antes de ativar: com N maior que o
    número real de proxies, a posição lida é a que o cliente escreve. Este teste
    fixa o comportamento para ninguém achar que "um a mais" é inofensivo."""
    req = _request(xff=[f"6.6.6.6, {CLIENTE_A}, {EDGE_CLOUDFLARE}"])
    assert str(resolve_client_ip(req, trusted_hops=3).ip) == "6.6.6.6"


def test_hops_menor_que_a_cadeia_real_falha_de_forma_segura():
    """Com N menor, a chave vira o IP do proxy: compartilhado, mas não burlável."""
    req = _request(xff=[f"6.6.6.6, {CLIENTE_A}, {EDGE_CLOUDFLARE}"])
    assert str(resolve_client_ip(req, trusted_hops=1).ip) == EDGE_CLOUDFLARE


# --- unidade: formatos de IP --------------------------------------------------------


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("198.51.100.7", "198.51.100.7"),
        (" 198.51.100.7 ", "198.51.100.7"),
        ("198.51.100.7:5678", "198.51.100.7"),
        ('"198.51.100.7"', "198.51.100.7"),
        ("2001:db8::1", "2001:db8::1"),
        ("[2001:db8::1]", "2001:db8::1"),
        ("[2001:db8::1]:443", "2001:db8::1"),
        ("::ffff:198.51.100.7", "198.51.100.7"),
    ],
)
def test_formatos_aceitos(bruto, esperado):
    assert str(parse_ip(bruto)) == esperado


@pytest.mark.parametrize("bruto", [None, "", "unknown", "[2001:db8::1", "1.2.3", "testclient"])
def test_formatos_recusados(bruto):
    assert parse_ip(bruto) is None


def test_ipv4_mapeado_em_ipv6_cai_no_mesmo_balde_do_ipv4(hops):
    hops(2)
    mapeado = _request(xff=[f"::ffff:{CLIENTE_A}, {EDGE_CLOUDFLARE}"])
    puro = _request(xff=[f"{CLIENTE_A}, {EDGE_CLOUDFLARE}"])
    assert rate_limit_key(mapeado) == rate_limit_key(puro) == CLIENTE_A


def test_ipv6_e_agrupado_pelo_slash_64(hops):
    """Um cliente controla o /64 inteiro; trocar de endereço não abre balde novo."""
    hops(2)
    a = rate_limit_key(_request(xff=[f"2001:db8:1:2::1, {EDGE_CLOUDFLARE}"]))
    b = rate_limit_key(_request(xff=[f"2001:db8:1:2:ffff:ffff:ffff:ffff, {EDGE_CLOUDFLARE}"]))
    outro = rate_limit_key(_request(xff=[f"2001:db8:1:3::1, {EDGE_CLOUDFLARE}"]))
    assert a == b == "2001:db8:1:2::/64"
    assert outro != a


def test_ipv4_nao_e_agrupado(hops):
    """NAT de operadora já junta muita gente num IPv4; agrupar pioraria."""
    hops(2)
    a = rate_limit_key(_request(xff=[f"198.51.100.7, {EDGE_CLOUDFLARE}"]))
    b = rate_limit_key(_request(xff=[f"198.51.100.8, {EDGE_CLOUDFLARE}"]))
    assert a != b


def test_conexao_sem_ip_valido_mantem_a_chave_crua():
    assert rate_limit_key(_request(peer="testclient")) == "testclient"
    assert rate_limit_key(_request(peer=None)) == UNKNOWN_CLIENT


# --- configuração ------------------------------------------------------------------


@pytest.mark.parametrize("valor", ["-1", "6", "dois"])
def test_hops_fora_do_intervalo_e_recusado(monkeypatch, valor):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", valor)
    with pytest.raises(ValidationError):
        Settings()


def test_diagnostico_vem_desligado(monkeypatch):
    monkeypatch.delenv("PROXY_DIAGNOSTICS_ENABLED", raising=False)
    assert Settings().proxy_diagnostics_enabled is False


# --- integração: o limite de verdade, numa rota real ---------------------------------


@pytest.fixture
def email_desligado(monkeypatch):
    """`forgot-password` sem provedor responde 503 sem tocar no banco — rota
    barata e limitada (5/min) para medir o balde."""
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def via_proxy(db_session):
    """Cliente HTTP cuja conexão vem do proxy do Render, como em produção."""

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    limiter.reset()
    transport = ASGITransport(app=app, client=(PROXY_RENDER, 4321))
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    limiter.reset()


async def _esqueci(cliente: AsyncClient, xff: str | None) -> int:
    headers = {"X-Forwarded-For": xff} if xff is not None else {}
    resposta = await cliente.post(
        f"{PREFIX}/auth/forgot-password", json={"email": "alguem@example.com"}, headers=headers
    )
    return resposta.status_code


async def test_sem_configurar_todos_dividem_o_balde_do_proxy(via_proxy, email_desligado, hops):
    """O defeito, reproduzido: com o padrão, dois usuários diferentes atrás do
    proxy gastam o mesmo limite."""
    hops(0)
    codigos_a = [await _esqueci(via_proxy, f"{CLIENTE_A}, {EDGE_CLOUDFLARE}") for _ in range(5)]
    codigo_b = await _esqueci(via_proxy, f"{CLIENTE_B}, {EDGE_CLOUDFLARE}")

    assert codigos_a == [503] * 5
    assert codigo_b == 429


async def test_com_hops_cada_cliente_tem_o_proprio_balde(via_proxy, email_desligado, hops):
    hops(2)
    codigos_a = [await _esqueci(via_proxy, f"{CLIENTE_A}, {EDGE_CLOUDFLARE}") for _ in range(6)]
    codigo_b = await _esqueci(via_proxy, f"{CLIENTE_B}, {EDGE_CLOUDFLARE}")

    assert codigos_a == [503] * 5 + [429], "o limite de 5/min do cliente A mudou"
    assert codigo_b == 503, "o cliente B herdou o balde do cliente A"


async def test_falsificar_o_cabecalho_nao_burla_o_limite(via_proxy, email_desligado, hops):
    """O ataque: trocar o X-Forwarded-For a cada pedido para parecer outra
    pessoa. Os proxies acrescentam o IP real à direita, e é ele que conta."""
    hops(2)
    codigos = [
        await _esqueci(via_proxy, f"192.0.2.{i}, {CLIENTE_A}, {EDGE_CLOUDFLARE}") for i in range(8)
    ]
    assert codigos[:5] == [503] * 5
    assert set(codigos[5:]) == {429}


async def test_cabecalho_curto_demais_nao_abre_balde_novo(via_proxy, email_desligado, hops):
    """Requisição com uma entrada só (fora da cadeia esperada) cai no balde da
    conexão — não ganha um balde por valor forjado."""
    hops(2)
    codigos = [await _esqueci(via_proxy, f"192.0.2.{i}") for i in range(6)]
    assert codigos == [503] * 5 + [429]


async def test_login_mantem_o_limite_de_10_por_minuto(via_proxy, hops):
    """Os limites existentes não mudaram com a troca da chave."""
    hops(2)
    xff = {"X-Forwarded-For": f"{CLIENTE_A}, {EDGE_CLOUDFLARE}"}
    codigos = [
        (
            await via_proxy.post(
                f"{PREFIX}/auth/login",
                json={"email": "ninguem@example.com", "password": "errada-123"},
                headers=xff,
            )
        ).status_code
        for _ in range(11)
    ]
    assert codigos == [401] * 10 + [429]


async def test_ipv6_do_mesmo_slash_64_divide_o_balde(via_proxy, email_desligado, hops):
    hops(2)
    codigos = [
        await _esqueci(via_proxy, f"2001:db8:1:2::{i:x}, {EDGE_CLOUDFLARE}") for i in range(1, 7)
    ]
    outro_64 = await _esqueci(via_proxy, f"2001:db8:1:3::1, {EDGE_CLOUDFLARE}")
    assert codigos == [503] * 5 + [429]
    assert outro_64 == 503


# --- diagnóstico GET /health/proxy -------------------------------------------------


@pytest.fixture
def diagnostico(monkeypatch):
    monkeypatch.setenv("PROXY_DIAGNOSTICS_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_diagnostico_desligado_responde_404(via_proxy, monkeypatch):
    monkeypatch.delenv("PROXY_DIAGNOSTICS_ENABLED", raising=False)
    get_settings.cache_clear()
    resposta = await via_proxy.get("/health/proxy")
    assert resposta.status_code == 404


async def test_diagnostico_mostra_a_forma_da_cadeia_sem_ip_completo(
    via_proxy, diagnostico, hops, caplog
):
    hops(0)
    caplog.set_level(logging.DEBUG)
    resposta = await via_proxy.get(
        "/health/proxy",
        headers={"X-Forwarded-For": f"192.0.2.55, {CLIENTE_A}, {EDGE_CLOUDFLARE}"},
    )

    assert resposta.status_code == 200
    assert resposta.headers["cache-control"] == "no-store"
    corpo = resposta.json()
    assert corpo["trusted_proxy_hops"] == 0
    assert corpo["conexao"] == {"tipo": "privado", "rede": "10.21.157.0/24"}
    assert corpo["x_forwarded_for"]["total"] == 3
    # As faixas de documentação (RFC 5737) contam como não-globais para o
    # `ipaddress`, por isso "privado"; o IP de edge da Cloudflare é público.
    assert corpo["x_forwarded_for"]["entradas"] == [
        {"posicao_da_direita": 3, "tipo": "privado", "rede": "192.0.2.0/24"},
        {"posicao_da_direita": 2, "tipo": "privado", "rede": "198.51.100.0/24"},
        {"posicao_da_direita": 1, "tipo": "publico", "rede": "104.16.0.0/24"},
    ]
    assert corpo["chave_do_rate_limit"]["origem"] == "peer"

    # Nenhum IP completo sai na resposta nem nos logs.
    for ip in ("192.0.2.55", CLIENTE_A, EDGE_CLOUDFLARE, PROXY_RENDER):
        assert ip not in resposta.text
        assert ip not in caplog.text


async def test_diagnostico_mostra_a_chave_escolhida_com_hops(via_proxy, diagnostico, hops):
    hops(2)
    corpo = (
        await via_proxy.get(
            "/health/proxy", headers={"X-Forwarded-For": f"{CLIENTE_A}, {EDGE_CLOUDFLARE}"}
        )
    ).json()
    assert corpo["chave_do_rate_limit"] == {
        "origem": "forwarded",
        "tipo": "privado",  # faixa de documentação; ver o teste acima
        "rede": "198.51.100.0/24",
    }


async def test_diagnostico_limita_entradas_mostradas(via_proxy, diagnostico):
    xff = ", ".join(f"192.0.2.{i}" for i in range(50))
    corpo = (await via_proxy.get("/health/proxy", headers={"X-Forwarded-For": xff})).json()
    assert corpo["x_forwarded_for"]["total"] == 50
    assert len(corpo["x_forwarded_for"]["entradas"]) == 10
    # As mostradas são as da direita: as que os proxies escrevem.
    assert corpo["x_forwarded_for"]["entradas"][-1]["posicao_da_direita"] == 1


def test_mascaras_do_diagnostico():
    assert client_ip.mask_ip(ipaddress.ip_address("198.51.100.7")) == "198.51.100.0/24"
    assert client_ip.mask_ip(ipaddress.ip_address("2001:db8:1:2::1")) == "2001:db8:1::/48"
