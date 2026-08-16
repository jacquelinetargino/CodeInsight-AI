"""Métricas estruturais do repositório.

Tudo aqui é heurística sobre organização de arquivos e diretórios — não há como
provar que uma estrutura é "ruim", só apontar sinais conhecidos de dificuldade
de manutenção. Por isso os achados derivados carregam confiança baixa e a
redação evita afirmar certeza.
"""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Acima disto um arquivo deixa de caber na cabeça de quem lê. Convencional.
LARGE_FILE_LINES = 500
HUGE_FILE_LINES = 1000

# Profundidade a partir da qual navegar vira custo.
MAX_REASONABLE_DEPTH = 6

# Arquivos soltos na raiz acima disto indicam falta de organização. Manifests e
# documentação de topo são normais, então o teto é generoso.
MAX_ROOT_FILES = 25

# Diretórios que indicam separação de responsabilidades quando presentes.
LAYER_DIRECTORY_NAMES = {
    "src",
    "app",
    "lib",
    "core",
    "domain",
    "services",
    "models",
    "controllers",
    "routes",
    "api",
    "handlers",
    "components",
    "pages",
    "utils",
    "internal",
    "pkg",
}


@dataclass
class ArchitectureReport:
    """Panorama estrutural. Guarda os números crus para que o analyzer decida —
    manter medição e julgamento separados deixa a heurística auditável."""

    total_files: int = 0
    root_files: list[str] = field(default_factory=list)
    max_depth: int = 0
    deep_paths: list[str] = field(default_factory=list)
    large_files: list[tuple[str, int]] = field(default_factory=list)
    huge_files: list[tuple[str, int]] = field(default_factory=list)
    directories: set[str] = field(default_factory=set)
    layer_directories: set[str] = field(default_factory=set)
    files_per_directory: Counter = field(default_factory=Counter)

    @property
    def has_layered_structure(self) -> bool:
        return bool(self.layer_directories)


def path_depth(relative_path: str) -> int:
    """Número de diretórios até o arquivo. `a/b/c.py` tem profundidade 2."""
    return len(Path(relative_path).parts) - 1


def count_lines(content: str) -> int:
    return content.count("\n") + (1 if content and not content.endswith("\n") else 0)
