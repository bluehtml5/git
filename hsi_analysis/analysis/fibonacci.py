"""Fibonacci retracement, extension, and overshoot target calculations."""
from __future__ import annotations

from typing import List, Tuple

import pandas as pd

from ..data.models import SupportResistanceZone

DEFAULT_RETRACE = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
DEFAULT_EXTEND = [1.0, 1.272, 1.414, 1.618, 2.0, 2.618]


def compute_fib_retracement(
    swing_high: float,
    swing_low: float,
    direction: str = "down",
) -> List[Tuple[float, float]]:
    """
    Compute Fibonacci retracement levels.
    direction='down': retracing from high (bearish swing, price pulled back up)
    direction='up':   retracing from low  (bullish swing, price pulled back down)

    Returns list of (ratio, price) tuples.
    """
    span = swing_high - swing_low
    results = []
    for ratio in DEFAULT_RETRACE:
        if direction == "down":
            price = swing_high - ratio * span
        else:
            price = swing_low + ratio * span
        results.append((ratio, round(price, 0)))
    return results


def compute_fib_extension(
    wave_a_start: float,
    wave_a_end: float,
    wave_b_end: float,
) -> List[Tuple[float, float]]:
    """
    Compute extension targets for wave C given an A-B-C structure.
    Extension is measured from wave_b_end in the direction of wave A.

    Returns list of (ratio, projected_price) tuples.
    """
    wave_a_length = abs(wave_a_end - wave_a_start)
    direction = 1 if wave_a_end > wave_a_start else -1
    results = []
    for ratio in DEFAULT_EXTEND:
        price = wave_b_end + direction * ratio * wave_a_length
        results.append((ratio, round(price, 0)))
    return results


def compute_overshoot_target(
    zone_price: float,
    direction: str,
    swing_range: float,
    extension: float = 0.272,
) -> float:
    """
    HSI overshoot calculation: zone ± extension × swing_range.

    HSI frequently breaks through S/R by 50–150 points (stop-hunting)
    before reversing. The 0.272 extension of the recent swing range
    approximates this empirically.

    direction='up':   overshoot = zone_price + extension * swing_range
    direction='down': overshoot = zone_price - extension * swing_range
    """
    offset = extension * swing_range
    if direction == "up":
        return round(zone_price + offset, 0)
    else:
        return round(zone_price - offset, 0)


def find_key_fibs(
    df: pd.DataFrame,
    lookback_bars: int = 60,
    current_price: float = None,
) -> List[SupportResistanceZone]:
    """
    Auto-detect the most recent significant swing and compute Fibonacci grid.
    Returns list of SupportResistanceZone with source='fibonacci'.
    """
    if df is None or len(df) < 10:
        return []

    recent = df.tail(lookback_bars)
    high = recent["high"]
    low = recent["low"]

    swing_high = float(high.max())
    swing_low = float(low.min())
    swing_range = swing_high - swing_low

    if swing_range < 1:
        return []

    if current_price is None:
        current_price = float(df["close"].iloc[-1])

    # Determine if we're in a retracement from high or from low
    high_bar = high.idxmax()
    low_bar = low.idxmin()

    # Whichever came last determines direction
    if df.index.get_loc(high_bar) > df.index.get_loc(low_bar):
        # High came after low → bullish swing, compute retracement from high
        direction = "down"
    else:
        direction = "up"

    levels = compute_fib_retracement(swing_high, swing_low, direction)
    zones: List[SupportResistanceZone] = []

    key_ratios = {0.236, 0.382, 0.5, 0.618, 0.786}
    for ratio, price in levels:
        if ratio not in key_ratios:
            continue
        zone_type = "support" if price <= current_price else "resistance"
        overshoot = compute_overshoot_target(
            price,
            "down" if zone_type == "support" else "up",
            swing_range,
        )
        zones.append(SupportResistanceZone(
            price=price,
            zone_type=zone_type,
            strength=4 if ratio in {0.382, 0.5, 0.618} else 3,
            source="fibonacci",
            overshoot_target=overshoot,
        ))

    return zones
