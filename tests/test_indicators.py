"""Tests for technical indicator calculations."""
import pytest
import pandas as pd
import numpy as np
from datetime import date

from hsi_analysis.analysis.indicators import (
    compute_macd,
    compute_rsi,
    compute_kdj,
    compute_atr,
    build_technical_signals,
)


def make_df(n=60, seed=42):
    rng = np.random.default_rng(seed)
    close = 20000 + np.cumsum(rng.normal(0, 100, n))
    high = close + rng.uniform(50, 200, n)
    low = close - rng.uniform(50, 200, n)
    volume = rng.uniform(1e6, 5e6, n)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": volume}, index=idx)


def test_macd_returns_correct_columns():
    df = make_df()
    result = compute_macd(df["close"])
    assert set(result.columns) == {"MACD_line", "MACD_signal", "MACD_hist"}
    assert len(result) == len(df)


def test_macd_histogram_equals_line_minus_signal():
    df = make_df()
    result = compute_macd(df["close"])
    diff = (result["MACD_line"] - result["MACD_signal"] - result["MACD_hist"]).dropna().abs()
    assert diff.max() < 1e-8


def test_rsi_range():
    df = make_df(100)
    rsi = compute_rsi(df["close"])
    valid = rsi.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_kdj_j_not_clipped():
    """KDJ J value should be allowed outside [0, 100]."""
    df = make_df(200, seed=99)
    kdj = compute_kdj(df["high"], df["low"], df["close"])
    assert set(kdj.columns) == {"K", "D", "J"}
    # J can exceed bounds — just check it's finite
    assert kdj["J"].dropna().apply(lambda x: np.isfinite(x)).all()


def test_atr_positive():
    df = make_df(50)
    atr = compute_atr(df["high"], df["low"], df["close"])
    assert (atr.dropna() > 0).all()


def test_build_technical_signals_structure():
    df = make_df(80)
    sig = build_technical_signals(df, "1d", date(2024, 3, 29))
    assert sig.timeframe == "1d"
    assert isinstance(sig.rsi, float)
    assert isinstance(sig.atr, float)
    assert sig.trend in ("bullish", "bearish", "ranging")
    assert sig.structure in ("HH/HL", "LH/LL", "HH/LL", "LH/HL", "unknown")


def test_build_technical_signals_short_df_returns_empty():
    df = make_df(10)
    sig = build_technical_signals(df, "1d", date(2024, 3, 29))
    assert sig.rsi == 50.0  # default empty signal value
