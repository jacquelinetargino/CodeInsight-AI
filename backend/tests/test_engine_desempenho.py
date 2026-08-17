"""O que o profiler encontrou, transformado em trava.

`django/django` leva ~113s para 7008 arquivos. O profiler mostrou 57s dentro de
`_io.open` — 52% do total — e a leitura óbvia seria "cada analyzer relê os
arquivos, deduplique". **Medido, essa leitura está errada:**

    1a passada (fria)    34,5s   6,508 ms/arquivo
    2a passada (quente)   0,6s   0,120 ms/arquivo
    3a passada (quente)   0,6s   0,110 ms/arquivo

O custo é o **primeiro toque** numa árvore recém-extraída — comportamento do
sistema de arquivos e do antivírus, não desperdício do programa. Deduplicar as
releituras economizaria ~1,2s de 113s, menos de 2%.

Um pré-filtro por alternação para o detector de credenciais também foi medido e
saiu **mais lento** (78 ms contra 65 ms): 16 padrões numa alternação custam mais
para avaliar do que curto-circuitar por eles.

O que sobrou de desperdício real era invariante recalculado, e está travado
abaixo.
"""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.engine import scanner


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def build_repo(root: Path, quantidade: int) -> Path:
    for i in range(quantidade):
        (root / f"m{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
    return root


def test_a_raiz_e_resolvida_uma_vez_por_scan(tmp_path, monkeypatch):
    """`Path.resolve()` é uma syscall. Recalcular a raiz por arquivo eram
    28 032 chamadas a `_getfinalpathname` em django/django, metade delas para o
    mesmo valor."""
    build_repo(tmp_path, 40)

    original = Path.resolve
    resolvidos: list[str] = []

    def espiao(self, *args, **kwargs):
        resolvidos.append(str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", espiao)
    scanner.scan_repository(tmp_path)

    da_raiz = [r for r in resolvidos if r == str(tmp_path)]
    assert len(da_raiz) == 1, f"a raiz foi resolvida {len(da_raiz)} vezes"


def test_a_contencao_continua_valendo_com_a_raiz_pre_resolvida(tmp_path):
    """A otimização não pode afrouxar a barreira: caminho fora da raiz continua
    sendo recusado."""
    repo = tmp_path / "repo"
    repo.mkdir()
    intruso = tmp_path / "fora.py"
    intruso.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(scanner.ScanError, match="fora da raiz"):
        scanner._relative_path(repo.resolve(), intruso)


def test_caminho_dentro_da_raiz_e_aceito(tmp_path):
    dentro = tmp_path / "sub" / "a.py"
    dentro.parent.mkdir()
    dentro.write_text("x = 1\n", encoding="utf-8")

    assert scanner._relative_path(tmp_path.resolve(), dentro) == "sub/a.py"
