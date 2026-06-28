from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence

from backend.app.strategy.indicators import as_float


DEFAULT_CHAOS_WINDOW = 20
CHAOS_STABILIZER = 0.1
CHAOS_SCORE_BANDS: tuple[tuple[float, int], ...] = (
    (1.0, 15),
    (3.0, 10),
    (8.0, 5),
)
CHAOS_REJECTION_THRESHOLD = 8.0


@dataclass(frozen=True)
class ChaosScore:
    value: float | None
    score: int


def score_chaos_value(value: float | None) -> int:
    if value is None or not isfinite(value) or value < 0:
        return 0
    for upper_bound, score in CHAOS_SCORE_BANDS:
        if value < upper_bound:
            return score
    return 0


def compute_chaos_score(
    series: Sequence[Mapping[str, Any]],
    target_index: int,
    window: int = DEFAULT_CHAOS_WINDOW,
) -> ChaosScore:
    """Compute volume-price disorder from ``window`` friction observations."""
    if not series or window <= 0 or target_index < window or target_index >= len(series):
        return ChaosScore(None, 0)

    baseline_close = as_float(series[target_index - window], "close")
    current_close = as_float(series[target_index], "close")
    if baseline_close is None or baseline_close <= 0 or current_close is None or current_close <= 0:
        return ChaosScore(None, 0)

    daily_friction: list[float] = []
    for index in range(target_index - window + 1, target_index + 1):
        previous_close = as_float(series[index - 1], "close")
        high = as_float(series[index], "high")
        low = as_float(series[index], "low")
        turnover_rate = as_float(series[index], "turnover_rate")
        if (
            previous_close is None
            or previous_close <= 0
            or high is None
            or low is None
            or high < low
            or turnover_rate is None
            or turnover_rate < 0
        ):
            return ChaosScore(None, 0)
        friction = (high - low) / previous_close * 100.0 * turnover_rate
        if not isfinite(friction):
            return ChaosScore(None, 0)
        daily_friction.append(friction)

    mean_friction = sum(daily_friction) / window
    net_return_abs = abs((current_close - baseline_close) / baseline_close * 100.0)
    chaos_value = mean_friction / (net_return_abs + CHAOS_STABILIZER)
    if not isfinite(chaos_value) or chaos_value < 0:
        return ChaosScore(None, 0)

    rounded_value = round(chaos_value, 2)
    return ChaosScore(rounded_value, score_chaos_value(rounded_value))
