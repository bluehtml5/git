"""Tests for HSI framework calculations."""
import pytest
import pandas as pd
import numpy as np
from datetime import date

from hsi_analysis.analysis.framework import (
    compute_monthly_mid,
    compute_framework_bands,
    compute_basis,
    assess_basis_signal,
    get_ao_prices,
)


def make_df(n=30):
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    close = np.linspace(19000, 21000, n)
    return pd.DataFrame({
        "open": close,
        "high": close + 200,
        "low": close - 200,
        "close": close,
    }, index=idx)


def test_monthly_mid_midpoint():
    df = make_df(22)
    mid = compute_monthly_mid(df, lookback=22)
    expected = (df["high"].max() + df["low"].min()) / 2
    assert mid == round(expected, 0)


def test_monthly_mid_short_df():
    df = make_df(2)
    mid = compute_monthly_mid(df, lookback=22)
    assert mid >= 0  # doesn't crash


def test_framework_bands_symmetry():
    lower, upper = compute_framework_bands(20000, atr=500, multiplier=1.5)
    assert upper == 20000 + round(1.5 * 500, 0)
    assert lower == 20000 - round(1.5 * 500, 0)
    assert upper > lower


def test_framework_upper_gt_mid_gt_lower():
    lower, upper = compute_framework_bands(20000, atr=300, multiplier=2.0)
    assert lower < 20000 < upper


def test_basis_positive():
    assert compute_basis(20100, 20000) == 100.0


def test_basis_negative():
    assert compute_basis(19900, 20000) == -100.0


def test_assess_basis_signal_premium():
    result = assess_basis_signal(600, atr=500)
    assert "升水" in result


def test_assess_basis_signal_discount():
    result = assess_basis_signal(-600, atr=500)
    assert "貼水" in result


def test_assess_basis_signal_flat():
    result = assess_basis_signal(0, atr=500)
    assert result == "平水"


def test_get_ao_prices_fallback():
    df = make_df(5)
    ao_big, ao_mini = get_ao_prices(df, df, date(2099, 1, 1))  # future date → fallback
    assert ao_big == float(df["open"].iloc[-1])
