from app.models.enums import Dimension
from app.services.analysis_service import (
    DIMENSION_MODULES,
    DIMENSION_WEIGHTS,
    compute_overall_score,
)
from app.services.pdf_service import DIMENSION_LABELS


def test_every_dimension_has_a_weight():
    assert set(DIMENSION_WEIGHTS) == set(Dimension)
    assert sum(DIMENSION_WEIGHTS.values()) == 1.0


def test_prompt_modules_cover_the_dimensions_that_the_ai_path_analyses():
    """O caminho de IA é legado e cobre menos que o motor.

    A asserção é de subconjunto, não de igualdade: `dependencies` e
    `configuration` são analisadas sem IA e não têm prompt — o que é o objetivo
    da migração, não uma lacuna.
    """
    assert set(DIMENSION_MODULES) < set(Dimension)
    assert set(Dimension) - set(DIMENSION_MODULES) == {
        Dimension.DEPENDENCIES,
        Dimension.CONFIGURATION,
    }


def test_every_dimension_has_a_report_label():
    """Uma dimensão sem rótulo apareceria como chave crua no PDF."""
    assert set(DIMENSION_LABELS) == set(Dimension)


def test_compute_overall_score_weighted_average():
    scores = {
        Dimension.SECURITY: 80,
        Dimension.QUALITY: 60,
        Dimension.DEPENDENCIES: 70,
        Dimension.ARCHITECTURE: 100,
        Dimension.TESTING: 50,
        Dimension.CONFIGURATION: 60,
        Dimension.DOCUMENTATION: 40,
        Dimension.GIT: 90,
    }
    # 80*.22 + 60*.16 + 70*.14 + 100*.12 + 50*.12 + 60*.10 + 40*.08 + 90*.06
    # = 17.6 + 9.6 + 9.8 + 12 + 6 + 6 + 3.2 + 5.4 = 69.6
    assert compute_overall_score(scores) == 69.6


def test_compute_overall_score_with_missing_dimensions_renormalizes_weights():
    scores = {Dimension.SECURITY: 100, Dimension.QUALITY: 100}
    assert compute_overall_score(scores) == 100.0


def test_compute_overall_score_empty_returns_zero():
    assert compute_overall_score({}) == 0.0
