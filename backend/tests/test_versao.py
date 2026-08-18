"""Os quatro lugares que declaram a versão precisam concordar.

Não é zelo excessivo — eles tinham divergido. Enquanto o projeto ia na 0.3.3,
`pyproject.toml`, `frontend/package.json` e o `FastAPI(version=...)` estavam
parados na 0.1.0. Só o selo do README era atualizado a cada release, porque é o
único que alguém olha.

O do FastAPI é o que mais incomoda: ele aparece em `/docs` e no `/openapi.json`,
ou seja, a API informava a quem a consome uma versão que não era a dela. Do
mesmo tipo das afirmações que os PRs 25-27 tiraram dos relatórios, só que sobre
a própria aplicação.

Também confere que a versão declarada tem uma entrada no CHANGELOG: subir a
versão sem dizer o que mudou é a outra metade do mesmo problema.
"""

import json
import re
from pathlib import Path

import pytest

from app import __version__
from app.main import app

RAIZ = Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "backend"


def test_a_aplicacao_publica_a_versao_do_pacote():
    """`/openapi.json` e `/docs` mostram este valor."""
    assert app.version == __version__


def test_pyproject_declara_a_mesma_versao():
    conteudo = (BACKEND / "pyproject.toml").read_text(encoding="utf-8")
    achado = re.search(r'^version\s*=\s*"([^"]+)"', conteudo, re.MULTILINE)
    assert achado is not None, "pyproject.toml não declara version"
    assert achado.group(1) == __version__


def test_package_json_do_frontend_declara_a_mesma_versao():
    dados = json.loads((RAIZ / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert dados["version"] == __version__


def test_o_selo_do_readme_mostra_a_mesma_versao():
    conteudo = (RAIZ / "README.md").read_text(encoding="utf-8")
    achado = re.search(r"badge/version-([0-9A-Za-z.\-]+?)-", conteudo)
    assert achado is not None, "README não tem o selo de versão"
    assert achado.group(1) == __version__


def test_a_versao_segue_o_versionamento_semantico():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__


def test_o_changelog_tem_uma_entrada_para_a_versao():
    """Subir a versão sem registrar o que mudou é a outra metade do problema."""
    conteudo = (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in conteudo, (
        f"CHANGELOG.md não tem seção para a versão {__version__} — "
        "a versão subiu sem dizer o que mudou"
    )


@pytest.mark.parametrize("arquivo", ["CHANGELOG.md", "README.md"])
def test_a_versao_anterior_nao_ficou_como_atual(arquivo: str):
    """Trava frouxa de propósito: só garante que o arquivo foi tocado na release,
    não que o texto esteja certo."""
    conteudo = (RAIZ / arquivo).read_text(encoding="utf-8")
    assert __version__ in conteudo
