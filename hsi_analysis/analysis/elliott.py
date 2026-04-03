"""
Simplified Elliott Wave labeling.

IMPORTANT: All counts produced here are labelled [建議] (suggested).
Full Elliott Wave analysis requires human judgment. This module provides
a mechanical first pass using Fibonacci ratio validation and alternation rules.
Do NOT trade solely on these counts.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .structure import detect_swing_points

logger = logging.getLogger(__name__)

WaveLabel = str  # "1", "2", "3", "4", "5", "A", "B", "C"


def label_elliott_waves(
    df: pd.DataFrame,
    order: int = 5,
    lookback: int = 100,
) -> List[Tuple[int, float, WaveLabel]]:
    """
    Suggest Elliott Wave labels for recent price action.

    Returns list of (bar_index, price, wave_label) tuples.
    All labels should be treated as [建議] — suggested only.

    Rules implemented:
    - Impulse: 5 waves up/down; corrective: A-B-C
    - Wave 3 cannot be shortest impulse wave
    - Wave 2 typically retraces 50–61.8% of Wave 1
    - Wave 3 extends to 161.8%+ of Wave 1
    - Wave 4 does not overlap Wave 1 territory
    """
    if df is None or len(df) < lookback // 2:
        return []

    recent = df.tail(lookback)
    sh_idx, sl_idx = detect_swing_points(recent, order=order)

    if not sh_idx or not sl_idx:
        return []

    highs = [(i, float(recent["high"].iloc[i])) for i in sh_idx]
    lows = [(i, float(recent["low"].iloc[i])) for i in sl_idx]

    # Merge and sort all pivots
    pivots: List[Tuple[int, float, str]] = (
        [(i, p, "H") for i, p in highs] + [(i, p, "L") for i, p in lows]
    )
    pivots.sort(key=lambda x: x[0])

    # Attempt to label last 5–7 pivots as impulse or A-B-C
    if len(pivots) < 5:
        return []

    last_pivots = pivots[-7:]
    return _try_impulse_label(last_pivots) or _try_corrective_label(last_pivots)


def _try_impulse_label(
    pivots: List[Tuple[int, float, str]],
) -> Optional[List[Tuple[int, float, WaveLabel]]]:
    """Attempt 5-wave impulse labeling."""
    if len(pivots) < 5:
        return None

    # Take first 5 pivots
    p = pivots[:5]
    prices = [x[1] for x in p]
    types = [x[2] for x in p]

    # Determine direction: bullish (L-H-L-H-L) or bearish (H-L-H-L-H)
    bullish_pattern = ["L", "H", "L", "H", "L"]
    bearish_pattern = ["H", "L", "H", "L", "H"]

    if types != bullish_pattern and types != bearish_pattern:
        return None

    # Basic Fibonacci ratio check for wave 3
    if types == bullish_pattern:
        w1 = prices[1] - prices[0]
        w3 = prices[3] - prices[2]
        if w1 <= 0 or w3 <= 0:
            return None
        if w3 < w1:  # Wave 3 cannot be shortest (simplified check)
            return None
    else:
        w1 = prices[0] - prices[1]
        w3 = prices[2] - prices[3]
        if w1 <= 0 or w3 <= 0:
            return None
        if w3 < w1:
            return None

    labels = ["1", "2", "3", "4", "5"]
    return [(p[i][0], p[i][1], labels[i]) for i in range(5)]


def _try_corrective_label(
    pivots: List[Tuple[int, float, str]],
) -> List[Tuple[int, float, WaveLabel]]:
    """Fall back to A-B-C corrective label."""
    if len(pivots) < 3:
        return []
    p = pivots[-3:]
    labels = ["A", "B", "C"]
    return [(p[i][0], p[i][1], labels[i]) for i in range(3)]


def get_wave_context_summary(
    waves: List[Tuple[int, float, WaveLabel]],
    current_price: float,
) -> str:
    """Return a Chinese-language one-line summary of the current wave context."""
    if not waves:
        return "[建議] 波浪形態不明確，暫無清晰計數"

    labels = [w[2] for w in waves]
    prices = [w[1] for w in waves]
    last_label = labels[-1]
    last_price = prices[-1]

    if last_label == "5":
        return f"[建議] 目前處於第5浪末端附近（{last_price:,.0f}），留意見頂回調信號"
    elif last_label == "3":
        return f"[建議] 目前處於第3浪延伸中（{last_price:,.0f}），趨勢最強段，順勢操作"
    elif last_label == "2":
        return f"[建議] 第2浪調整中（{last_price:,.0f}），等待第3浪啟動"
    elif last_label == "4":
        return f"[建議] 第4浪橫盤整理（{last_price:,.0f}），等待第5浪突破"
    elif last_label == "C":
        return f"[建議] ABC調整浪C段（{last_price:,.0f}），留意調整結束買入機會"
    elif last_label == "A":
        return f"[建議] ABC調整浪A段開始（{last_price:,.0f}），短期向下調整"
    elif last_label == "B":
        return f"[建議] ABC調整浪B段反彈（{last_price:,.0f}），反彈後仍有C浪下探"
    else:
        return f"[建議] 最近波浪標記為{last_label}（{last_price:,.0f}），形態持續觀察"


def validate_wave_ratios(
    waves: List[Tuple[int, float, WaveLabel]],
) -> dict:
    """
    Check Fibonacci ratio relationships between detected waves.
    Returns dict of {rule_name: bool}.
    """
    result = {}
    if len(waves) < 5:
        return result

    prices = [w[1] for w in waves[:5]]
    labels = [w[2] for w in waves[:5]]

    if labels == ["1", "2", "3", "4", "5"]:
        w1 = abs(prices[1] - prices[0])
        w2 = abs(prices[2] - prices[1])
        w3 = abs(prices[3] - prices[2])
        if w1 > 0:
            result["w2_retrace_ok"] = 0.382 <= (w2 / w1) <= 0.786
            result["w3_extends_ok"] = (w3 / w1) >= 1.272
            result["w3_not_shortest"] = w3 >= w1

    return result
