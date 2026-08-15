"""Analyzer de dependências.

Lê os manifestos do repositório e reporta o que compromete reprodutibilidade ou
cadeia de suprimentos. Não instala nada, não resolve versões e não consulta
base de vulnerabilidades pela rede — ferramentas como `pip-audit` e `npm audit`
podem complementar isto no futuro, mas o motor não pode depender delas.
"""

import logging
from pathlib import Path

from app.engine.acquisition import read_text
from app.engine.analyzers.base import AnalyzerResult
from app.engine.findings import Finding, FindingCategory
from app.engine.models import RepositoryScan
from app.engine.rules.dependencies import LOCK_FILES, Dependency, parse_manifest
from app.engine.rules.dependency_rules import register_dependency_rules
from app.engine.rules.registry import RuleRegistry

logger = logging.getLogger(__name__)


class DependencyAnalyzer:
    """Avalia manifestos de dependência de Python, JS, Go, Rust e Java."""

    name = "dependency"
    category = FindingCategory.DEPENDENCIES

    def __init__(self, registry: RuleRegistry | None = None) -> None:
        if registry is None:
            registry = RuleRegistry()
            register_dependency_rules(registry)
        self.registry = registry

    def analyze(self, root: Path, scan: RepositoryScan) -> AnalyzerResult:
        resultado = AnalyzerResult(analyzer=self.name, category=self.category)
        nomes_presentes = {Path(f.path).name for f in scan.files}

        for arquivo in scan.files:
            nome = Path(arquivo.path).name
            conteudo = read_text(root / arquivo.path)
            if not conteudo:
                continue

            relatorio = parse_manifest(nome, conteudo)
            if relatorio is None:
                continue

            resultado.files_analyzed += 1
            if relatorio.parse_error:
                resultado.notes.append(f"{arquivo.path}: {relatorio.parse_error}")
                continue

            for dependencia in relatorio.dependencies:
                resultado.findings.extend(self._check_dependency(arquivo.path, dependencia))

            resultado.findings.extend(
                self._check_lock_file(arquivo.path, nome, nomes_presentes, relatorio.dependencies)
            )

        return resultado

    # --- por dependência ---

    def _check_dependency(self, relative_path: str, dep: Dependency) -> list[Finding]:
        achados: list[Finding] = []

        if dep.has_insecure_source:
            regra = self.registry.get("DEP-004")
            achados.append(
                regra.build_finding(
                    analyzer=self.name,
                    file_path=relative_path,
                    line_start=dep.line or None,
                    evidence=f"{dep.name} {dep.spec}".strip(),
                    title=f"{regra.name}: {dep.name}",
                )
            )
        elif dep.has_git_source:
            regra = self.registry.get("DEP-003")
            achados.append(
                regra.build_finding(
                    analyzer=self.name,
                    file_path=relative_path,
                    line_start=dep.line or None,
                    evidence=f"{dep.name} {dep.spec}".strip(),
                    title=f"{regra.name}: {dep.name}",
                )
            )
        elif not dep.spec.strip():
            regra = self.registry.get("DEP-001")
            achados.append(
                regra.build_finding(
                    analyzer=self.name,
                    file_path=relative_path,
                    line_start=dep.line or None,
                    evidence=dep.name,
                    title=f"{regra.name}: {dep.name}",
                )
            )
        elif not dep.is_pinned:
            regra = self.registry.get("DEP-002")
            achados.append(
                regra.build_finding(
                    analyzer=self.name,
                    file_path=relative_path,
                    line_start=dep.line or None,
                    evidence=f"{dep.name} {dep.spec}".strip(),
                    title=f"{regra.name}: {dep.name}",
                )
            )

        return achados

    # --- por manifesto ---

    def _check_lock_file(
        self,
        relative_path: str,
        manifest_name: str,
        present: set[str],
        dependencies: list[Dependency],
    ) -> list[Finding]:
        """Lock só faz falta quando há dependência para travar."""
        esperados = LOCK_FILES.get(manifest_name)
        if not esperados or not dependencies:
            return []
        if any(nome in present for nome in esperados):
            return []

        regra = self.registry.get("DEP-005")
        return [
            regra.build_finding(
                analyzer=self.name,
                file_path=relative_path,
                evidence=f"{manifest_name} sem {' ou '.join(esperados)}",
            )
        ]
