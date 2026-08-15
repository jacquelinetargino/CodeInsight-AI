"""Detecção de testes: framework, organização e volume.

Os testes do repositório analisado **nunca são executados**. Rodar a suíte de
terceiros seria executar código arbitrário — exatamente o que o motor promete
não fazer. Tudo aqui é inferido de nomes de arquivo, imports e configuração.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

# Import ou chamada que denuncia o framework. Casado contra o conteúdo do
# arquivo, não contra o nome — `import pytest` é evidência mais forte que um
# arquivo chamado `test_x.py`.
FRAMEWORK_SIGNATURES: dict[str, re.Pattern[str]] = {
    "pytest": re.compile(r"^\s*(?:import\s+pytest|from\s+pytest\b)", re.MULTILINE),
    "unittest": re.compile(r"^\s*(?:import\s+unittest|from\s+unittest\b)", re.MULTILINE),
    "jest": re.compile(r"\b(?:from\s+['\"]@jest|jest\.(?:mock|fn|spyOn))", re.MULTILINE),
    "vitest": re.compile(r"\bfrom\s+['\"]vitest['\"]", re.MULTILINE),
    "testing-library": re.compile(r"@testing-library/", re.MULTILINE),
    "junit": re.compile(r"\bimport\s+org\.junit", re.MULTILINE),
    "go-testing": re.compile(r"^\s*func\s+Test\w+\s*\(\s*t\s+\*testing\.T", re.MULTILINE),
    "rspec": re.compile(r"^\s*(?:require\s+['\"]rspec|RSpec\.describe)", re.MULTILINE),
    "cargo-test": re.compile(r"#\[(?:test|cfg\(test\))\]", re.MULTILINE),
}

# Padrões de nome que identificam arquivo de teste em cada ecossistema.
_TEST_FILE_PATTERNS = (
    re.compile(r"(?:^|/)test_[^/]+\.py$"),
    re.compile(r"(?:^|/)[^/]+_test\.py$"),
    re.compile(r"(?:^|/)[^/]+\.(?:test|spec)\.(?:js|jsx|ts|tsx)$"),
    re.compile(r"(?:^|/)[^/]+Test\.java$"),
    re.compile(r"(?:^|/)[^/]+_test\.go$"),
    re.compile(r"(?:^|/)[^/]+_spec\.rb$"),
)

# Diretórios convencionais de teste.
_TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec", "e2e", "integration"}

# Arquivos de configuração que indicam infraestrutura de teste montada.
TEST_CONFIG_FILES = {
    "pytest.ini",
    "tox.ini",
    "jest.config.js",
    "jest.config.ts",
    "vitest.config.ts",
    "vitest.config.js",
    "karma.conf.js",
    "phpunit.xml",
}

# Configuração de cobertura.
COVERAGE_CONFIG_FILES = {".coveragerc", "codecov.yml", ".codecov.yml", "coverage.xml"}

# Extensões que contam como código-fonte para a proporção teste/fonte.
_SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".php"}


@dataclass
class TestingReport:
    """Panorama de testes do repositório."""

    frameworks: set[str] = field(default_factory=set)
    test_files: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    test_directories: set[str] = field(default_factory=set)
    has_test_config: bool = False
    has_coverage_config: bool = False

    @property
    def test_ratio(self) -> float:
        """Arquivos de teste por arquivo de fonte. Não é cobertura — cobertura
        exigiria executar a suíte, o que o motor não faz."""
        if not self.source_files:
            return 0.0
        return len(self.test_files) / len(self.source_files)


def is_test_file(relative_path: str) -> bool:
    caminho = relative_path.replace("\\", "/")
    if any(padrao.search(caminho) for padrao in _TEST_FILE_PATTERNS):
        return True
    # Arquivo dentro de diretório de teste conta mesmo sem o nome convencional.
    return any(parte in _TEST_DIR_NAMES for parte in Path(caminho).parts[:-1])


def detect_frameworks(content: str) -> set[str]:
    return {nome for nome, padrao in FRAMEWORK_SIGNATURES.items() if padrao.search(content)}


def is_source_file(relative_path: str) -> bool:
    return Path(relative_path).suffix.lower() in _SOURCE_EXTENSIONS
