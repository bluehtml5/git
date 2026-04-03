"""Tests for backtest engine and statistics."""
import pytest
import pandas as pd
import numpy as np
from datetime import date

from hsi_analysis.backtest.stats import (
    compute_stats,
    compute_max_consecutive_losses,
    compute_sharpe,
    BacktestStats,
)
from hsi_analysis.backtest.engine import BacktestEngine
from hsi_analysis.backtest.strategy import HSIFrameworkStrategy


def make_df(n=200, seed=42, trend=0):
    """Create synthetic OHLCV data."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(trend, 100, n)
    close = 20000 + np.cumsum(returns)
    close = np.maximum(close, 1000)
    high = close + rng.uniform(50, 200, n)
    low = close - rng.uniform(50, 200, n)
    low = np.minimum(low, close)
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.DataFrame({
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.uniform(1e6, 5e6, n),
    }, index=idx)


def make_trades(n_win, n_loss, win_pts=200, loss_pts=-100):
    trades = []
    for i in range(n_win):
        trades.append({"pnl_points": win_pts, "pnl_hkd": win_pts * 10})
    for i in range(n_loss):
        trades.append({"pnl_points": loss_pts, "pnl_hkd": loss_pts * 10})
    return trades


class TestComputeStats:
    def test_win_rate(self):
        trades = make_trades(6, 4)
        stats = compute_stats(trades, 1_000_000)
        assert stats.win_rate_pct == pytest.approx(60.0, abs=0.1)

    def test_profit_factor(self):
        trades = make_trades(3, 3, win_pts=200, loss_pts=-100)
        stats = compute_stats(trades, 1_000_000)
        assert stats.profit_factor == pytest.approx(2.0, abs=0.01)

    def test_empty_trades(self):
        stats = compute_stats([], 1_000_000)
        assert stats.total_trades == 0
        assert stats.sharpe_ratio == 0.0

    def test_total_pnl(self):
        trades = make_trades(5, 5, win_pts=100, loss_pts=-50)
        stats = compute_stats(trades, 1_000_000)
        assert stats.total_pnl_hkd == pytest.approx((5 * 100 + 5 * (-50)) * 10)


class TestMaxConsecutiveLosses:
    def test_all_wins(self):
        assert compute_max_consecutive_losses([True, True, True]) == 0

    def test_all_losses(self):
        assert compute_max_consecutive_losses([False, False, False]) == 3

    def test_mixed(self):
        assert compute_max_consecutive_losses([True, False, False, True, False]) == 2

    def test_empty(self):
        assert compute_max_consecutive_losses([]) == 0


class TestSharpe:
    def test_positive_returns_positive_sharpe(self):
        # Varying positive returns so std > 0
        rng = np.random.default_rng(0)
        returns = np.abs(rng.normal(0.002, 0.001, 100))
        sharpe = compute_sharpe(returns)
        assert sharpe > 0

    def test_zero_std_returns_zero(self):
        returns = np.array([0.0] * 20)
        assert compute_sharpe(returns) == 0.0


class TestBacktestEngine:
    def test_engine_runs_without_error(self):
        df = make_df(200)
        engine = BacktestEngine.from_name("framework", df, initial_capital=1_000_000)
        stats = engine.run()
        assert isinstance(stats, BacktestStats)
        assert stats.total_trades >= 0

    def test_engine_respects_date_range(self):
        df = make_df(300)
        engine = BacktestEngine.from_name("framework", df)
        stats_short = engine.run(
            start=date(2022, 6, 1),
            end=date(2022, 9, 1),
        )
        # Fewer bars → fewer or equal trades than full range
        engine2 = BacktestEngine.from_name("framework", df)
        stats_full = engine2.run()
        assert stats_short.total_trades <= stats_full.total_trades

    def test_unknown_strategy_raises(self):
        df = make_df(100)
        with pytest.raises(ValueError):
            BacktestEngine.from_name("nonexistent_strategy", df)
