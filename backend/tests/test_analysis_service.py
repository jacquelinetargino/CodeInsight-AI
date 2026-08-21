"""O que sobrou de `analysis_service` depois que o caminho de análise por prompt
foi removido.

`DIMENSION_WEIGHTS`, `DIMENSION_MODULES`, `compute_overall_score`,
`run_dimension_analysis` e `persist_dimension_result` viviam aqui e não tinham um
único chamador no repositório — a análise é do motor desde a migração. O que
eles garantiam continua garantido em outro lugar:

- que `Dimension` (banco) e `FindingCategory` (motor) não divirjam:
  `test_engine_scoring.py::test_os_dois_enums_de_dimensao_nao_podem_divergir`;
- que os pesos somem 1.0: `test_engine_scoring.py`, sobre a tabela do motor, que
  era a fonte única de onde a daqui era espelhada;
- que a média ponderada esteja certa: `score_repository`, no motor.

O que ficou aqui é o que não tem cobertura equivalente em outro arquivo.
"""

from app.models.enums import Dimension
from app.services.pdf_service import DIMENSION_LABELS


def test_every_dimension_has_a_report_label():
    """Uma dimensão sem rótulo apareceria como chave crua no PDF."""
    assert set(DIMENSION_LABELS) == set(Dimension)
