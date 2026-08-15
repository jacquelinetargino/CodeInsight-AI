"""Analyzer de testes.

Inventaria a infraestrutura de teste **sem executá-la**. Rodar a suíte de um
repositório de terceiros seria executar código arbitrário; toda conclusão aqui
vem de nomes de arquivo, imports e configuração.
"""

import logging
from pathlib import Path

from app.engine.acquisition import read_text
from app.engine.analyzers.base import AnalyzerResult
from app.engine.findings import Finding, FindingCategory
from app.engine.models import RepositoryScan
from app.engine.rules.registry import RuleRegistry
from app.engine.rules.testing import (
    COVERAGE_CONFIG_FILES,
    TEST_CONFIG_FILES,
    TestingReport,
    detect_frameworks,
    is_source_file,
    is_test_file,
)
from app.engine.rules.testing_rules import register_testing_rules

logger = logging.getLogger(__name__)

# Abaixo disto a cobertura é desigual o bastante para valer um aviso. É
# convencional — daí a confiança baixa da regra correspondente.
MIN_TEST_RATIO = 0.1

_TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec"}


class TestingAnalyzer:
    """Avalia presença, organização e volume de testes."""

    # O nome começa com "Test", então o pytest tentaria coletá-la como classe de
    # teste. Este marcador diz que não é.
    __test__ = False

    name = "testing"
    category = FindingCategory.TESTING

    def __init__(self, registry: RuleRegistry | None = None) -> None:
        if registry is None:
            registry = RuleRegistry()
            register_testing_rules(registry)
        self.registry = registry

    def analyze(self, root: Path, scan: RepositoryScan) -> AnalyzerResult:
        resultado = AnalyzerResult(analyzer=self.name, category=self.category)
        relatorio = self._collect(root, scan)
        resultado.files_analyzed = len(relatorio.test_files)
        resultado.findings.extend(self._evaluate(relatorio))
        return resultado

    def _collect(self, root: Path, scan: RepositoryScan) -> TestingReport:
        relatorio = TestingReport()

        for arquivo in scan.files:
            nome = Path(arquivo.path).name

            if nome in TEST_CONFIG_FILES:
                relatorio.has_test_config = True
            if nome in COVERAGE_CONFIG_FILES:
                relatorio.has_coverage_config = True

            if arquivo.is_binary:
                continue

            if is_test_file(arquivo.path):
                relatorio.test_files.append(arquivo.path)
                partes = Path(arquivo.path).parts[:-1]
                relatorio.test_directories.update(p for p in partes if p in _TEST_DIR_NAMES)
                # O framework vem do conteúdo: `import pytest` é evidência mais
                # forte que o nome do arquivo.
                relatorio.frameworks.update(detect_frameworks(read_text(root / arquivo.path)))
            elif is_source_file(arquivo.path):
                relatorio.source_files.append(arquivo.path)

        return relatorio

    def _evaluate(self, relatorio: TestingReport) -> list[Finding]:
        achados: list[Finding] = []

        if not relatorio.test_files:
            # Sem nenhum teste, cobrar organização e cobertura seria repetir o
            # mesmo problema em três achados.
            return [self.registry.get("TST-001").build_finding(analyzer=self.name)]

        evidencia = (
            f"{len(relatorio.test_files)} arquivos de teste, "
            f"{len(relatorio.source_files)} de código"
        )

        if relatorio.test_ratio < MIN_TEST_RATIO:
            achados.append(
                self.registry.get("TST-002").build_finding(analyzer=self.name, evidence=evidencia)
            )

        if not relatorio.frameworks:
            achados.append(
                self.registry.get("TST-003").build_finding(analyzer=self.name, evidence=evidencia)
            )

        if not relatorio.test_directories:
            achados.append(
                self.registry.get("TST-004").build_finding(analyzer=self.name, evidence=evidencia)
            )

        if not relatorio.has_coverage_config:
            achados.append(self.registry.get("TST-005").build_finding(analyzer=self.name))

        return achados
