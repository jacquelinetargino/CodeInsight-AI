"""Analyzer de Git.

Combina duas fontes: o que está versionado (do repositório extraído) e como o
repositório é operado (da API do GitHub). A segunda é **opcional** — análise sem
acesso à API ainda avalia os arquivos, e o que não pôde ser avaliado vira nota
em vez de silêncio.

Nenhum comando `git` é executado e nenhum conteúdo de arquivo sensível é lido:
a classificação é por nome e extensão, e o achado reporta só o caminho.
"""

import logging
from pathlib import Path

from app.engine.analyzers.base import AnalyzerResult
from app.engine.findings import Finding, FindingCategory
from app.engine.models import RepositoryScan
from app.engine.rules.git_activity import (
    LARGE_BINARY_BYTES,
    GitActivity,
    classify_sensitive_file,
)
from app.engine.rules.git_rules import register_git_rules
from app.engine.rules.registry import RuleRegistry

logger = logging.getLogger(__name__)

# Proporção de mensagens ruins a partir da qual o histórico deixa de ser útil.
LOW_QUALITY_MESSAGE_RATIO = 0.4

# Abaixo disto não há amostra suficiente para julgar o histórico.
MIN_COMMITS_FOR_JUDGEMENT = 5


class GitAnalyzer:
    """Avalia riscos de versionamento e de operação do repositório."""

    name = "git"
    category = FindingCategory.GIT

    def __init__(
        self, registry: RuleRegistry | None = None, activity: GitActivity | None = None
    ) -> None:
        if registry is None:
            registry = RuleRegistry()
            register_git_rules(registry)
        self.registry = registry
        # Dados da API entram por construtor para que `analyze` mantenha a
        # assinatura comum a todos os analyzers.
        self.activity = activity

    def analyze(self, root: Path, scan: RepositoryScan) -> AnalyzerResult:
        resultado = AnalyzerResult(analyzer=self.name, category=self.category)

        resultado.findings.extend(self._check_files(scan))
        resultado.files_analyzed = len(scan.files)

        if self.activity is None:
            # Sem dados da API, metade da análise não aconteceu. Registrar isso
            # impede que o score trate "não avaliado" como "sem problema".
            resultado.notes.append(
                "Atividade do repositório não avaliada: dados da API do GitHub indisponíveis."
            )
            return resultado

        resultado.findings.extend(self._check_activity(self.activity))
        return resultado

    def _check_files(self, scan: RepositoryScan) -> list[Finding]:
        """Avalia o que está versionado.

        Arquivos acima do teto de análise não entram em `scan.files` — o scanner
        os inventaria à parte. Precisam ser percorridos aqui também: uma chave
        privada grande demais para ler continua sendo uma chave privada
        versionada, e escaparia se olhássemos só a lista principal.
        """
        achados: list[Finding] = []

        todos = [f.path for f in scan.files] + [f.path for f in scan.oversized_files]
        for caminho in todos:
            categoria = classify_sensitive_file(caminho)
            if categoria:
                achados.append(
                    self.registry.get("GIT-001").build_finding(
                        analyzer=self.name,
                        file_path=caminho,
                        # Só o caminho e a categoria: o conteúdo nunca é lido.
                        evidence=f"{caminho} ({categoria})",
                        title=f"Arquivo sensível versionado: {categoria}",
                    )
                )

        # Passar do teto de análise (2 MB) não é, por si, um problema: o que
        # incha o repositório de forma permanente é a ordem de grandeza acima.
        for grande in scan.oversized_files:
            if grande.size_bytes < LARGE_BINARY_BYTES:
                continue
            if classify_sensitive_file(grande.path):
                continue  # já reportado como sensível, que é o problema maior
            achados.append(
                self.registry.get("GIT-002").build_finding(
                    analyzer=self.name,
                    file_path=grande.path,
                    evidence=f"{grande.size_bytes / 1024 / 1024:.1f} MB",
                )
            )

        return achados

    def _check_activity(self, activity: GitActivity) -> list[Finding]:
        achados: list[Finding] = []

        if activity.branches and not activity.default_branch_is_protected:
            achados.append(
                self.registry.get("GIT-003").build_finding(
                    analyzer=self.name,
                    evidence=f"branch principal: {activity.default_branch}",
                )
            )

        # Um único contribuidor num projeto com histórico é sinal de risco de
        # continuidade; num repositório recém-criado, não diz nada.
        if (
            len(activity.contributors) == 1
            and len(activity.recent_commits) >= MIN_COMMITS_FOR_JUDGEMENT
        ):
            achados.append(
                self.registry.get("GIT-004").build_finding(
                    analyzer=self.name,
                    evidence=f"{len(activity.recent_commits)} commits, 1 autor",
                )
            )

        total = len(activity.recent_commits)
        if total >= MIN_COMMITS_FOR_JUDGEMENT:
            ruins = len(activity.low_quality_messages)
            if ruins / total >= LOW_QUALITY_MESSAGE_RATIO:
                achados.append(
                    self.registry.get("GIT-005").build_finding(
                        analyzer=self.name,
                        evidence=f"{ruins} de {total} commits recentes",
                    )
                )

            if activity.merged_pull_requests == 0:
                achados.append(
                    self.registry.get("GIT-006").build_finding(
                        analyzer=self.name,
                        evidence=f"{total} commits, nenhum pull request mergeado",
                    )
                )

        return achados
