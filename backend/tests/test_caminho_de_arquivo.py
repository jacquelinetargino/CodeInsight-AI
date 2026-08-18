"""`file_path` de `POST /analysis/{id}/fix` escapava do repositório.

Mesma classe do PR 35, por outra porta. O front reenvia o `file_path` do achado
e ele entra no CAMINHO de uma URL da GitHub API:

    /repos/{full_name}/contents/{file_path}

O httpx normaliza `..` no momento em que a URL é construída, então um segmento a
mais troca o endpoint chamado. Medido antes da correção, interceptando a
requisição real que sai:

    file_path = "../../../../user"
    -> https://api.github.com/user

    file_path = "../../../vitima/repo-privado/contents/.env"
    -> https://api.github.com/repos/vitima/repo-privado/contents/.env

A requisição sai com `Authorization: Bearer` — o PAT do usuário, ou, quando ele
não conectou nenhum, o `GITHUB_TOKEN` do próprio servidor. O conteúdo volta em
base64, é decodificado e segue para o provedor de IA como contexto da correção,
que o usuário lê. Ou seja: com token de servidor configurado, qualquer usuário
autenticado lia qualquer repositório que aquele token alcança.

Os testes abaixo interceptam a requisição de verdade em vez de conferir a
string do caminho: o que interessa é qual URL o httpx monta no fim, e foi
justamente a diferença entre as duas coisas que abriu o buraco.
"""

import base64
import uuid

import httpx
import pytest

from app.core.config import get_settings
from app.services import github_service
from app.services.github_service import InvalidFilePathError

settings = get_settings()
PREFIX = settings.api_v1_prefix

TOKEN_DO_SERVIDOR = "TOKEN-DO-SERVIDOR"
PREFIXO_ESPERADO = "https://api.github.com/repos/dono/repo/contents/"


@pytest.fixture
def requisicoes(monkeypatch):
    """Captura as requisições que sairiam para a GitHub API."""
    vistas: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistas.append(request)
        return httpx.Response(
            200,
            json={"encoding": "base64", "content": base64.b64encode(b"conteudo").decode()},
        )

    transport = httpx.MockTransport(handler)
    send_original = httpx.AsyncClient.send

    async def send(self, request, **kwargs):
        # Só o que vai para a GitHub API é interceptado. O `client` dos testes é
        # um AsyncClient também, e capturar tudo faria a própria chamada à API
        # da aplicação receber a resposta falsa.
        if request.url.host != "api.github.com":
            return await send_original(self, request, **kwargs)
        return await transport.handle_async_request(request)

    monkeypatch.setattr(httpx.AsyncClient, "send", send, raising=True)
    return vistas


# --- o escape ---------------------------------------------------------------


@pytest.mark.parametrize(
    "file_path",
    [
        pytest.param("../../../../user", id="alcanca-/user"),
        pytest.param("../../../vitima/repo-privado/contents/.env", id="outro-repositorio"),
        pytest.param("../../../../repos/vitima/privado/contents/.env", id="volta-para-repos"),
        pytest.param("a/../../../../user", id="escapa-no-meio"),
        pytest.param("../", id="so-navegacao"),
        pytest.param("..", id="ponto-ponto-sozinho"),
        pytest.param(".", id="ponto-sozinho"),
    ],
)
async def test_caminho_que_escapa_e_recusado_antes_de_qualquer_requisicao(
    file_path: str, requisicoes
):
    with pytest.raises(InvalidFilePathError):
        await github_service.get_file_content(TOKEN_DO_SERVIDOR, "dono/repo", file_path)

    assert requisicoes == [], (
        "a entrada foi recusada, mas uma requisição saiu assim mesmo — com a "
        f"credencial do servidor: {[str(r.url) for r in requisicoes]}"
    )


@pytest.mark.parametrize(
    "file_path",
    [
        pytest.param("x?ref=outra-branch", id="query-string"),
        pytest.param("x#fragmento", id="fragmento"),
        pytest.param("x%2F..%2Fy", id="percent"),
        pytest.param("/etc/passwd", id="caminho-absoluto"),
        pytest.param("a//b", id="segmento-vazio"),
        pytest.param("a/b/", id="barra-no-fim"),
        pytest.param("arquivo\x00.py", id="nul"),
        pytest.param("arquivo\n.py", id="quebra-de-linha"),
        pytest.param("", id="vazio"),
        pytest.param("   ", id="so-espaco"),
        pytest.param("a" * 5000, id="grande-demais"),
    ],
)
async def test_caminho_malformado_e_recusado(file_path: str, requisicoes):
    with pytest.raises(InvalidFilePathError):
        await github_service.get_file_content(TOKEN_DO_SERVIDOR, "dono/repo", file_path)

    assert requisicoes == []


# --- o que precisa continuar funcionando ------------------------------------


@pytest.mark.parametrize(
    "file_path",
    [
        "app/main.py",
        "README.md",
        ".github/workflows/ci.yml",
        "src/components/Button.test.tsx",
        "pasta com espaco/arquivo.py",
        "acentuação/ção.py",
        "a.b.c/d-e_f/g.py",
        "..oculto/arquivo.py",  # ponto-ponto NO NOME não é navegação
        "arquivo..py",
    ],
)
async def test_caminho_legitimo_passa_e_chega_ao_endpoint_certo(file_path: str, requisicoes):
    conteudo = await github_service.get_file_content(TOKEN_DO_SERVIDOR, "dono/repo", file_path)

    assert conteudo == "conteudo"
    assert len(requisicoes) == 1
    assert str(requisicoes[0].url).startswith(PREFIXO_ESPERADO), str(requisicoes[0].url)


# --- a rede embaixo: a guarda geral do _get ---------------------------------


async def test_guarda_do_get_pega_caminho_normalizado(requisicoes):
    """A validação de entrada é a primeira linha; esta é a que continua valendo
    para a chamada que alguém acrescentar amanhã.

    Chamar `_get` direto é o que um caminho novo faria — sem passar por
    `_validate_repo_file_path`.
    """
    with pytest.raises(InvalidFilePathError, match="reescrito"):
        await github_service._get("/repos/dono/repo/contents/../../../user", TOKEN_DO_SERVIDOR)

    assert requisicoes == []


async def test_guarda_do_get_deixa_passar_caminho_normal(requisicoes):
    await github_service._get("/repos/dono/repo/contents/app/main.py", TOKEN_DO_SERVIDOR)

    assert len(requisicoes) == 1


# --- pela API, que é por onde o atacante entra ------------------------------


@pytest.mark.asyncio
async def test_a_rota_de_correcao_recusa_caminho_que_escapa(
    client, test_user, authed_client_factory, override_ai_provider, requisicoes, db_session
):
    """A trava no ponto de entrada real. Um 500 aqui também "funcionaria" como
    recusa, mas 400 é a resposta correta para entrada inválida — e a diferença
    importa: 500 significa que a exceção escapou sem ninguém tratar.
    """
    from app.models.analysis import Analysis
    from app.models.enums import AnalysisStatus
    from app.models.repository import Repository

    repo = Repository(
        user_id=test_user.id,
        github_repo_id=7,
        full_name="dono/repo",
        default_branch="main",
        private=False,
    )
    db_session.add(repo)
    await db_session.commit()
    await db_session.refresh(repo)

    analysis = Analysis(repository_id=repo.id, status=AnalysisStatus.DONE)
    db_session.add(analysis)
    await db_session.commit()
    await db_session.refresh(analysis)

    override_ai_provider(json_responses=[{"suggested_code": "x", "explanation": "y"}])

    resposta = await client.post(
        f"{PREFIX}/analysis/{analysis.id}/fix",
        json={
            "title": "achado",
            "description": "descrição",
            "file_path": "../../../vitima/repo-privado/contents/.env",
        },
        headers=authed_client_factory(test_user.id),
    )

    assert resposta.status_code == 400, resposta.text
    assert requisicoes == [], (
        "a rota recusou, mas uma requisição saiu para a GitHub API: "
        f"{[str(r.url) for r in requisicoes]}"
    )


@pytest.mark.asyncio
async def test_a_rota_de_correcao_aceita_caminho_normal(
    client, test_user, authed_client_factory, override_ai_provider, requisicoes, db_session
):
    """A trava do outro lado: recusar tudo também passaria no teste acima."""
    from app.models.analysis import Analysis
    from app.models.enums import AnalysisStatus
    from app.models.repository import Repository

    repo = Repository(
        user_id=test_user.id,
        github_repo_id=8,
        full_name="dono/repo",
        default_branch="main",
        private=False,
    )
    db_session.add(repo)
    await db_session.commit()
    await db_session.refresh(repo)

    analysis = Analysis(repository_id=repo.id, status=AnalysisStatus.DONE)
    db_session.add(analysis)
    await db_session.commit()
    await db_session.refresh(analysis)

    override_ai_provider(json_responses=[{"suggested_code": "x", "explanation": "y"}])

    resposta = await client.post(
        f"{PREFIX}/analysis/{analysis.id}/fix",
        json={"title": "achado", "description": "descrição", "file_path": "app/main.py"},
        headers=authed_client_factory(test_user.id),
    )

    assert resposta.status_code == 201, resposta.text
    assert len(requisicoes) == 1
    assert str(requisicoes[0].url).startswith(PREFIXO_ESPERADO)


@pytest.mark.asyncio
async def test_analise_de_outro_usuario_continua_404(
    client, test_user, authed_client_factory, override_ai_provider, requisicoes
):
    """Sanidade: a validação nova não pode ter passado à frente do dono."""
    override_ai_provider(json_responses=[{"suggested_code": "x", "explanation": "y"}])

    resposta = await client.post(
        f"{PREFIX}/analysis/{uuid.uuid4()}/fix",
        json={"title": "a", "description": "b", "file_path": "../../../../user"},
        headers=authed_client_factory(test_user.id),
    )

    assert resposta.status_code == 404, resposta.text
    assert requisicoes == []
