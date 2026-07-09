"""Real statistics over a domain's score history, via NumPy.

Nothing here is hand-rolled arithmetic: mean/std are ``ndarray`` reductions,
the trend line is an actual least-squares fit (``numpy.polyfit``), not a
"is the last number bigger than the first" heuristic.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_SPARK_CHARS = "▁▂▃▄▅▆▇█"


@dataclass(frozen=True)
class TrendStats:
    n: int
    mean: float
    std: float
    minimum: int
    maximum: int
    slope_per_run: float
    direction: str  # "improving" | "degrading" | "flat"
    sparkline: str


def analyze(points: list[int]) -> TrendStats | None:
    if not points:
        return None

    values = np.asarray(points, dtype=np.float64)
    n = values.size

    mean = float(np.mean(values))
    std = float(np.std(values))
    minimum = int(np.min(values))
    maximum = int(np.max(values))

    if n >= 2:
        x = np.arange(n, dtype=np.float64)
        slope, _intercept = np.polyfit(x, values, 1)
        slope = float(slope)
    else:
        slope = 0.0

    if abs(slope) < 0.15:
        direction = "flat"
    elif slope > 0:
        direction = "improving"
    else:
        direction = "degrading"

    sparkline = _sparkline(values)

    return TrendStats(
        n=n,
        mean=mean,
        std=std,
        minimum=minimum,
        maximum=maximum,
        slope_per_run=slope,
        direction=direction,
        sparkline=sparkline,
    )


def _sparkline(values: np.ndarray) -> str:
    lo, hi = float(np.min(values)), float(np.max(values))
    if hi == lo:
        return _SPARK_CHARS[-1] * values.size
    normalized = (values - lo) / (hi - lo)
    top = len(_SPARK_CHARS) - 1
    levels = np.clip((normalized * top).round().astype(int), 0, top)
    return "".join(_SPARK_CHARS[i] for i in levels)


def z_scores(points: list[int]) -> list[float]:
    """Per-sample z-score — how many std-devs each run is from the mean.

    Used to flag an unusually bad run (e.g. |z| > 2) instead of just the
    single most recent delta.
    """
    if len(points) < 2:
        return [0.0] * len(points)
    values = np.asarray(points, dtype=np.float64)
    std = float(np.std(values))
    if std == 0:
        return [0.0] * values.size
    mean = float(np.mean(values))
    return list(((values - mean) / std).round(2))
