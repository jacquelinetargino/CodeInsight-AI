"""Analyzer de configuração e infraestrutura.

Lê Dockerfile, docker-compose, workflows de CI e .gitignore como texto. Nenhuma
imagem é construída, nenhum container sobe, nenhum workflow é executado.
"""

import logging
from pathlib import Path

from app.engine.acquisition import read_text
from app.engine.analyzers.base import AnalyzerResult
from app.engine.findings import Finding, FindingCategory
from app.engine.models import RepositoryScan
from app.engine.rules.configuration import (
    analyze_compose,
    analyze_dockerfile,
    analyze_workflow,
    missing_gitignore_entries,
)
from app.engine.rules.configuration_rules import register_configuration_rules
from app.engine.rules.registry import RuleRegistry

logger = logging.getLogger(__name__)

_COMPOSE_NAMES = {
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}


class ConfigurationAnalyzer:
    """Avalia Dockerfile, compose, CI e .gitignore."""

    name = "configuration"
    category = FindingCategory.CONFIGURATION

    def __init__(self, registry: RuleRegistry | None = None) -> None:
        if registry is None:
            registry = RuleRegistry()
            register_configuration_rules(registry)
        self.registry = registry

    def analyze(self, root: Path, scan: RepositoryScan) -> AnalyzerResult:
        resultado = AnalyzerResult(analyzer=self.name, category=self.category)
        tem_gitignore = False

        for arquivo in scan.files:
            nome = Path(arquivo.path).name
            caminho_posix = arquivo.path.replace("\\", "/")

            if arquivo.is_binary:
                continue

            if nome == ".gitignore" and "/" not in caminho_posix:
                tem_gitignore = True
                resultado.files_analyzed += 1
                resultado.findings.extend(self._check_gitignore(arquivo.path, root))
            elif nome == "Dockerfile" or nome.startswith("Dockerfile."):
                resultado.files_analyzed += 1
                resultado.findings.extend(self._check_dockerfile(arquivo.path, root))
            elif nome in _COMPOSE_NAMES:
                resultado.files_analyzed += 1
                resultado.findings.extend(self._check_compose(arquivo.path, root))
            elif caminho_posix.startswith(".github/workflows/") and nome.endswith(
                (".yml", ".yaml")
            ):
                resultado.files_analyzed += 1
                resultado.findings.extend(self._check_workflow(arquivo.path, root))

        if not tem_gitignore:
            resultado.findings.append(
                self.registry.get("CFG-009").build_finding(analyzer=self.name)
            )

        return resultado

    def _check_dockerfile(self, relative_path: str, root: Path) -> list[Finding]:
        relatorio = analyze_dockerfile(read_text(root / relative_path))
        achados: list[Finding] = []

        if relatorio.runs_as_root:
            usuario = relatorio.final_user or "não declarado (root)"
            achados.append(
                self.registry.get("CFG-001").build_finding(
                    analyzer=self.name,
                    file_path=relative_path,
                    evidence=f"USER final: {usuario}",
                )
            )
        if relatorio.uses_floating_tag:
            achados.append(
                self.registry.get("CFG-002").build_finding(
                    analyzer=self.name,
                    file_path=relative_path,
                    evidence=", ".join(relatorio.base_images[:3]),
                )
            )
        for linha, nome in relatorio.embedded_secrets:
            achados.append(
                self.registry.get("CFG-003").build_finding(
                    analyzer=self.name,
                    file_path=relative_path,
                    line_start=linha,
                    # O nome da variável basta como evidência; o valor não é
                    # incluído justamente por ser a credencial.
                    evidence=f"{nome} com valor literal",
                )
            )
        for linha in relatorio.remote_add:
            achados.append(
                self.registry.get("CFG-004").build_finding(
                    analyzer=self.name, file_path=relative_path, line_start=linha
                )
            )
        if not relatorio.has_healthcheck:
            achados.append(
                self.registry.get("CFG-011").build_finding(
                    analyzer=self.name, file_path=relative_path
                )
            )

        return achados

    def _check_compose(self, relative_path: str, root: Path) -> list[Finding]:
        relatorio = analyze_compose(read_text(root / relative_path))
        achados: list[Finding] = []

        for linha in relatorio.privileged_lines:
            achados.append(
                self.registry.get("CFG-005").build_finding(
                    analyzer=self.name, file_path=relative_path, line_start=linha
                )
            )
        for linha in relatorio.host_network_lines:
            achados.append(
                self.registry.get("CFG-006").build_finding(
                    analyzer=self.name, file_path=relative_path, line_start=linha
                )
            )

        return achados

    def _check_workflow(self, relative_path: str, root: Path) -> list[Finding]:
        relatorio = analyze_workflow(read_text(root / relative_path))
        achados: list[Finding] = []

        for linha, ref in relatorio.unpinned_actions:
            achados.append(
                self.registry.get("CFG-007").build_finding(
                    analyzer=self.name, file_path=relative_path, line_start=linha, evidence=ref
                )
            )
        for linha in relatorio.curl_pipe_shell:
            achados.append(
                self.registry.get("CFG-008").build_finding(
                    analyzer=self.name, file_path=relative_path, line_start=linha
                )
            )

        return achados

    def _check_gitignore(self, relative_path: str, root: Path) -> list[Finding]:
        faltando = missing_gitignore_entries(read_text(root / relative_path))
        if not faltando:
            return []
        return [
            self.registry.get("CFG-010").build_finding(
                analyzer=self.name,
                file_path=relative_path,
                evidence=f"Categorias sem cobertura: {', '.join(faltando)}",
            )
        ]
