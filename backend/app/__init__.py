"""Pacote da aplicação.

`__version__` é a **única** fonte da versão para o código. Os outros três
lugares que declaram versão — `pyproject.toml`, `frontend/package.json` e o
selo do README — são arquivos de metadados que não dá para importar daqui, e
por isso `tests/test_versao.py` confere que os quatro concordam.

Isso não é zelo excessivo: três deles estavam parados em 0.1.0 enquanto o
projeto ia na 0.3.3, e o do `FastAPI(version=...)` aparecia em `/docs` e no
`/openapi.json` — ou seja, a API dizia à quem a consome uma versão que não era
a dela.
"""

__version__ = "0.3.4"
