"""Orquestra uma análise completa: adquirir, inventariar, analisar, pontuar.

É o ponto de entrada do CodeInsight Engine. Não conhece banco de dados, não
conhece HTTP e **não usa provedor de IA** — recebe um repositório, devolve
achados e score. Quem persiste é a camada de serviço.

Um analyzer que falha não derruba a análise: a exceção vira nota na dimensão
correspondente e as demais seguem. O oposto — perder sete dimensões porque uma
quebrou — seria pior para quem pediu a análise.
"""

import asyncio
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.engine.acquisition import acquire_repository
from app.engine.analyzers import (
    Analyzer,
    AnalyzerResult,
    ArchitectureAnalyzer,
    ConfigurationAnalyzer,
    DependencyAnalyzer,
    DocumentationAnalyzer,
    GitAnalyzer,
    QualityAnalyzer,
    SecurityAnalyzer,
    TestingAnalyzer,
)
from app.engine.models import RepositoryScan
from app.engine.rules.git_activity import GitActivity
from app.engine.scanner import scan_repository
from app.engine.scoring import RepositoryScore, score_repository

logger = logging.getLogger(__name__)


class AnalysisTimeoutError(Exception):
    """A análise passou do tempo máximo. Mensagem segura para exibir."""


class EngineReport(BaseModel):
    """Resultado completo de uma análise do motor."""

    scan: RepositoryScan
    results: list[AnalyzerResult] = Field(default_factory=list)
    score: RepositoryScore

    @property
    def findings_count(self) -> int:
        return sum(len(r.findings) for r in self.results)


def build_analyzers(activity: GitActivity | None = None) -> list[Analyzer]:
    """Os analyzers de uma execução.

    `activity` é opcional: sem dados da API do GitHub o analyzer de Git avalia
    só o que está versionado e registra a lacuna como nota.
    """
    return [
        SecurityAnalyzer(),
        QualityAnalyzer(),
        DependencyAnalyzer(),
        ArchitectureAnalyzer(),
        TestingAnalyzer(),
        ConfigurationAnalyzer(),
        DocumentationAnalyzer(),
        GitAnalyzer(activity=activity),
    ]


def analyze_directory(root: Path, activity: GitActivity | None = None) -> EngineReport:
    """Analisa um diretório já em disco. Síncrono e sem rede.

    Separado de `analyze_repository` para que a análise seja testável sem tocar
    a rede, e para que o trabalho pesado possa ir para uma thread.
    """
    scan = scan_repository(root)
    resultados: list[AnalyzerResult] = []

    for analyzer in build_analyzers(activity):
        try:
            resultados.append(analyzer.analyze(root, scan))
        except Exception as exc:  # noqa: BLE001
            # O repositório é dado de terceiros: um arquivo inesperado pode
            # quebrar um analyzer. Perder as outras sete dimensões por causa
            # disso seria pior do que reportar a falha desta.
            logger.exception("Analyzer %s falhou", analyzer.name)
            resultados.append(
                AnalyzerResult(
                    analyzer=analyzer.name,
                    category=analyzer.category,
                    notes=[f"Dimensão não avaliada: o analyzer falhou ({type(exc).__name__})."],
                )
            )

    return EngineReport(scan=scan, results=resultados, score=score_repository(resultados))


async def analyze_repository(
    access_token: str | None,
    full_name: str,
    ref: str,
    *,
    activity: GitActivity | None = None,
) -> EngineReport:
    """Baixa, extrai e analisa um repositório do GitHub.

    O diretório temporário é removido ao final, inclusive em erro, timeout e
    cancelamento — a limpeza é do `acquire_repository`.
    """
    settings = get_settings()

    async with acquire_repository(access_token, full_name, ref) as root:
        try:
            # A análise é CPU-bound e roda em thread para não travar o event
            # loop: o backend continua servindo requisições enquanto isso.
            return await asyncio.wait_for(
                asyncio.to_thread(analyze_directory, root, activity),
                timeout=settings.engine_max_analysis_seconds,
            )
        except TimeoutError as exc:
            raise AnalysisTimeoutError(
                f"A análise passou de {settings.engine_max_analysis_seconds} segundos e foi "
                "interrompida. Repositórios muito grandes podem exceder o limite."
            ) from exc
