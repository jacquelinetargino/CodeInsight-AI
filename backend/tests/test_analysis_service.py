from app.models.enums import Dimension
from app.services.analysis_service import (
    DIMENSION_MODULES,
    DIMENSION_WEIGHTS,
    compute_overall_score,
)


def test_all_six_dimensions_have_a_prompt_module_and_weight():
    assert set(DIMENSION_MODULES) == set(Dimension)
    assert set(DIMENSION_WEIGHTS) == set(Dimension)
    assert sum(DIMENSION_WEIGHTS.values()) == 1.0


def test_compute_overall_score_weighted_average_across_six_dimensions():
    scores = {
        Dimension.SECURITY: 80,
        Dimension.QUALITY: 60,
        Dimension.ARCHITECTURE: 100,
        Dimension.DOCUMENTATION: 40,
        Dimension.TESTS: 50,
        Dimension.GIT: 90,
    }
    # 80*.25 + 60*.25 + 100*.15 + 40*.15 + 50*.10 + 90*.10 = 20+15+15+6+5+9 = 70
    assert compute_overall_score(scores) == 70.0


def test_compute_overall_score_with_missing_dimensions_renormalizes_weights():
    scores = {Dimension.SECURITY: 100, Dimension.QUALITY: 100}
    assert compute_overall_score(scores) == 100.0


def test_compute_overall_score_empty_returns_zero():
    assert compute_overall_score({}) == 0.0
