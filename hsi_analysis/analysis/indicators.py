"""Technical indicators: MACD, RSI, KDJ, ATR, Bollinger Bands."""
from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd

ta = None  # pandas-ta not required; all indicators have built-in implementations

from ..data.models import TechnicalSignals

logger = logging.getLogger(__name__)


def _safe_float(series: pd.Series, idx: int = -1) -> float:
    """Extract a float from a Series safely, returning 0.0 on failure."""
    try:
        val = series.iloc[idx]
        return float(val) if pd.notna(val) else 0.0
    except (IndexError, TypeError):
        return 0.0


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Return DataFrame with columns: MACD_line, MACD_signal, MACD_hist."""
    if ta is not None:
        result = ta.macd(close, fast=fast, slow=slow, signal=signal)
        if result is not None and not result.empty:
            result.columns = ["MACD_line", "MACD_hist", "MACD_signal"]
            return result[["MACD_line", "MACD_signal", "MACD_hist"]]

    # Manual fallback
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_sig = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - macd_sig
    return pd.DataFrame({
        "MACD_line": macd_line,
        "MACD_signal": macd_sig,
        "MACD_hist": macd_hist,
    })


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI."""
    if ta is not None:
        result = ta.rsi(close, length=period)
        if result is not None:
            return result

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_kdj(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 9,
    signal: int = 3,
) -> pd.DataFrame:
    """
    KDJ stochastic. J = 3K − 2D.
    Note: J can exceed [0, 100] — do NOT clip values.
    """
    if ta is not None:
        stoch = ta.stoch(high, low, close, k=period, d=signal, smooth_k=signal)
        if stoch is not None and not stoch.empty:
            k_col = [c for c in stoch.columns if "_K" in c]
            d_col = [c for c in stoch.columns if "_D" in c]
            if k_col and d_col:
                k = stoch[k_col[0]]
                d = stoch[d_col[0]]
                j = 3 * k - 2 * d
                return pd.DataFrame({"K": k, "D": d, "J": j})

    # Manual fallback
    lowest_low = low.rolling(period).min()
    highest_high = high.rolling(period).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan) * 100
    k = rsv.ewm(com=signal - 1, adjust=False).mean()
    d = k.ewm(com=signal - 1, adjust=False).mean()
    j = 3 * k - 2 * d
    return pd.DataFrame({"K": k, "D": d, "J": j})


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range."""
    if ta is not None:
        result = ta.atr(high, low, close, length=period)
        if result is not None:
            return result

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def compute_bollinger(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> pd.DataFrame:
    """Bollinger Bands. Returns DataFrame with columns: upper, mid, lower."""
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    return pd.DataFrame({
        "upper": mid + std_dev * std,
        "mid": mid,
        "lower": mid - std_dev * std,
    })


def build_technical_signals(
    df: pd.DataFrame,
    timeframe: str,
    report_date: date,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal_period: int = 9,
    rsi_period: int = 14,
    kdj_period: int = 9,
    atr_period: int = 14,
) -> TechnicalSignals:
    """
    Compute all indicators on df and return a TechnicalSignals for the latest bar.
    df must have columns: open, high, low, close, volume (lowercase).
    """
    if df is None or len(df) < macd_slow + macd_signal_period:
        return _empty_signals(report_date, timeframe)

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    macd_df = compute_macd(close, macd_fast, macd_slow, macd_signal_period)
    rsi_series = compute_rsi(close, rsi_period)
    kdj_df = compute_kdj(high, low, close, kdj_period)
    atr_series = compute_atr(high, low, close, atr_period)

    # Determine market structure from last 20 bars
    structure = _classify_structure(high.tail(20), low.tail(20))
    trend = _classify_trend(macd_df["MACD_hist"])

    return TechnicalSignals(
        trade_date=report_date,
        timeframe=timeframe,
        macd_line=_safe_float(macd_df["MACD_line"]),
        macd_signal=_safe_float(macd_df["MACD_signal"]),
        macd_hist=_safe_float(macd_df["MACD_hist"]),
        rsi=_safe_float(rsi_series),
        kdj_k=_safe_float(kdj_df["K"]),
        kdj_d=_safe_float(kdj_df["D"]),
        kdj_j=_safe_float(kdj_df["J"]),
        atr=_safe_float(atr_series),
        structure=structure,
        trend=trend,
        close=_safe_float(close),
    )


def _classify_structure(high: pd.Series, low: pd.Series) -> str:
    """Classify last two swing highs/lows as HH/HL, LH/LL, etc."""
    if len(high) < 4:
        return "unknown"
    mid = len(high) // 2
    recent_high = high.iloc[mid:].max()
    prior_high = high.iloc[:mid].max()
    recent_low = low.iloc[mid:].min()
    prior_low = low.iloc[:mid].min()

    higher_high = recent_high > prior_high
    higher_low = recent_low > prior_low

    if higher_high and higher_low:
        return "HH/HL"
    elif not higher_high and not higher_low:
        return "LH/LL"
    elif higher_high and not higher_low:
        return "HH/LL"
    else:
        return "LH/HL"


def _classify_trend(macd_hist: pd.Series) -> str:
    """Simple trend classification from MACD histogram direction."""
    if len(macd_hist) < 3:
        return "ranging"
    recent = macd_hist.dropna().tail(3)
    if len(recent) < 2:
        return "ranging"
    if recent.iloc[-1] > 0 and recent.iloc[-1] > recent.iloc[-2]:
        return "bullish"
    elif recent.iloc[-1] < 0 and recent.iloc[-1] < recent.iloc[-2]:
        return "bearish"
    else:
        return "ranging"


def _empty_signals(report_date: date, timeframe: str) -> TechnicalSignals:
    return TechnicalSignals(
        trade_date=report_date,
        timeframe=timeframe,
        macd_line=0.0, macd_signal=0.0, macd_hist=0.0,
        rsi=50.0, kdj_k=50.0, kdj_d=50.0, kdj_j=50.0,
        atr=0.0, structure="unknown", trend="ranging",
    )
