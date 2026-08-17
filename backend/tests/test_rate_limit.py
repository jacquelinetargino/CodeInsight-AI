"""As duas rotas caras têm limite de taxa, e ele dispara.

`SECURITY.md`, `README.md` e `docs/security.md` prometem limite em
`POST /analysis` (10/min/IP) e `POST /analysis/{id}/fix` (20/min/IP) — os dois
endpoints que disparam chamadas custosas ao provedor de IA.

Nada verificava. Remover o decorador `@limiter.limit(...)` não quebrava nenhum
teste, e a proteção sumiria em silêncio.

O limitador guarda contagem em memória, global ao processo. A fixture zera antes
e depois de cada teste daqui: sem isso, gastar o orçamento aqui faria os testes
de `test_analysis.py` receberem 429 e a suíte ficaria dependente da ordem.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.limiter import limiter

settings = get_settings()
PREFIX = settings.api_v1_prefix


@pytest.fixture(autouse=True)
def limitador_zerado():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def analise_nao_roda(monkeypatch):
    """O que está sob teste é o limite, não a análise."""

    async def noop(analysis_id):  # pragma: no cover
        pass

    monkeypatch.setattr("app.api.routes.analysis.run_repository_analysis", noop)


# --- o limite dispara ---------------------------------------------------------


@pytest.mark.asyncio
async def test_criacao_de_analise_e_limitada(
    client: AsyncClient, test_user, authed_client_factory, analise_nao_roda
):
    """10/minuto. O repositório nem precisa existir: o limitador roda antes da
    rota, então o 429 aparece mesmo com 404 nas primeiras."""
    headers = authed_client_factory(test_user.id)

    codigos = [
        (
            await client.post(
                f"{PREFIX}/analysis",
                json={"repository_id": str(uuid.uuid4())},
                headers=headers,
            )
        ).status_code
        for _ in range(12)
    ]

    assert 429 in codigos, f"o limite de 10/minute nunca disparou: {codigos}"
    assert (
        codigos.index(429) >= 10
    ), f"limitou cedo demais, na chamada {codigos.index(429) + 1}: {codigos}"


@pytest.mark.asyncio
async def test_correcao_e_limitada(
    client: AsyncClient, test_user, authed_client_factory, override_ai_provider
):
    """20/minuto por IP — o dobro da criação, porque é uma correção por achado e
    o usuário costuma pedir várias na mesma sessão.

    **Cada chamada usa um `analysis_id` diferente de propósito.** Foi assim que
    o defeito apareceu: com `key_style="url"` (o padrão do slowapi) o caminho
    concreto entra no balde, e ids diferentes nunca acumulavam. O limite valia
    por análise, não por IP.
    """
    override_ai_provider(json_responses=[{"suggested_code": "x", "explanation": "y"}] * 30)
    headers = authed_client_factory(test_user.id)

    codigos = [
        (
            await client.post(
                f"{PREFIX}/analysis/{uuid.uuid4()}/fix",
                json={"title": "t", "description": "d"},
                headers=headers,
            )
        ).status_code
        for _ in range(23)
    ]

    assert 429 in codigos, f"o limite de 20/minute nunca disparou: {codigos}"
    assert (
        codigos.index(429) >= 20
    ), f"limitou cedo demais, na chamada {codigos.index(429) + 1}: {codigos}"


# --- o limite não atrapalha o uso normal --------------------------------------


@pytest.mark.asyncio
async def test_uso_normal_nao_e_limitado(
    client: AsyncClient, test_user, authed_client_factory, analise_nao_roda
):
    """A trava do outro lado: limitar tudo também passaria nos testes acima."""
    headers = authed_client_factory(test_user.id)

    for _ in range(9):
        resposta = await client.post(
            f"{PREFIX}/analysis", json={"repository_id": str(uuid.uuid4())}, headers=headers
        )
        assert resposta.status_code != 429


@pytest.mark.asyncio
async def test_consulta_de_status_nao_e_limitada(
    client: AsyncClient, test_user, authed_client_factory
):
    """O frontend faz polling enquanto a análise roda. Limitar leitura
    transformaria a tela de progresso em erro."""
    headers = authed_client_factory(test_user.id)

    codigos = {
        (await client.get(f"{PREFIX}/settings/github-token", headers=headers)).status_code
        for _ in range(40)
    }
    assert codigos == {200}


# --- a configuração não pode voltar a prometer o que não faz ------------------


def test_nao_existe_limite_padrao_declarado():
    """Havia um `default_limits=["120/minute"]` que nunca se aplicava: o
    `slowapi` só impõe limite padrão pelo `SlowAPIMiddleware`, que a aplicação
    não registra. Medido, 130 chamadas a uma rota sem decorador responderam 200.

    Se alguém redeclarar o padrão, ou registra o middleware junto, ou este teste
    falha para lembrar que a promessa é vazia.
    """
    from app.main import app

    tem_middleware = any(
        "SlowAPI" in type(m.cls).__name__ or "SlowAPI" in str(getattr(m, "cls", ""))
        for m in app.user_middleware
    )
    padrao_declarado = bool(getattr(limiter, "_default_limits", []))

    assert not padrao_declarado or tem_middleware, (
        "limiter declara limite padrão mas SlowAPIMiddleware não está registrado — "
        "o padrão não se aplica a rota nenhuma"
    )


def test_o_balde_do_limite_e_por_endpoint_e_nao_por_url():
    """A trava da correção acima.

    Com `key_style="url"` o caminho concreto entra na chave do limite. Numa rota
    com id variável — `POST /analysis/{id}/fix` — isso dá um orçamento inteiro
    por análise: medido, 23 chamadas com ids diferentes e nenhum 429, quando o
    limite anunciado é de 20 por minuto.

    `POST /analysis` não sofria disso porque o caminho é fixo, e foi por isso
    que o defeito passou despercebido: um dos dois limites funcionava.
    """
    assert limiter._key_style == "endpoint"
