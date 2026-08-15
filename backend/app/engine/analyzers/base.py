"""Contrato comum dos analyzers.

Cada analyzer é independente: recebe o inventário do scanner e a raiz em disco,
devolve achados da sua categoria. Nenhum depende do outro, e nenhum precisa de
provedor de IA.
"""

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from app.engine.findings import Finding, FindingCategory
from app.engine.models import RepositoryScan


class AnalyzerResult(BaseModel):
    """Saída de um analyzer.

    `notes` registra o que atrapalhou a análise — arquivo ilegível, sintaxe
    inválida. Sem isso, um repositório que o motor mal conseguiu ler pareceria
    um repositório limpo.
    """

    analyzer: str
    category: FindingCategory
    findings: list[Finding] = Field(default_factory=list)
    files_analyzed: int = 0
    notes: list[str] = Field(default_factory=list)


class Analyzer(Protocol):
    """Interface que todo analyzer implementa."""

    name: str
    category: FindingCategory

    def analyze(self, root: Path, scan: RepositoryScan) -> AnalyzerResult: ...
