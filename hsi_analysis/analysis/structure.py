"""Market structure: swing point detection, S/R zones, round numbers."""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd

try:
    from scipy.signal import argrelextrema
except ImportError:
    argrelextrema = None

from ..data.models import SupportResistanceZone


def detect_swing_points(
    df: pd.DataFrame,
    order: int = 5,
) -> Tuple[List[int], List[int]]:
    """
    Identify swing highs and swing lows using local extrema detection.
    Returns (swing_high_indices, swing_low_indices).
    order = number of bars on each side to confirm a swing.
    """
    high = df["high"].values
    low = df["low"].values

    if argrelextrema is not None and len(high) > 2 * order:
        sh_idx = list(argrelextrema(high, np.greater_equal, order=order)[0])
        sl_idx = list(argrelextrema(low, np.less_equal, order=order)[0])
    else:
        # Simple fallback: rolling window comparison
        sh_idx, sl_idx = [], []
        for i in range(order, len(high) - order):
            window_high = high[i - order: i + order + 1]
            window_low = low[i - order: i + order + 1]
            if high[i] == window_high.max():
                sh_idx.append(i)
            if low[i] == window_low.min():
                sl_idx.append(i)

    return sh_idx, sl_idx


def classify_market_structure(
    swing_highs: List[float],
    swing_lows: List[float],
) -> str:
    """
    Compare last two swing highs and last two swing lows.
    Returns: "HH/HL" | "LH/LL" | "HH/LL" | "LH/HL"
    """
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "unknown"

    hh = swing_highs[-1] > swing_highs[-2]
    hl = swing_lows[-1] > swing_lows[-2]

    if hh and hl:
        return "HH/HL"
    elif not hh and not hl:
        return "LH/LL"
    elif hh and not hl:
        return "HH/LL"
    else:
        return "LH/HL"


def build_sr_zones(
    df: pd.DataFrame,
    swing_high_idx: List[int],
    swing_low_idx: List[int],
    cluster_tolerance: float = 0.005,
) -> List[SupportResistanceZone]:
    """
    Cluster nearby swing points into S/R zones.
    Assigns strength 1–5 based on number of touches.
    cluster_tolerance = fraction of price for merging levels.
    """
    high = df["high"].values
    low = df["low"].values
    current_price = float(df["close"].iloc[-1])

    levels: List[Tuple[float, str]] = []
    for i in swing_high_idx:
        levels.append((high[i], "resistance"))
    for i in swing_low_idx:
        levels.append((low[i], "support"))

    if not levels:
        return []

    # Sort by price
    levels.sort(key=lambda x: x[0])

    # Cluster nearby levels
    clusters: List[List[Tuple[float, str]]] = []
    current_cluster: List[Tuple[float, str]] = [levels[0]]

    for price, zone_type in levels[1:]:
        cluster_ref = current_cluster[0][0]
        if abs(price - cluster_ref) / cluster_ref <= cluster_tolerance:
            current_cluster.append((price, zone_type))
        else:
            clusters.append(current_cluster)
            current_cluster = [(price, zone_type)]
    clusters.append(current_cluster)

    zones: List[SupportResistanceZone] = []
    for cluster in clusters:
        avg_price = sum(p for p, _ in cluster) / len(cluster)
        strength = min(5, len(cluster))
        zone_type = "support" if avg_price < current_price else "resistance"
        zones.append(SupportResistanceZone(
            price=round(avg_price, 0),
            zone_type=zone_type,
            strength=strength,
            source="structure",
        ))

    return zones


def identify_round_numbers(
    current_price: float,
    range_pct: float = 0.05,
    step: int = 200,
) -> List[SupportResistanceZone]:
    """
    Generate HSI round number levels (multiples of step) near current price.
    HSI is psychologically anchored to 200-point and 500-point rounds.
    """
    lower = current_price * (1 - range_pct)
    upper = current_price * (1 + range_pct)

    start = int(lower // step) * step
    zones: List[SupportResistanceZone] = []
    price = start
    while price <= upper:
        if lower <= price <= upper:
            zone_type = "support" if price <= current_price else "resistance"
            # Extra strength for multiples of 500 and 1000
            if price % 1000 == 0:
                strength = 4
            elif price % 500 == 0:
                strength = 3
            else:
                strength = 2
            zones.append(SupportResistanceZone(
                price=float(price),
                zone_type=zone_type,
                strength=strength,
                source="round_number",
            ))
        price += step

    return zones
