"""Tests for Fibonacci level calculations."""
import pytest
from hsi_analysis.analysis.fibonacci import (
    compute_fib_retracement,
    compute_fib_extension,
    compute_overshoot_target,
    find_key_fibs,
)
import pandas as pd
import numpy as np


def test_fib_retracement_down_zero_level_is_high():
    levels = compute_fib_retracement(21000, 20000, direction="down")
    ratios = {r: p for r, p in levels}
    assert ratios[0.0] == 21000


def test_fib_retracement_down_one_level_is_low():
    levels = compute_fib_retracement(21000, 20000, direction="down")
    ratios = {r: p for r, p in levels}
    assert ratios[1.0] == 20000


def test_fib_retracement_golden_ratio():
    levels = compute_fib_retracement(21000, 20000, direction="down")
    ratios = {r: p for r, p in levels}
    expected = round(21000 - 0.618 * 1000, 0)
    assert ratios[0.618] == expected


def test_fib_retracement_up_zero_is_low():
    levels = compute_fib_retracement(21000, 20000, direction="up")
    ratios = {r: p for r, p in levels}
    assert ratios[0.0] == 20000


def test_overshoot_down():
    result = compute_overshoot_target(20000, "down", swing_range=1000)
    assert result < 20000
    assert result == round(20000 - 0.272 * 1000, 0)


def test_overshoot_up():
    result = compute_overshoot_target(21000, "up", swing_range=1000)
    assert result > 21000


def test_fib_extension_direction():
    """Extension targets should be in the correct direction."""
    exts = compute_fib_extension(20000, 21000, 20500)
    # Wave A goes up (20000→21000); extension from 20500 should be above 20500
    prices = [p for _, p in exts]
    assert all(p > 20500 for p in prices)


def make_df(n=80, seed=1):
    rng = np.random.default_rng(seed)
    close = 20000 + np.cumsum(rng.normal(0, 80, n))
    high = close + rng.uniform(30, 150, n)
    low = close - rng.uniform(30, 150, n)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame({"high": high, "low": low, "close": close}, index=idx)


def test_find_key_fibs_returns_zones():
    df = make_df()
    zones = find_key_fibs(df)
    assert isinstance(zones, list)
    for z in zones:
        assert z.source == "fibonacci"
        assert z.strength in (3, 4)
