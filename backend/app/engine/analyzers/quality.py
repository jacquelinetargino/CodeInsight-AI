"""Analyzer de qualidade de código.

Consome as mesmas detecções que o analyzer de segurança — a AST de Python e os
padrões de JS/TS — mas traduz a outra metade do vocabulário: as ocorrências que
falam de manutenibilidade, não de risco.

A separação é intencional. Quem lê um relatório de segurança quer saber o que
pode ser explorado; misturar "esta função tem 80 linhas" no meio disso faria as
duas informações perderem valor.
"""

import logging
from pathlib import Path

from app.engine.acquisition import read_text
from app.engine.analyzers.base import AnalyzerResult
from app.engine.findings import DetectionMethod, Finding, FindingCategory
from app.engine.models import RepositoryScan
from app.engine.rules.javascript import analyze_javascript
from app.engine.rules.python_ast import analyze_python
from app.engine.rules.quality_rules import register_quality_rules
from app.engine.rules.registry import RuleRegistry
from app.engine.rules.testing import is_test_file

logger = logging.getLogger(__name__)

ANALYZER_NAME = "quality"

# Ocorrência da AST de Python -> regra. As demais ocorrências do mesmo relatório
# são de segurança e pertencem ao SecurityAnalyzer.
_AST_RULE_BY_KIND: dict[str, str] = {
    "function-too-long": "QUA-001",
    "function-too-complex": "QUA-002",
    "class-too-large": "QUA-003",
    "too-many-arguments": "QUA-004",
    "mutable-default-argument": "QUA-005",
    "bare-except": "QUA-006",
    "broad-except": "QUA-007",
    "silenced-exception": "QUA-008",
    "assert-for-validation": "QUA-009",
    "request-without-timeout": "QUA-010",
}

_JS_RULE_BY_KIND: dict[str, str] = {
    "js-var-declaration": "QUA-011",
    "js-console-log": "QUA-012",
    "js-debugger": "QUA-013",
    "js-any-type": "QUA-014",
}

# Mesmo teto do analyzer de segurança: sem parser não dá para distinguir código
# de string ou de comentário, então nenhuma detecção textual merece certeza.
_JS_CONFIDENCE = 0.7

# Regras que descrevem a prática correta quando o arquivo é de teste.
#
# `assert` é como se escreve um teste em pytest, e uma chamada de rede num teste
# vai para um servidor local ou um dublê. Reportar as duas ali produziria
# centenas de achados corretos-porém-inúteis — medido em repositórios reais, é a
# diferença entre um relatório que se lê e um que se ignora.
_IRRELEVANTE_EM_TESTE = {"QUA-009", "QUA-010"}

_JS_LANGUAGES = {"JavaScript", "TypeScript", "Vue", "Svelte"}


class QualityAnalyzer:
    """Avalia manutenibilidade e tratamento de erro."""

    name = ANALYZER_NAME
    category = FindingCategory.QUALITY

    def __init__(self, registry: RuleRegistry | None = None) -> None:
        if registry is None:
            registry = RuleRegistry()
            register_quality_rules(registry)
        self.registry = registry

    def analyze(self, root: Path, scan: RepositoryScan) -> AnalyzerResult:
        resultado = AnalyzerResult(analyzer=self.name, category=self.category)

        for arquivo in scan.files:
            if arquivo.is_binary:
                continue
            if arquivo.language != "Python" and arquivo.language not in _JS_LANGUAGES:
                continue

            conteudo = read_text(root / arquivo.path)
            if not conteudo:
                continue

            resultado.files_analyzed += 1

            if arquivo.language == "Python":
                achados, nota = self._scan_python(arquivo.path, conteudo)
                resultado.findings.extend(achados)
                if nota:
                    resultado.notes.append(nota)
            else:
                resultado.findings.extend(self._scan_javascript(arquivo.path, conteudo))

        return resultado

    def _scan_python(self, relative_path: str, content: str) -> tuple[list[Finding], str | None]:
        relatorio = analyze_python(content)
        if relatorio.parse_error:
            # Arquivo ilegível não é arquivo limpo: sem a nota, o score trataria
            # a ausência de achados como ausência de problemas.
            return [], f"{relative_path}: {relatorio.parse_error}"

        achados = self._traduzir(
            relative_path, relatorio.issues, _AST_RULE_BY_KIND, None, DetectionMethod.AST
        )
        return achados, None

    def _scan_javascript(self, relative_path: str, content: str) -> list[Finding]:
        return self._traduzir(
            relative_path,
            analyze_javascript(content).issues,
            _JS_RULE_BY_KIND,
            _JS_CONFIDENCE,
            DetectionMethod.TEXT,
        )

    def _traduzir(
        self,
        relative_path: str,
        ocorrencias,
        mapa: dict[str, str],
        teto_confianca: float | None,
        metodo: DetectionMethod,
    ) -> list[Finding]:
        achados: list[Finding] = []
        arquivo_de_teste = is_test_file(relative_path)

        for ocorrencia in ocorrencias:
            rule_id = mapa.get(ocorrencia.kind)
            if rule_id is None:
                continue  # ocorrência de segurança, tratada por outro analyzer
            if arquivo_de_teste and rule_id in _IRRELEVANTE_EM_TESTE:
                continue
            regra = self.registry.get(rule_id)
            confianca = (
                regra.confidence
                if teto_confianca is None
                else min(regra.confidence, teto_confianca)
            )
            achados.append(
                regra.build_finding(
                    analyzer=self.name,
                    file_path=relative_path,
                    line_start=ocorrencia.line,
                    line_end=ocorrencia.line,
                    evidence=ocorrencia.evidence,
                    description=ocorrencia.detail or regra.description,
                    confidence=confianca,
                    detection_method=metodo,
                )
            )
        return achados
