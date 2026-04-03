"""HSI-specific framework: monthly mid, 上軌/下軌 bands, AO prices, basis."""
from __future__ import annotations

from datetime import date
from typing import Tuple

import pandas as pd


def compute_monthly_mid(df_daily: pd.DataFrame, lookback: int = 22) -> float:
    """
    Monthly M (mid) price = (period_high + period_low) / 2
    over the past `lookback` trading days.
    This is the centre line of the HSI 框架 (framework) system.
    """
    if df_daily is None or len(df_daily) < 5:
        return 0.0
    recent = df_daily.tail(lookback)
    period_high = float(recent["high"].max())
    period_low = float(recent["low"].min())
    return round((period_high + period_low) / 2, 0)


def compute_framework_bands(
    monthly_mid: float,
    atr: float,
    multiplier: float = 1.5,
) -> Tuple[float, float]:
    """
    HSI framework upper (上軌) and lower (下軌) bands.
    upper = M + multiplier × ATR
    lower = M − multiplier × ATR

    The multiplier is configurable in config.yaml (default 1.5).
    Returns (lower_band, upper_band).
    """
    offset = multiplier * atr
    lower = round(monthly_mid - offset, 0)
    upper = round(monthly_mid + offset, 0)
    return lower, upper


def get_ao_prices(
    df_futures_big: pd.DataFrame,
    df_futures_mini: pd.DataFrame,
    trade_date: date,
) -> Tuple[float, float]:
    """
    Extract AO (opening auction) prices for 大期 and 細期.
    Uses the daily open column as the best yfinance approximation.
    Returns (ao_big, ao_mini).
    """
    def _get_open(df: pd.DataFrame) -> float:
        if df is None or df.empty:
            return 0.0
        # Try to match trade_date
        df_copy = df.copy()
        df_copy.index = pd.to_datetime(df_copy.index)
        target = pd.Timestamp(trade_date)
        # Look for the row on trade_date
        mask = df_copy.index.normalize() == target.normalize()
        subset = df_copy[mask]
        if not subset.empty:
            return float(subset["open"].iloc[0])
        # Fallback: last available open
        return float(df_copy["open"].iloc[-1])

    ao_big = _get_open(df_futures_big)
    ao_mini = _get_open(df_futures_mini)
    # If mini unavailable, estimate from big (mini ≈ big)
    if ao_mini == 0.0 and ao_big != 0.0:
        ao_mini = ao_big
    return ao_big, ao_mini


def compute_basis(futures_price: float, spot_index: float) -> float:
    """
    期現基差 = futures_price − spot_index
    Positive = contango (期貨升水)
    Negative = backwardation (期貨貼水)
    """
    return round(futures_price - spot_index, 0)


def assess_basis_signal(basis: float, atr: float) -> str:
    """Return a Chinese-language assessment of the basis level."""
    if atr == 0:
        return "正常"
    ratio = abs(basis) / atr
    if basis > 0:
        if ratio > 0.3:
            return "升水（期貨溢價明顯，市場情緒偏樂觀）"
        else:
            return "輕微升水"
    elif basis < 0:
        if ratio > 0.3:
            return "貼水（期貨折讓明顯，市場情緒偏謹慎）"
        else:
            return "輕微貼水"
    return "平水"
