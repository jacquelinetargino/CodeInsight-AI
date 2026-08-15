"""Detecção de linguagem: determinística, por extensão e nomes especiais."""

from pathlib import Path

import pytest

from app.engine.languages import detect_language


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("app.py", "Python"),
        ("main.PY", "Python"),  # extensão em maiúsculas
        ("index.ts", "TypeScript"),
        ("Component.tsx", "TypeScript"),
        ("server.js", "JavaScript"),
        ("Main.java", "Java"),
        ("main.go", "Go"),
        ("lib.rs", "Rust"),
        ("style.scss", "SCSS"),
        ("config.yml", "YAML"),
        ("data.json", "JSON"),
        ("README.md", "Markdown"),
        ("query.sql", "SQL"),
        ("deploy.sh", "Shell"),
    ],
)
def test_detects_by_extension(nome: str, esperado: str):
    assert detect_language(nome) == esperado


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("Dockerfile", "Dockerfile"),
        ("dockerfile", "Dockerfile"),
        ("Makefile", "Makefile"),
        ("CMakeLists.txt", "CMake"),
        ("Gemfile", "Ruby"),
        ("Jenkinsfile", "Groovy"),
    ],
)
def test_detects_by_special_filename(nome: str, esperado: str):
    assert detect_language(nome) == esperado


def test_special_name_wins_over_extension():
    """`Dockerfile.prod` é Dockerfile — `.prod` não significa nada."""
    assert detect_language("Dockerfile.prod") == "Dockerfile"


@pytest.mark.parametrize(
    "nome",
    [
        "arquivo.desconhecido",
        "binario.xyz",
        "LICENSE",  # sem extensão e sem nome especial
        ".gitignore",  # oculto sem extensão
        ".env",
    ],
)
def test_returns_none_when_unknown(nome: str):
    """Dizer 'não sei' é melhor do que chutar e enviesar o score."""
    assert detect_language(nome) is None


def test_accepts_path_and_str():
    assert detect_language(Path("src/app.py")) == "Python"
    assert detect_language("src/app.py") == "Python"


def test_unicode_filename():
    assert detect_language("relatório_análise.py") == "Python"
    assert detect_language("配置.yaml") == "YAML"


def test_is_deterministic():
    """Mesma entrada, mesma saída — sem estado, sem aleatoriedade."""
    assert {detect_language("app.py") for _ in range(50)} == {"Python"}
