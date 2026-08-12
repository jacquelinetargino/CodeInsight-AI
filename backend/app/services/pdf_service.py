"""Renderiza o relatório de uma análise em PDF (HTML -> PDF via WeasyPrint),
reaproveitando os mesmos dados exibidos no dashboard."""

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app.models.analysis import Analysis
from app.models.enums import Dimension

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

DIMENSION_LABELS = {
    Dimension.SECURITY: "Segurança",
    Dimension.QUALITY: "Qualidade de Código",
    Dimension.ARCHITECTURE: "Arquitetura",
    Dimension.DOCUMENTATION: "Documentação",
    Dimension.TESTS: "Testes",
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

    return HTML(string=html_content).write_pdf()
