"""Leitura de documentação: quais seções um README cobre.

Markdown é lido como texto — cabeçalhos são extraídos por expressão regular, sem
renderizar nada. O reconhecimento de seção é por palavra-chave, em português e
inglês, porque repositório real vem nos dois idiomas.

A detecção é declaradamente heurística: um README pode explicar instalação sem
usar a palavra "instalação". Por isso os achados derivados daqui carregam
confiança abaixo de 1 — dizer "não encontrei" é diferente de "não existe".
"""

import re
from dataclasses import dataclass, field

# `# Título`, `## Título`, e também a forma sublinhada (`Título` + `====`).
_ATX_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(?P<texto>.+?)\s*#*\s*$", re.MULTILINE)
_SETEXT_HEADING_RE = re.compile(r"^(?P<texto>[^\n]+)\n[=-]{3,}\s*$", re.MULTILINE)

# Bloco de código cercado por crases ou til.
_CODE_FENCE_RE = re.compile(r"^\s{0,3}(?:```|~~~)", re.MULTILINE)

# Distintivos (badges) e imagens não são conteúdo explicativo.
_BADGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")

SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "installation": ("instala", "install", "setup", "getting started", "começando", "requisito"),
    "usage": ("uso", "usage", "como usar", "how to use", "utiliza", "quickstart", "exemplo"),
    "configuration": ("config", "configura", "environment", "ambiente", "variáve", "variave"),
    "api": ("api", "endpoint", "rota", "route", "reference", "referência", "referencia"),
    "architecture": ("arquitetura", "architecture", "estrutura", "structure", "design"),
    "contributing": ("contribu", "contributing", "development", "desenvolvimento"),
    "license": ("licen",),
    "testing": ("teste", "test"),
}


@dataclass
class ReadmeReport:
    """O que um README cobre.

    `sections` guarda os títulos crus; `covered` diz quais temas foram
    reconhecidos. Separar os dois deixa a heurística auditável.
    """

    headings: list[str] = field(default_factory=list)
    covered: set[str] = field(default_factory=set)
    content_length: int = 0
    has_code_examples: bool = False


def extract_headings(content: str) -> list[str]:
    titulos = [m.group("texto").strip() for m in _ATX_HEADING_RE.finditer(content)]
    titulos.extend(m.group("texto").strip() for m in _SETEXT_HEADING_RE.finditer(content))
    return titulos


def _meaningful_length(content: str) -> int:
    """Comprimento sem distintivos: um README que é só uma fileira de badges não
    documenta nada."""
    return len(_BADGE_RE.sub("", content).strip())


def analyze_readme(content: str) -> ReadmeReport:
    """Identifica quais temas o README cobre.

    A busca por palavra-chave acontece nos **títulos** e, como rede de
    segurança, no corpo — um README sem cabeçalhos ainda pode explicar
    instalação.
    """
    relatorio = ReadmeReport(
        headings=extract_headings(content),
        content_length=_meaningful_length(content),
        has_code_examples=bool(_CODE_FENCE_RE.search(content)),
    )

    titulos = " | ".join(relatorio.headings).lower()
    corpo = content.lower()

    for tema, palavras in SECTION_KEYWORDS.items():
        if any(p in titulos for p in palavras):
            relatorio.covered.add(tema)
        elif any(p in corpo for p in palavras):
            # Encontrado só no corpo: conta, mas é sinal mais fraco.
            relatorio.covered.add(tema)

    return relatorio


# Arquivos de documentação reconhecidos, por papel. As variações cobrem as
# formas comuns em repositórios reais.
DOC_FILES: dict[str, tuple[str, ...]] = {
    "readme": ("README.md", "README.rst", "README.txt", "README"),
    "license": ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING"),
    "contributing": ("CONTRIBUTING.md", "CONTRIBUTING.rst", "CONTRIBUTING"),
    "changelog": ("CHANGELOG.md", "CHANGELOG.rst", "CHANGELOG", "HISTORY.md"),
    "security": ("SECURITY.md", "SECURITY"),
    "code_of_conduct": ("CODE_OF_CONDUCT.md", "CODE_OF_CONDUCT"),
}


def classify_doc_file(filename: str) -> str | None:
    """Papel documental do arquivo, ou `None` se não for documentação conhecida."""
    for papel, nomes in DOC_FILES.items():
        if any(filename.lower() == nome.lower() for nome in nomes):
            return papel
    return None
