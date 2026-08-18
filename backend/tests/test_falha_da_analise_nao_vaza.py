"""O que uma análise falhada conta para quem a pediu.

`Analysis.error_message` é devolvido por `GET /analysis/{id}` e renderizado na
página da análise. Ele recebia `str(exc)` de qualquer exceção que escapasse de
`run_repository_analysis`, ou seja, o texto era o que o Python tivesse a dizer.
Medido, com as exceções que de fato podem acontecer ali:

    FileNotFoundError  -> "[Errno 2] No such file or directory:
                           'C:\\Users\\Jacta\\AppData\\Local\\Temp\\
                            codeinsight-a1b2c3\\src\\repo-abc123\\x.py'"
    KeyError           -> "'chave_que_nao_existe'"
    HTTPStatusError    -> "Client error '404 Not Found' for url
                           'https://api.github.com/repos/alguem/privado'"

O primeiro entrega o caminho do diretório temporário e o nome da conta que roda
o servidor. O segundo não informa nada. O terceiro sabe algo útil — que o
repositório não foi encontrado — mas conta junto qual URL interna foi chamada.

E como as mensagens de erro do sistema de arquivos carregam o nome do arquivo,
o repositório analisado — que é dado NÃO CONFIÁVEL — escolhia parte do texto
exibido na página de quem pediu a análise.

A regra passa a ser: só chega ao usuário a mensagem escrita para ele. O detalhe
inteiro continua no log.
"""

import httpx
import pytest

from app.core.errors import FalhaVisivelAoUsuario
from app.engine.acquisition import AcquisitionError, RepositoryTooLargeError
from app.engine.pipeline import AnalysisTimeoutError
from app.tasks.analysis_tasks import ERRO_INTERNO, _mensagem_para_o_usuario

CAMINHO_DO_SERVIDOR = r"C:\Users\Jacta\AppData\Local\Temp\codeinsight-a1b2c3\src\repo\x.py"


# --- o que não pode passar ----------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(
            FileNotFoundError(2, "No such file or directory", CAMINHO_DO_SERVIDOR),
            id="caminho-do-servidor",
        ),
        pytest.param(KeyError("chave_que_nao_existe"), id="bug-de-programacao"),
        pytest.param(AttributeError("'NoneType' object has no attribute 'name'"), id="atributo"),
        pytest.param(
            RecursionError("maximum recursion depth exceeded while parsing"), id="recursao"
        ),
    ],
)
def test_excecao_inesperada_vira_mensagem_generica(exc: Exception):
    assert _mensagem_para_o_usuario(exc) == ERRO_INTERNO


def test_caminho_do_servidor_nao_aparece():
    """O teste acima já cobre por igualdade, mas este falha com uma mensagem que
    diz o que vazou — e continua valendo se o texto genérico for reescrito."""
    mensagem = _mensagem_para_o_usuario(
        FileNotFoundError(2, "No such file or directory", CAMINHO_DO_SERVIDOR)
    )
    for fragmento in ("C:\\", "AppData", "Temp", "codeinsight-a1b2c3", "Jacta"):
        assert fragmento not in mensagem, f"vazou {fragmento!r}: {mensagem!r}"


def test_conteudo_do_repositorio_analisado_nao_volta_na_mensagem():
    """Nome de arquivo vem do repositório, que é conteúdo não confiável. O React
    escapa na renderização, então não é XSS — mas texto escolhido por terceiro
    não deveria chegar a uma tela por um caminho que ninguém desenhou."""
    hostil = "<script>alert(1)</script>"
    exc = OSError(22, "Invalid argument", f"/tmp/codeinsight-x/src/repo/{hostil}")

    mensagem = _mensagem_para_o_usuario(exc)

    assert hostil not in mensagem
    assert mensagem == ERRO_INTERNO


# --- o que precisa continuar passando -----------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(
            AcquisitionError("Repositório ou referência não encontrada: o/r@main"),
            id="aquisicao",
        ),
        pytest.param(
            RepositoryTooLargeError("O repositório tem mais de 20000 arquivos analisáveis."),
            id="tamanho",
        ),
        pytest.param(
            AnalysisTimeoutError("A análise passou de 300 segundos e foi interrompida."),
            id="timeout",
        ),
        pytest.param(
            FalhaVisivelAoUsuario("O repositório desta análise não existe mais."),
            id="marca-direta",
        ),
    ],
)
def test_mensagem_escrita_para_o_usuario_chega_inteira(exc: Exception):
    assert _mensagem_para_o_usuario(exc) == str(exc)


def test_mensagem_longa_e_truncada():
    """O campo é Text no banco, mas devolver um texto sem teto para a interface
    não ajuda ninguém."""
    assert len(_mensagem_para_o_usuario(FalhaVisivelAoUsuario("x" * 5000))) == 2000


# --- GitHub: traduzido, não escondido ----------------------------------------


def _erro_http(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.github.com/repos/alguem/privado")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("erro", request=request, response=response)


@pytest.mark.parametrize(
    ("status_code", "trecho"),
    [
        (404, "não encontrou"),
        (403, "recusou o acesso"),
        (401, "recusou o acesso"),
        (429, "limite de requisições"),
        (500, "respondeu 500"),
    ],
)
def test_recusa_do_github_vira_texto_acionavel(status_code: int, trecho: str):
    mensagem = _mensagem_para_o_usuario(_erro_http(status_code))

    assert trecho in mensagem
    assert mensagem != ERRO_INTERNO


@pytest.mark.parametrize("status_code", [401, 403, 404, 429, 500])
def test_a_url_interna_nao_aparece_na_mensagem_do_github(status_code: int):
    """O texto do httpx traz a URL chamada. Ela descreve a integração, não o
    problema de quem pediu a análise."""
    mensagem = _mensagem_para_o_usuario(_erro_http(status_code))

    assert "api.github.com" not in mensagem
    assert "/repos/" not in mensagem
