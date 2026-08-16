"""Analyzer de arquitetura.

Avalia organização estrutural a partir do inventário do scanner. Toda conclusão
é heurística — não existe estrutura universalmente correta — então as regras
carregam confiança baixa e a redação evita veredito.
"""

import logging
from collections import Counter
from pathlib import Path

from app.engine.acquisition import read_text
from app.engine.analyzers.base import AnalyzerResult
from app.engine.findings import Finding, FindingCategory
from app.engine.models import RepositoryScan
from app.engine.rules.architecture import (
    HUGE_FILE_LINES,
    LARGE_FILE_LINES,
    LAYER_DIRECTORY_NAMES,
    MAX_REASONABLE_DEPTH,
    MAX_ROOT_FILES,
    ArchitectureReport,
    count_lines,
    path_depth,
)
from app.engine.rules.architecture_rules import register_architecture_rules
from app.engine.rules.registry import RuleRegistry

logger = logging.getLogger(__name__)

# Acima disto um diretório vira depósito em vez de unidade coesa.
MAX_FILES_PER_DIRECTORY = 40

# Abaixo disto o projeto é pequeno demais para cobrar separação de camadas.
MIN_FILES_FOR_LAYERING = 15


class ArchitectureAnalyzer:
    """Avalia estrutura de diretórios, tamanho de arquivos e separação aparente."""

    name = "architecture"
    category = FindingCategory.ARCHITECTURE

    def __init__(self, registry: RuleRegistry | None = None) -> None:
        if registry is None:
            registry = RuleRegistry()
            register_architecture_rules(registry)
        self.registry = registry

    def analyze(self, root: Path, scan: RepositoryScan) -> AnalyzerResult:
        resultado = AnalyzerResult(analyzer=self.name, category=self.category)
        relatorio = self._collect(root, scan)
        resultado.files_analyzed = relatorio.total_files
        resultado.findings.extend(self._evaluate(relatorio))
        return resultado

    def _collect(self, root: Path, scan: RepositoryScan) -> ArchitectureReport:
        relatorio = ArchitectureReport(total_files=len(scan.files), files_per_directory=Counter())

        for arquivo in scan.files:
            profundidade = path_depth(arquivo.path)
            relatorio.max_depth = max(relatorio.max_depth, profundidade)
            if profundidade > MAX_REASONABLE_DEPTH:
                relatorio.deep_paths.append(arquivo.path)

            partes = Path(arquivo.path).parts
            if len(partes) == 1:
                relatorio.root_files.append(arquivo.path)
            else:
                diretorio = str(Path(arquivo.path).parent).replace("\\", "/")
                relatorio.directories.add(diretorio)
                relatorio.files_per_directory[diretorio] += 1
                relatorio.layer_directories.update(
                    p for p in partes[:-1] if p.lower() in LAYER_DIRECTORY_NAMES
                )

            # Contagem de linhas só faz sentido em texto.
            if arquivo.is_binary or arquivo.language is None:
                continue
            linhas = count_lines(read_text(root / arquivo.path))
            if linhas > HUGE_FILE_LINES:
                relatorio.huge_files.append((arquivo.path, linhas))
            elif linhas > LARGE_FILE_LINES:
                relatorio.large_files.append((arquivo.path, linhas))

        return relatorio

    def _evaluate(self, relatorio: ArchitectureReport) -> list[Finding]:
        achados: list[Finding] = []

        for caminho, linhas in relatorio.huge_files:
            achados.append(
                self.registry.get("ARC-002").build_finding(
                    analyzer=self.name, file_path=caminho, evidence=f"{linhas} linhas"
                )
            )
        for caminho, linhas in relatorio.large_files:
            achados.append(
                self.registry.get("ARC-001").build_finding(
                    analyzer=self.name, file_path=caminho, evidence=f"{linhas} linhas"
                )
            )

        if relatorio.deep_paths:
            achados.append(
                self.registry.get("ARC-003").build_finding(
                    analyzer=self.name,
                    file_path=relatorio.deep_paths[0],
                    evidence=f"profundidade máxima {relatorio.max_depth}",
                )
            )

        if len(relatorio.root_files) > MAX_ROOT_FILES:
            achados.append(
                self.registry.get("ARC-004").build_finding(
                    analyzer=self.name,
                    evidence=f"{len(relatorio.root_files)} arquivos na raiz",
                )
            )

        # Projeto pequeno não precisa de camadas — cobrar seria ruído.
        if relatorio.total_files >= MIN_FILES_FOR_LAYERING and not relatorio.has_layered_structure:
            achados.append(
                self.registry.get("ARC-005").build_finding(
                    analyzer=self.name,
                    evidence=f"{len(relatorio.directories)} diretórios, nenhum de camada",
                )
            )

        for diretorio, quantidade in relatorio.files_per_directory.most_common():
            if quantidade <= MAX_FILES_PER_DIRECTORY:
                break
            achados.append(
                self.registry.get("ARC-006").build_finding(
                    analyzer=self.name,
                    file_path=diretorio,
                    evidence=f"{quantidade} arquivos",
                )
            )

        return achados
