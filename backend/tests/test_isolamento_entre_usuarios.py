"""Um usuário não alcança o dado de outro.

As rotas verificam posse — `get_owned(id, current_user.id)` e
`get_owned_detail(id, current_user.id)` — em sete pontos. **Nenhum teste
garantia isso.** Trocar `get_owned_detail(id, user_id)` por `get(id)` num
refactor deixaria os 709 testes existentes passando e embarcaria um IDOR: um
usuário lendo a análise, o repositório e o relatório de outro.

Estes testes cobrem toda rota que recebe um identificador. Um endpoint novo que
esqueça a verificação de posse não é pego por eles automaticamente — por isso o
último teste enumera as rotas e falha quando aparece uma que não está coberta
aqui.

A resposta esperada é **404, não 403**: dizer "existe, mas não é seu" já vaza a
existência do recurso.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.analysis import Analysis, AnalysisResult
from app.models.enums import AnalysisStatus, Dimension
from app.models.readme import GeneratedReadme
from app.models.repository import Repository
from app.models.user import User

settings = get_settings()
PREFIX = settings.api_v1_prefix


async def _criar_usuario(db_session, apelido: str) -> User:
    user = User(
        email=f"{apelido}-{uuid.uuid4().hex[:6]}@exemplo.test",
        hashed_password=hash_password("senha-de-teste-bem-comprida"),
        username=f"{apelido}{uuid.uuid4().hex[:6]}",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def cenario(db_session):
    """Dono com um repositório e uma análise concluída; e um intruso sem nada."""
    dono = await _criar_usuario(db_session, "dono")
    intruso = await _criar_usuario(db_session, "intruso")

    repo = Repository(
        user_id=dono.id, github_repo_id=987, full_name="dono/privado", default_branch="main"
    )
    db_session.add(repo)
    await db_session.commit()
    await db_session.refresh(repo)

    analise = Analysis(repository_id=repo.id, status=AnalysisStatus.DONE, overall_score=80.0)
    db_session.add(analise)
    await db_session.commit()
    await db_session.refresh(analise)

    db_session.add(
        AnalysisResult(
            analysis_id=analise.id,
            dimension=Dimension.SECURITY,
            score=80,
            summary="resumo do dono",
            findings=[],
        )
    )
    db_session.add(GeneratedReadme(analysis_id=analise.id, content="# README privado do dono"))
    await db_session.commit()

    return {"dono": dono, "intruso": intruso, "repo": repo, "analise": analise}


# --- toda rota que recebe um id -----------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metodo,caminho",
    [
        ("get", "/analysis/{analysis_id}"),
        ("get", "/analysis/{analysis_id}/readme"),
        ("get", "/reports/{analysis_id}/pdf"),
    ],
)
async def test_intruso_nao_alcanca_analise_alheia(
    client: AsyncClient, authed_client_factory, cenario, metodo, caminho
):
    rota = f"{PREFIX}{caminho.format(analysis_id=cenario['analise'].id)}"
    headers = authed_client_factory(cenario["intruso"].id)

    resposta = await getattr(client, metodo)(rota, headers=headers)

    # 404 e não 403: distinguir "não existe" de "não é seu" já vaza a
    # existência do recurso.
    assert resposta.status_code == 404, f"{metodo.upper()} {rota} devolveu {resposta.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("rota", ["/readme", "/fix"])
async def test_intruso_nao_alcanca_rota_de_ia_alheia(
    client: AsyncClient, authed_client_factory, cenario, override_ai_provider, rota
):
    """As rotas de IA precisam barrar o intruso **antes** de gastar a cota de
    quem paga.

    O provedor é injetado aqui de propósito. O FastAPI resolve as dependências
    antes de entrar no corpo, então sem provedor configurado estas rotas
    respondem 503 para todo mundo — dono ou não. Não é bypass: ninguém alcança
    o recurso. Mas é o caminho com provedor que precisa ser verificado, porque
    é nele que a checagem de posse de fato roda.
    """
    override_ai_provider(
        text_responses=["# README"], json_responses=[{"suggested_code": "x", "explanation": "y"}]
    )
    headers = authed_client_factory(cenario["intruso"].id)
    corpo = {"title": "t", "description": "d"} if rota == "/fix" else None

    resposta = await client.post(
        f"{PREFIX}/analysis/{cenario['analise'].id}{rota}", json=corpo, headers=headers
    )
    assert resposta.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "caminho",
    ["/repos/{repository_id}", "/repos/{repository_id}/github-summary"],
)
async def test_intruso_nao_alcanca_repositorio_alheio(
    client: AsyncClient, authed_client_factory, cenario, caminho
):
    rota = f"{PREFIX}{caminho.format(repository_id=cenario['repo'].id)}"
    headers = authed_client_factory(cenario["intruso"].id)

    assert (await client.get(rota, headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_intruso_nao_lista_analises_de_repositorio_alheio(
    client: AsyncClient, authed_client_factory, cenario
):
    headers = authed_client_factory(cenario["intruso"].id)
    resposta = await client.get(
        f"{PREFIX}/analysis", params={"repository_id": str(cenario["repo"].id)}, headers=headers
    )
    assert resposta.status_code == 404


@pytest.mark.asyncio
async def test_intruso_nao_dispara_analise_em_repositorio_alheio(
    client: AsyncClient, authed_client_factory, cenario, monkeypatch
):
    """Escrita, não só leitura: o intruso não pode nem começar uma análise."""

    async def nunca_deveria_rodar(analysis_id):  # pragma: no cover
        raise AssertionError("a análise foi enfileirada para um intruso")

    monkeypatch.setattr("app.api.routes.analysis.run_repository_analysis", nunca_deveria_rodar)
    headers = authed_client_factory(cenario["intruso"].id)

    resposta = await client.post(
        f"{PREFIX}/analysis",
        json={"repository_id": str(cenario["repo"].id)},
        headers=headers,
    )
    assert resposta.status_code == 404


# --- o dono continua alcançando o que é dele ---------------------------------


@pytest.mark.asyncio
async def test_o_dono_alcanca_a_propria_analise(
    client: AsyncClient, authed_client_factory, cenario
):
    """A trava contra o excesso de zelo: negar para todo mundo também passaria
    nos testes acima."""
    headers = authed_client_factory(cenario["dono"].id)

    resposta = await client.get(f"{PREFIX}/analysis/{cenario['analise'].id}", headers=headers)
    assert resposta.status_code == 200
    assert resposta.json()["results"][0]["summary"] == "resumo do dono"


@pytest.mark.asyncio
async def test_o_dono_alcanca_o_proprio_readme(client: AsyncClient, authed_client_factory, cenario):
    headers = authed_client_factory(cenario["dono"].id)
    resposta = await client.get(
        f"{PREFIX}/analysis/{cenario['analise'].id}/readme", headers=headers
    )
    assert resposta.status_code == 200
    assert "README privado do dono" in resposta.text


# --- nenhuma rota nova pode escapar ------------------------------------------


def test_toda_rota_com_identificador_esta_coberta_aqui():
    """Enumera as rotas registradas e falha quando aparece uma que recebe um
    identificador de recurso sem estar nesta suíte.

    Sem isto, um endpoint novo entraria sem verificação de posse e sem ninguém
    perceber — que é exatamente o buraco que esta suíte existe para fechar.
    """
    from app.main import app

    COBERTAS = {
        ("GET", f"{PREFIX}/analysis/{{analysis_id}}"),
        ("GET", f"{PREFIX}/analysis/{{analysis_id}}/readme"),
        ("POST", f"{PREFIX}/analysis/{{analysis_id}}/readme"),
        ("POST", f"{PREFIX}/analysis/{{analysis_id}}/fix"),
        ("GET", f"{PREFIX}/reports/{{analysis_id}}/pdf"),
        ("GET", f"{PREFIX}/repos/{{repository_id}}"),
        ("GET", f"{PREFIX}/repos/{{repository_id}}/github-summary"),
        # Recebe o id no corpo, coberta por
        # `test_intruso_nao_dispara_analise_em_repositorio_alheio`.
        ("POST", f"{PREFIX}/analysis"),
    }

    encontradas = set()
    for rota in app.routes:
        caminho = getattr(rota, "path", "")
        if "{analysis_id}" not in caminho and "{repository_id}" not in caminho:
            continue
        for metodo in getattr(rota, "methods", set()) - {"HEAD", "OPTIONS"}:
            encontradas.add((metodo, caminho))

    descobertas = encontradas - COBERTAS
    assert not descobertas, (
        f"rotas com identificador sem teste de isolamento: {sorted(descobertas)}. "
        "Acrescente o caso nesta suíte antes de mergear."
    )


# --- os agregados do dashboard também são por usuário ------------------------


@pytest.mark.asyncio
async def test_dashboard_do_intruso_nao_conta_dados_alheios(
    client: AsyncClient, authed_client_factory, cenario
):
    """Os agregados são somas e médias sobre o banco inteiro, filtradas por
    dono. Remover esse filtro não quebra nenhuma consulta — só passa a somar o
    de todo mundo, silenciosamente.

    Verificado por mutação: retirando o filtro das três agregações, os 721
    testes anteriores continuavam passando.
    """
    headers = authed_client_factory(cenario["intruso"].id)
    resumo = (await client.get(f"{PREFIX}/dashboard/summary", headers=headers)).json()

    assert resumo["repositories_analyzed"] == 0
    assert resumo["total_analyses"] == 0
    assert resumo["average_score"] is None
    assert resumo["total_findings"] == 0
    assert resumo["total_suggestions"] == 0
    assert resumo["recent_history"] == []


@pytest.mark.asyncio
async def test_dashboard_do_dono_conta_os_dados_dele(
    client: AsyncClient, authed_client_factory, cenario
):
    """A trava do outro lado: zerar tudo para todo mundo também passaria no
    teste acima."""
    headers = authed_client_factory(cenario["dono"].id)
    resumo = (await client.get(f"{PREFIX}/dashboard/summary", headers=headers)).json()

    assert resumo["repositories_analyzed"] == 1
    assert resumo["total_analyses"] == 1
    assert resumo["average_score"] == 80.0
    assert len(resumo["recent_history"]) == 1


# --- nenhuma rota de negócio pode ser pública --------------------------------


def test_toda_rota_de_negocio_exige_autenticacao():
    """`SECURITY.md`: "JWT assinado, validado em toda rota protegida".

    Uma rota nova sem `Depends(get_current_user)` fica pública em silêncio —
    nenhum teste existente notaria, porque testes de rota autenticam por
    hábito e nunca perguntam o que acontece sem token.

    A lista abaixo é de exceções deliberadas. Acrescentar algo a ela é uma
    decisão explícita, que aparece no diff.
    """
    import inspect

    from app.api.deps import get_current_user
    from app.main import app

    PUBLICAS = {
        # Documentação e sonda de saúde.
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/health",
        # O usuário ainda não tem token nestas.
        f"{PREFIX}/auth/register",
        f"{PREFIX}/auth/login",
        # Logout é do lado do cliente: o token é stateless e o servidor não
        # guarda blocklist. Exigir token aqui não protegeria nada.
        f"{PREFIX}/auth/logout",
    }

    desprotegidas = set()
    for rota in app.routes:
        caminho = getattr(rota, "path", "")
        endpoint = getattr(rota, "endpoint", None)
        metodos = getattr(rota, "methods", set()) - {"HEAD", "OPTIONS"}
        if not metodos or endpoint is None or caminho in PUBLICAS:
            continue
        try:
            parametros = inspect.signature(endpoint).parameters.values()
        except (TypeError, ValueError):  # pragma: no cover
            continue
        if not any(getattr(p.default, "dependency", None) is get_current_user for p in parametros):
            desprotegidas.add((sorted(metodos)[0], caminho))

    assert not desprotegidas, (
        f"rotas sem autenticação: {sorted(desprotegidas)}. Ou acrescente "
        "`Depends(get_current_user)`, ou declare a exceção na lista PUBLICAS."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metodo,caminho",
    [
        ("get", "/auth/me"),
        ("get", "/repos"),
        ("get", "/analysis"),
        ("get", "/dashboard/summary"),
        ("get", "/settings/github-token"),
    ],
)
async def test_sem_token_a_rota_recusa(client: AsyncClient, metodo, caminho):
    """A trava acima é estrutural — lê assinaturas. Esta verifica o efeito de
    verdade, numa amostra: sem cabeçalho de autorização, a resposta é 401."""
    resposta = await getattr(client, metodo)(f"{PREFIX}{caminho}")
    assert resposta.status_code == 401
