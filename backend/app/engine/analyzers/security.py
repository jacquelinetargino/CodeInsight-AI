"""Analyzer de segurança: junta o detector de credenciais e a análise AST num
conjunto de achados classificados por regra.

Este módulo não detecta nada por conta própria — ele traduz. O detector diz
"encontrei um padrão de chave da AWS na linha 12"; aqui isso vira "SEC-001, alta
severidade, com esta recomendação". Manter tradução e detecção separadas permite
mudar a política de severidade sem tocar nos detectores.
"""

import logging
from pathlib import Path

from app.engine.acquisition import read_text
from app.engine.analyzers.base import AnalyzerResult
from app.engine.findings import Finding, FindingCategory
from app.engine.models import RepositoryScan
from app.engine.rules.javascript import analyze_javascript
from app.engine.rules.python_ast import analyze_python
from app.engine.rules.registry import RuleRegistry
from app.engine.rules.secrets import detect_secrets
from app.engine.rules.security_rules import register_security_rules

logger = logging.getLogger(__name__)

ANALYZER_NAME = "security"

# Padrão de credencial -> regra. Explícito porque enquadrar uma senha como
# "chave de API" tornaria a recomendação errada.
_SECRET_RULE_BY_PATTERN: dict[str, str] = {
    "private-key": "SEC-003",
    "jwt": "SEC-004",
    "database-url-with-password": "SEC-002",
    "generic-assignment": "SEC-002",
}
_DEFAULT_SECRET_RULE = "SEC-001"

# Ocorrência da AST -> regra.
_AST_RULE_BY_KIND: dict[str, str] = {
    "dangerous-eval": "SEC-006",
    "dangerous-exec": "SEC-007",
    "dangerous-compile": "SEC-007",
    "sql-injection-risk": "SEC-008",
    "subprocess-shell-true": "SEC-009",
    "os-command-execution": "SEC-009",
    "unsafe-deserialization": "SEC-011",
    "yaml-unsafe-load": "SEC-012",
    "weak-hash": "SEC-010",
}

# Ocorrência de JS/TS -> regra. A detecção é textual, sem parser, então estas
# valem menos que as equivalentes de Python: ver `_JS_CONFIDENCE`.
_JS_RULE_BY_KIND: dict[str, str] = {
    "js-eval": "SEC-006",
    "js-function-constructor": "SEC-007",
    "js-settimeout-string": "SEC-007",
    "js-inner-html": "SEC-013",
    "js-document-write": "SEC-013",
    "js-dangerously-set-html": "SEC-013",
    "js-insert-adjacent-html": "SEC-013",
    "js-child-process-exec": "SEC-009",
    "js-math-random-security": "SEC-014",
    "js-credential-in-storage": "SEC-015",
    "js-insecure-transport": "SEC-016",
}

# Teto de confiança para achados de JS/TS. Sem parser não dá para distinguir
# código de string ou de template, então nenhuma detecção textual merece a
# mesma certeza de uma da AST.
_JS_CONFIDENCE = 0.7

# Linguagens que o analyzer trata como JS/TS.
_JS_LANGUAGES = {"JavaScript", "TypeScript", "Vue", "Svelte"}

# Arquivos de ambiente que não deveriam estar versionados. `.env.example` e
# afins são o padrão recomendado e ficam de fora.
_ENV_FILENAMES = {".env", ".env.local", ".env.production", ".env.prod"}


class SecurityAnalyzer:
    """Procura credenciais expostas e padrões de código inseguros."""

    name = ANALYZER_NAME
    category = FindingCategory.SECURITY

    def __init__(self, registry: RuleRegistry | None = None) -> None:
        # Registro próprio por padrão: o analyzer é autossuficiente e os testes
        # não precisam preparar estado global.
        if registry is None:
            registry = RuleRegistry()
            register_security_rules(registry)
        self.registry = registry

    def analyze(self, root: Path, scan: RepositoryScan) -> AnalyzerResult:
        resultado = AnalyzerResult(analyzer=self.name, category=self.category)

        for arquivo in scan.files:
            if arquivo.is_binary:
                continue

            caminho = root / arquivo.path
            conteudo = read_text(caminho)
            if not conteudo:
                continue

            resultado.files_analyzed += 1
            resultado.findings.extend(self._scan_secrets(arquivo.path, conteudo))

            if arquivo.language == "Python":
                achados, nota = self._scan_python(arquivo.path, conteudo)
                resultado.findings.extend(achados)
                if nota:
                    resultado.notes.append(nota)
            elif arquivo.language in _JS_LANGUAGES:
                resultado.findings.extend(self._scan_javascript(arquivo.path, conteudo))

        resultado.findings.extend(self._check_env_files(scan))
        return resultado

    # --- credenciais ---

    def _scan_secrets(self, relative_path: str, content: str) -> list[Finding]:
        achados: list[Finding] = []
        for ocorrencia in detect_secrets(content):
            rule_id = _SECRET_RULE_BY_PATTERN.get(ocorrencia.pattern_name, _DEFAULT_SECRET_RULE)
            regra = self.registry.get(rule_id)
            achados.append(
                regra.build_finding(
                    analyzer=self.name,
                    file_path=relative_path,
                    line_start=ocorrencia.line,
                    line_end=ocorrencia.line,
                    # A evidência já vem mascarada do detector — o valor real
                    # nunca chega até aqui.
                    evidence=ocorrencia.masked_evidence,
                    title=f"{regra.name}: {ocorrencia.description}",
                    # A confiança do padrão manda: um prefixo proprietário vale
                    # mais que uma atribuição genérica.
                    confidence=min(regra.confidence, ocorrencia.confidence),
                )
            )
        return achados

    # --- código Python ---

    def _scan_python(self, relative_path: str, content: str) -> tuple[list[Finding], str | None]:
        relatorio = analyze_python(content)
        if relatorio.parse_error:
            # Não é achado de segurança: é limitação da análise, e precisa ficar
            # visível para o score não tratar "ilegível" como "limpo".
            return [], f"{relative_path}: {relatorio.parse_error}"

        achados: list[Finding] = []
        for ocorrencia in relatorio.issues:
            rule_id = _AST_RULE_BY_KIND.get(ocorrencia.kind)
            if rule_id is None:
                continue  # ocorrência de qualidade, tratada por outro analyzer
            regra = self.registry.get(rule_id)
            achados.append(
                regra.build_finding(
                    analyzer=self.name,
                    file_path=relative_path,
                    line_start=ocorrencia.line,
                    line_end=ocorrencia.line,
                    evidence=ocorrencia.evidence,
                    description=ocorrencia.detail or regra.description,
                )
            )
        return achados, None

    # --- código JavaScript/TypeScript ---

    def _scan_javascript(self, relative_path: str, content: str) -> list[Finding]:
        """Detecção textual, sem parser. A confiança é limitada porque não dá
        para distinguir código de string ou de template."""
        achados: list[Finding] = []
        for ocorrencia in analyze_javascript(content).issues:
            rule_id = _JS_RULE_BY_KIND.get(ocorrencia.kind)
            if rule_id is None:
                continue  # ocorrência de qualidade, tratada por outro analyzer
            regra = self.registry.get(rule_id)
            achados.append(
                regra.build_finding(
                    analyzer=self.name,
                    file_path=relative_path,
                    line_start=ocorrencia.line,
                    line_end=ocorrencia.line,
                    evidence=ocorrencia.evidence,
                    description=ocorrencia.detail or regra.description,
                    confidence=min(regra.confidence, _JS_CONFIDENCE),
                )
            )
        return achados

    # --- arquivos de ambiente ---

    def _check_env_files(self, scan: RepositoryScan) -> list[Finding]:
        regra = self.registry.get("SEC-005")
        achados: list[Finding] = []
        for arquivo in scan.files:
            nome = Path(arquivo.path).name
            if nome in _ENV_FILENAMES:
                achados.append(
                    regra.build_finding(
                        analyzer=self.name,
                        file_path=arquivo.path,
                        evidence=f"{arquivo.path} ({arquivo.size_bytes} bytes)",
                    )
                )
        return achados
