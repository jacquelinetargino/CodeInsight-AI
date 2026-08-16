"""Renderiza o relatório de uma análise em PDF (HTML -> PDF via xhtml2pdf),
reaproveitando os mesmos dados exibidos no dashboard."""

from datetime import datetime
from io import BytesIO
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

from app.models.analysis import Analysis
from app.models.enums import Dimension

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

DIMENSION_LABELS = {
    Dimension.SECURITY: "Segurança",
    Dimension.QUALITY: "Qualidade de Código",
    Dimension.DEPENDENCIES: "Dependências",
    Dimension.ARCHITECTURE: "Arquitetura",
    Dimension.TESTING: "Testes",
    Dimension.CONFIGURATION: "Configuração",
    Dimension.DOCUMENTATION: "Documentação",
    Dimension.GIT: "Git",
}


def render_analysis_pdf(analysis: Analysis, repository_full_name: str) -> bytes:
    template = _env.get_template("report.html")

    results = [
        {
            "dimension_label": DIMENSION_LABELS.get(r.dimension, r.dimension.value),
            "score": r.score,
            "summary": r.summary,
            "findings": r.findings,
        }
        for r in sorted(analysis.results, key=lambda r: r.dimension.value)
    ]

    html_content = template.render(
        repository_full_name=repository_full_name,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
        overall_score=analysis.overall_score or 0,
        results=results,
        suggestions=[
            {"title": s.title, "description": s.description, "severity": s.severity.value}
            for s in analysis.suggestions
        ],
    )

    buffer = BytesIO()
    result = pisa.CreatePDF(html_content, dest=buffer)
    if result.err:
        raise RuntimeError(f"Falha ao gerar PDF do relatório (analysis {analysis.id})")
    return buffer.getvalue()
