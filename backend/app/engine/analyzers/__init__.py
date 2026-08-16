"""Analyzers do CodeInsight Engine.

Cada um cobre uma dimensão, é independente dos demais e não depende de provedor
de IA. Todos recebem o inventário do scanner e devolvem `AnalyzerResult`.
"""

from app.engine.analyzers.architecture import ArchitectureAnalyzer
from app.engine.analyzers.base import Analyzer, AnalyzerResult
from app.engine.analyzers.configuration import ConfigurationAnalyzer
from app.engine.analyzers.dependency import DependencyAnalyzer
from app.engine.analyzers.documentation import DocumentationAnalyzer
from app.engine.analyzers.security import SecurityAnalyzer
from app.engine.analyzers.testing import TestingAnalyzer

__all__ = [
    "Analyzer",
    "AnalyzerResult",
    "ArchitectureAnalyzer",
    "ConfigurationAnalyzer",
    "DependencyAnalyzer",
    "DocumentationAnalyzer",
    "SecurityAnalyzer",
    "TestingAnalyzer",
]
