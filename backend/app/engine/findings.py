"""Achados produzidos pelos analyzers.

O `Finding` do motor é mais rico que o formato histórico gravado no JSONB de
`analysis_results.findings` (título, descrição, sugestão, severidade, arquivo e
linha). Em vez de quebrar as análises já persistidas, a serialização produz um
**superconjunto**: quem só conhece os campos antigos continua lendo, e quem
conhece os novos ganha regra, confiança, evidência e analyzer.

Nada aqui executa ou interpreta conteúdo de repositório — `Finding` é só dado.
"""

import hashlib
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.models.enums import Severity

# Evidência é um trecho para o humano entender o achado, não o arquivo inteiro.
# O corte também evita gravar blobs enormes no JSONB.
MAX_EVIDENCE_CHARS = 500


class FindingCategory(str, Enum):
    """Dimensões cobertas pelos analyzers do motor.

    São oito, contra as seis do enum `Dimension` do banco. A diferença é
    intencional: o enum do Postgres só ganha os valores novos na migration do
    PR 15, e o motor não precisa esperar por isso para existir. A conversão
    acontece na camada de persistência.
    """

    SECURITY = "security"
    QUALITY = "quality"
    ARCHITECTURE = "architecture"
    DEPENDENCIES = "dependencies"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    GIT = "git"
    CONFIGURATION = "configuration"


class Finding(BaseModel):
    """Um achado concreto, ancorado num arquivo e numa regra.

    `confidence` existe porque boa parte da análise é heurística: afirmar
    certeza sobre o que foi apenas inferido é pior do que declarar a dúvida.
    """

    id: str = Field(description="Identificador estável, derivado do conteúdo do achado")
    rule_id: str
    category: FindingCategory
    severity: Severity
    title: str
    description: str
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    evidence: str | None = Field(
        default=None,
        description="Trecho curto que sustenta o achado; segredos já vêm mascarados",
    )
    recommendation: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    analyzer: str

    @field_validator("evidence")
    @classmethod
    def _truncate_evidence(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) <= MAX_EVIDENCE_CHARS:
            return value
        return value[:MAX_EVIDENCE_CHARS] + "…"

    def to_legacy_dict(self) -> dict:
        """Serializa para o formato do JSONB, mantendo os campos históricos com
        os nomes que o frontend e o schema da API já esperam.

        `suggestion` e `line` são os nomes antigos de `recommendation` e
        `line_start`; ambos continuam presentes para não quebrar quem lê o
        formato anterior.
        """
        return {
            # --- campos que já existiam ---
            "title": self.title,
            "description": self.description,
            "suggestion": self.recommendation,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line": self.line_start,
            # --- campos novos do motor ---
            "id": self.id,
            "rule_id": self.rule_id,
            "category": self.category.value,
            "line_end": self.line_end,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "analyzer": self.analyzer,
        }

    @classmethod
    def from_legacy_dict(cls, data: dict) -> "Finding":
        """Reconstrói um `Finding` a partir do JSONB, inclusive de análises
        antigas que só têm os seis campos originais.

        Os campos ausentes recebem valores explícitos de "desconhecido" em vez
        de inventados: `rule_id` marca a origem legada e `confidence` cai, porque
        um achado sem regra rastreável merece menos peso.
        """
        legacy = "rule_id" not in data
        title = data.get("title", "Achado sem título")
        file_path = data.get("file_path")
        line_start = data.get("line_start", data.get("line"))

        return cls(
            id=data.get("id")
            or build_finding_id(
                rule_id=data.get("rule_id", "LEGACY"),
                file_path=file_path,
                line_start=line_start,
                title=title,
            ),
            rule_id=data.get("rule_id", "LEGACY"),
            category=FindingCategory(data.get("category", FindingCategory.QUALITY.value)),
            severity=Severity(data.get("severity", Severity.MEDIUM.value)),
            title=title,
            description=data.get("description", ""),
            file_path=file_path,
            line_start=line_start,
            line_end=data.get("line_end"),
            evidence=data.get("evidence"),
            recommendation=data.get("recommendation", data.get("suggestion")),
            confidence=data.get("confidence", 0.5 if legacy else 1.0),
            analyzer=data.get("analyzer", "legacy"),
        )


def build_finding_id(
    *, rule_id: str, file_path: str | None, line_start: int | None, title: str
) -> str:
    """Identificador determinístico: a mesma ocorrência no mesmo lugar produz
    sempre o mesmo id.

    Isso permite comparar duas análises do mesmo repositório e saber o que
    surgiu, sumiu ou permaneceu — e dá ao achado uma identidade que hoje não
    existe (achados vivem dentro do JSONB, sem chave própria).
    """
    material = f"{rule_id}|{file_path or ''}|{line_start if line_start is not None else ''}|{title}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    return f"finding-{digest}"
