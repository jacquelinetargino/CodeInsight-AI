"""Detecção de linguagem determinística: extensão primeiro, nomes especiais
depois. Sem IA, sem heurística estatística, sem rede.

A regra é ser previsível e testável — o mesmo arquivo produz sempre a mesma
resposta, e cada mapeamento é uma linha auditável. Quando nada casa, a resposta é
`None`: dizer "não sei" é melhor do que chutar uma linguagem e enviesar o score.
"""

from pathlib import Path

# Extensão -> linguagem. Minúsculas; a busca normaliza antes de consultar.
EXTENSION_MAP: dict[str, str] = {
    # --- linguagens de programação ---
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".h": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".swift": "Swift",
    ".m": "Objective-C",
    ".scala": "Scala",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".dart": "Dart",
    ".lua": "Lua",
    ".pl": "Perl",
    ".r": "R",
    # --- shell ---
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".fish": "Shell",
    ".ps1": "PowerShell",
    # --- marcação, estilo e dados ---
    ".html": "HTML",
    ".htm": "HTML",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "SCSS",
    ".less": "Less",
    ".sql": "SQL",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "INI",
    ".xml": "XML",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".rst": "reStructuredText",
    ".txt": "Text",
    # --- infraestrutura ---
    ".tf": "Terraform",
    ".dockerfile": "Dockerfile",
    ".gradle": "Gradle",
    ".proto": "Protocol Buffers",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
}

# Arquivos sem extensão (ou com extensão que engana) cujo NOME identifica o
# formato. Só entram nomes em que o nome é de fato o indicador — manifestos como
# `requirements.txt` são dados de dependência, não linguagem, e ficam de fora.
FILENAME_MAP: dict[str, str] = {
    "dockerfile": "Dockerfile",
    "containerfile": "Dockerfile",
    "makefile": "Makefile",
    "gnumakefile": "Makefile",
    "cmakelists.txt": "CMake",
    "gemfile": "Ruby",
    "rakefile": "Ruby",
    "jenkinsfile": "Groovy",
    "vagrantfile": "Ruby",
    "brewfile": "Ruby",
}


def detect_language(path: Path | str) -> str | None:
    """Devolve a linguagem, ou `None` quando não há regra que case.

    Aceita `Path` ou string para servir tanto ao scanner (que tem Path) quanto a
    testes e chamadas com nome solto.
    """
    name = Path(path).name
    if not name:
        return None

    lowered = name.lower()

    # Nome especial tem prioridade: `Dockerfile.prod` é Dockerfile, e a extensão
    # `.prod` não significa nada.
    if lowered in FILENAME_MAP:
        return FILENAME_MAP[lowered]
    base = lowered.split(".", 1)[0]
    if base in FILENAME_MAP and lowered.startswith(f"{base}."):
        return FILENAME_MAP[base]

    # Arquivo oculto sem extensão (".gitignore") não tem linguagem: `suffix` do
    # pathlib devolve "" nesse caso, então a consulta abaixo simplesmente falha.
    suffix = Path(lowered).suffix
    if suffix:
        return EXTENSION_MAP.get(suffix)

    return None
