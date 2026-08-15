"""Analyzer de documentação.

Avalia a presença dos arquivos de documentação e a cobertura de temas no README.
Tudo é leitura de texto — nenhum markdown é renderizado, nenhum link é seguido,
nenhuma requisição é feita.
"""

import logging
from pathlib import Path

from app.engine.acquisition import read_text
from app.engine.analyzers.base import AnalyzerResult
from app.engine.findings import Finding, FindingCategory
from app.engine.models import RepositoryScan
from app.engine.rules.documentation import ReadmeReport, analyze_readme, classify_doc_file
from app.engine.rules.documentation_rules import register_documentation_rules
from app.engine.rules.registry import RuleRegistry

logger = logging.getLogger(__name__)

# Abaixo disto o README não chega a explicar o projeto. O valor é convencional —
# daí a confiança menor na regra correspondente.
MIN_README_CHARS = 300

# Tema do README -> regra que cobra sua ausência.
_SECTION_RULES: dict[str, str] = {
    "installation": "DOC-003",
    "usage": "DOC-004",
    "configuration": "DOC-005",
}

# Papel documental -> regra que cobra sua ausência.
_MISSING_FILE_RULES: dict[str, str] = {
    "license": "DOC-007",
    "contributing": "DOC-008",
}


class DocumentationAnalyzer:
    """Avalia README, LICENSE, CONTRIBUTING e a pasta docs/."""

    name = "documentation"
    category = FindingCategory.DOCUMENTATION

    def __init__(self, registry: RuleRegistry | None = None) -> None:
        if registry is None:
            registry = RuleRegistry()
            register_documentation_rules(registry)
        self.registry = registry

    def analyze(self, root: Path, scan: RepositoryScan) -> AnalyzerResult:
        resultado = AnalyzerResult(analyzer=self.name, category=self.category)

        papeis: dict[str, str] = {}
        for arquivo in scan.files:
            papel = classify_doc_file(Path(arquivo.path).name)
            # Só documentação na raiz conta: um README dentro de `exemplos/` não
            # é o README do projeto.
            if papel and "/" not in arquivo.path and papel not in papeis:
                papeis[papel] = arquivo.path

        resultado.files_analyzed = len(papeis)

        readme_path = papeis.get("readme")
        if readme_path is None:
            resultado.findings.append(
                self.registry.get("DOC-001").build_finding(analyzer=self.name)
            )
        else:
            conteudo = read_text(root / readme_path)
            resultado.findings.extend(self._check_readme(readme_path, analyze_readme(conteudo)))

        for papel, rule_id in _MISSING_FILE_RULES.items():
            if papel not in papeis:
                resultado.findings.append(
                    self.registry.get(rule_id).build_finding(analyzer=self.name)
                )

        return resultado

    def _check_readme(self, relative_path: str, relatorio: ReadmeReport) -> list[Finding]:
        achados: list[Finding] = []

        # Comprimento sozinho é sinal fraco: um README curto que explica
        # instalação e uso está completo, só é conciso. O que caracteriza README
        # vazio é ser curto **e** não cobrir os temas essenciais.
        temas_essenciais = relatorio.covered & set(_SECTION_RULES)
        if relatorio.content_length < MIN_README_CHARS and len(temas_essenciais) < 2:
            achados.append(
                self.registry.get("DOC-002").build_finding(
                    analyzer=self.name,
                    file_path=relative_path,
                    evidence=f"{relatorio.content_length} caracteres de conteúdo",
                )
            )
            # README quase vazio: cobrar cada seção em separado seria ruído
            # repetindo o mesmo problema.
            return achados

        for tema, rule_id in _SECTION_RULES.items():
            if tema not in relatorio.covered:
                achados.append(
                    self.registry.get(rule_id).build_finding(
                        analyzer=self.name,
                        file_path=relative_path,
                        evidence=(
                            f"Seções encontradas: {', '.join(relatorio.headings[:8]) or 'nenhuma'}"
                        ),
                    )
                )

        if not relatorio.has_code_examples:
            achados.append(
                self.registry.get("DOC-006").build_finding(
                    analyzer=self.name, file_path=relative_path
                )
            )

        return achados
