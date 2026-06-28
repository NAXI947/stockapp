from __future__ import annotations

from backend.app.strategy.chaos import compute_chaos_score, score_chaos_value
from backend.app.strategy.indicators import adjusted_moving_average, as_float, has_st_risk


def test_as_float_rejects_non_finite_values() -> None:
    assert as_float({"value": "nan"}, "value") is None
    assert as_float({"value": "inf"}, "value") is None
    assert as_float({"value": "2.5"}, "value") == 2.5


def test_adjusted_moving_average_preserves_existing_formula() -> None:
    series = [
        {"close": 10, "adj_factor": 1},
        {"close": 10, "adj_factor": 2},
    ]
    assert adjusted_moving_average(series, 1, 2) == 7.5


def test_st_risk_matches_existing_name_rule() -> None:
    assert has_st_risk("*ST示例") is True
    assert has_st_risk("普通股票") is False


def test_chaos_score_bands_are_explicit_and_stable() -> None:
    assert score_chaos_value(0.99) == 15
    assert score_chaos_value(1.0) == 10
    assert score_chaos_value(3.0) == 5
    assert score_chaos_value(8.0) == 0
    assert score_chaos_value(None) == 0


def test_chaos_requires_window_plus_one_rows() -> None:
    series = [
        {"close": 10.0, "high": 10.2, "low": 9.8, "turnover_rate": 1.0}
        for _ in range(20)
    ]
    assert compute_chaos_score(series, 19).value is None
