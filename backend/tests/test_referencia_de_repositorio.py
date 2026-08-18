"""A referência de repositório vira caminho de URL da GitHub API.

`resolve_repo_full_name` recebe o que o usuário digitou e devolve `owner/repo`,
que é interpolado direto em `f"/repos/{full_name}"`. A requisição sai com o
**token do servidor** quando o usuário não tem PAT próprio
(`resolve_access_token`).

O padrão anterior aceitava qualquer coisa sem barra, e isso permitia escapar do
prefixo `/repos`:

    "../user"  ->  https://api.github.com/repos/../user
               ->  https://api.github.com/user        (normalizado pelo httpx)

Ou seja: um usuário autenticado escolhia qual endpoint da GitHub API o servidor
chamaria, com a credencial do servidor, e recebia a resposta. `?` no nome do
repositório injetava parâmetro de query pelo mesmo caminho.

Os testes abaixo cobrem os dois lados — o que precisa ser recusado e o que não
pode ser perdido.
"""

import httpx
import pytest

from app.services.github_service import (
    GITHUB_API_BASE,
    InvalidRepositoryReferenceError,
    resolve_repo_full_name,
)

# --- o que precisa ser recusado ----------------------------------------------

HOSTIS = {
    "traversal": "../user",
    "traversal_codificado": "..%2fuser",
    "traversal_no_repo": "octocat/..",
    "ponto_como_repo": "octocat/.",
    "injecao_de_query": "octocat/repo?per_page=999999",
    "injecao_de_token": "octocat/repo?access_token=roubado",
    "fragmento": "octocat/repo#outro",
    "barra_codificada": "octocat/repo%2f..%2f..",
    "credencial_embutida": "user:senha@host",
    "ponto_e_virgula": "octocat/repo;rm -rf",
    "comprimento_absurdo": "octocat/" + "a" * 300,
    "homoglifo_cirilico": "оctocat/Hello",
    "hifen_no_inicio": "-octocat/repo",
    "hifen_no_fim": "octocat-/repo",
    "byte_nulo": "octocat/repo\x00",
    "espaco": "octocat/re po",
    "duas_barras": "octocat/repo/extra",
}


@pytest.mark.parametrize("nome,entrada", HOSTIS.items())
def test_referencia_hostil_e_recusada(nome, entrada):
    with pytest.raises(InvalidRepositoryReferenceError):
        resolve_repo_full_name(entrada)


def test_nenhuma_referencia_aceita_escapa_do_prefixo_repos():
    """A propriedade que de fato importa, verificada no caminho final.

    Não basta recusar a lista acima: qualquer entrada aceita precisa produzir
    uma URL que continue sob `/repos/`, com exatamente dois segmentos e sem
    query.
    """
    aceitas = [
        "octocat/Hello-World",
        "github/.github",
        "org-name/my_repo-2.0",
        "https://github.com/psf/requests.git",
    ]
    for entrada in aceitas:
        url = httpx.URL(f"{GITHUB_API_BASE}/repos/{resolve_repo_full_name(entrada)}")

        assert url.host == "api.github.com"
        assert url.path.startswith("/repos/")
        assert len(url.path.strip("/").split("/")) == 3  # repos, owner, repo
        assert not url.query


# --- o que não pode ser perdido ----------------------------------------------

LEGITIMOS = {
    "owner/repo": ("octocat/Hello-World", "octocat/Hello-World"),
    "ponto_no_inicio": ("github/.github", "github/.github"),
    "sublinhado_e_ponto": ("org_1/repo.js", "org_1/repo.js"),
    "url_https": ("https://github.com/psf/requests", "psf/requests"),
    "url_com_git": ("https://github.com/psf/requests.git", "psf/requests"),
    "url_com_www": ("www.github.com/psf/requests", "psf/requests"),
    "url_com_barra_final": ("https://github.com/psf/requests/", "psf/requests"),
    "espacos_ao_redor": ("  octocat/Hello-World  ", "octocat/Hello-World"),
    "limite_de_tamanho": ("A" * 39 + "/" + "b" * 100, "A" * 39 + "/" + "b" * 100),
}


@pytest.mark.parametrize("nome,caso", LEGITIMOS.items())
def test_referencia_legitima_e_aceita(nome, caso):
    """A trava do outro lado: recusar tudo também passaria nos testes acima."""
    entrada, esperado = caso
    assert resolve_repo_full_name(entrada) == esperado


def test_o_sublinhado_no_dono_e_deliberado():
    """O GitHub documenta apenas alfanumérico e hífen para conta, mas
    sublinhado é inofensivo num caminho de URL. Aceitá-lo evita rejeitar alguma
    conta antiga sem abrir mão de nada — a decisão está registrada no módulo."""
    assert resolve_repo_full_name("dono_antigo/repo") == "dono_antigo/repo"
