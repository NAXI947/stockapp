from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Sequence


Row = Mapping[str, Any]


def as_float(row: Mapping[str, Any], key: str, default: float | None = None) -> float | None:
    """Return a finite float from a row-like object, or the supplied default."""
    try:
        value = row[key]
        if value is None or str(value).strip() == "":
            return default
        result = float(value)
        return result if isfinite(result) else default
    except (KeyError, IndexError, TypeError, ValueError):
        return default


def latest_adjustment_factor(series: Sequence[Row], index: int) -> float | None:
    """Find the latest positive adjustment factor at or before ``index``."""
    for current_index in range(index, -1, -1):
        adjustment_factor = as_float(series[current_index], "adj_factor")
        if adjustment_factor is not None and adjustment_factor > 0:
            return adjustment_factor
    return None


def adjusted_moving_average(series: Sequence[Row], index: int, window: int) -> float | None:
    """Calculate an adjusted close moving average for a positive window."""
    if window <= 0 or index < 0 or index >= len(series) or index + 1 < window:
        return None

    current_adjustment = latest_adjustment_factor(series, index)
    if current_adjustment is None:
        return None

    adjusted_prices: list[float] = []
    for item in series[index - window + 1 : index + 1]:
        close = as_float(item, "close")
        if close is None:
            return None
        item_adjustment = as_float(item, "adj_factor") or current_adjustment
        adjusted_prices.append(close * item_adjustment / current_adjustment)
    return round(sum(adjusted_prices) / window, 4)


def has_st_risk(stock_name: str | None) -> bool:
    """Match the existing ST-name exclusion rule."""
    return bool(stock_name and "ST" in stock_name.upper())
