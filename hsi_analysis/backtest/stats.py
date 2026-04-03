"""Backtest performance statistics."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np


@dataclass
class BacktestStats:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    avg_win_points: float
    avg_loss_points: float
    profit_factor: float
    sharpe_ratio: float
    max_drawdown_pct: float
    max_consecutive_losses: int
    total_pnl_hkd: float
    annualised_return_pct: float
    trade_records: List[dict] = field(default_factory=list)

    def summary_text(self) -> str:
        lines = [
            "=" * 40,
            "  回測統計結果 Backtest Statistics",
            "=" * 40,
            f"  總交易次數:       {self.total_trades}",
            f"  勝出次數:         {self.winning_trades}",
            f"  虧損次數:         {self.losing_trades}",
            f"  勝率:             {self.win_rate_pct:.1f}%",
            f"  平均盈利 (點):    {self.avg_win_points:.0f}",
            f"  平均虧損 (點):    {self.avg_loss_points:.0f}",
            f"  盈虧比 (PF):      {self.profit_factor:.2f}",
            f"  夏普比率:         {self.sharpe_ratio:.2f}",
            f"  最大回撤:         {self.max_drawdown_pct:.1f}%",
            f"  最大連續虧損次數:  {self.max_consecutive_losses}",
            f"  總盈虧 (HKD):     {self.total_pnl_hkd:,.0f}",
            f"  年化回報:         {self.annualised_return_pct:.1f}%",
            "=" * 40,
        ]
        return "\n".join(lines)


def compute_stats(
    trades: List[dict],
    initial_capital: float,
    risk_free_rate: float = 0.04,
    trading_days_per_year: int = 252,
) -> BacktestStats:
    """Compute all performance metrics from trade records."""
    if not trades:
        return BacktestStats(
            total_trades=0, winning_trades=0, losing_trades=0,
            win_rate_pct=0.0, avg_win_points=0.0, avg_loss_points=0.0,
            profit_factor=0.0, sharpe_ratio=0.0, max_drawdown_pct=0.0,
            max_consecutive_losses=0, total_pnl_hkd=0.0,
            annualised_return_pct=0.0, trade_records=trades,
        )

    pnl_points = [t["pnl_points"] for t in trades]
    pnl_hkd = [t["pnl_hkd"] for t in trades]

    wins = [p for p in pnl_points if p > 0]
    losses = [p for p in pnl_points if p < 0]

    win_rate = len(wins) / len(pnl_points) * 100 if pnl_points else 0.0
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = abs(np.mean(losses)) if losses else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    total_pnl = sum(pnl_hkd)
    max_dd = _compute_max_drawdown(pnl_hkd, initial_capital)
    max_consec_loss = compute_max_consecutive_losses([p > 0 for p in pnl_points])

    # Sharpe on daily HKD returns (one trade = one period approximation)
    daily_returns = np.array(pnl_hkd) / initial_capital
    sharpe = compute_sharpe(daily_returns, risk_free_rate)

    # Annualised return (CAGR approximation)
    n_years = max(len(trades) / trading_days_per_year, 1 / trading_days_per_year)
    end_equity = initial_capital + total_pnl
    cagr = ((end_equity / initial_capital) ** (1 / n_years) - 1) * 100 if initial_capital > 0 else 0.0

    return BacktestStats(
        total_trades=len(trades),
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate_pct=round(win_rate, 1),
        avg_win_points=round(avg_win, 0),
        avg_loss_points=round(avg_loss, 0),
        profit_factor=round(profit_factor, 2),
        sharpe_ratio=round(sharpe, 2),
        max_drawdown_pct=round(max_dd, 2),
        max_consecutive_losses=max_consec_loss,
        total_pnl_hkd=round(total_pnl, 0),
        annualised_return_pct=round(cagr, 1),
        trade_records=trades,
    )


def compute_sharpe(
    daily_returns,
    risk_free_rate: float = 0.04,
) -> float:
    """Annualised Sharpe ratio."""
    arr = np.array(daily_returns, dtype=float)
    if len(arr) == 0 or arr.std() == 0:
        return 0.0
    daily_rfr = risk_free_rate / 252
    excess = arr - daily_rfr
    return float((excess.mean() / excess.std()) * np.sqrt(252))


def compute_max_consecutive_losses(win_flags: List[bool]) -> int:
    """Length of the longest consecutive False (loss) streak."""
    max_streak = current = 0
    for flag in win_flags:
        if not flag:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak


def _compute_max_drawdown(pnl_hkd: List[float], initial_capital: float) -> float:
    equity = initial_capital
    peak = equity
    max_dd = 0.0
    for pnl in pnl_hkd:
        equity += pnl
        if equity > peak:
            peak = equity
        if peak > 0:
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)
    return max_dd
