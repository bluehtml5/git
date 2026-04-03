"""Track live risk state: drawdown, consecutive losses, daily P&L."""
from __future__ import annotations

from datetime import date
from typing import List

from ..storage.repository import TradeRepository


class RiskTracker:
    """
    Tracks risk state from the trade_results table.
    Provides risk_coefficient for position sizing adjustments.
    """

    def __init__(self, repo: TradeRepository, config):
        self.repo = repo
        self.config = config  # RiskConfig

    def get_consecutive_losses(self) -> int:
        """Count of consecutive losing trades (most recent first)."""
        pnl_list = self.repo.get_all_pnl_points()
        count = 0
        for pnl in reversed(pnl_list):
            if pnl < 0:
                count += 1
            else:
                break
        return count

    def get_current_risk_coefficient(self) -> float:
        """
        Return 1.0 normally; reduce to risk_coefficient_reduction
        if consecutive losses >= limit.
        """
        losses = self.get_consecutive_losses()
        if losses >= self.config.consecutive_loss_limit:
            return self.config.risk_coefficient_reduction
        return 1.0

    def get_max_drawdown(self, lookback_days: int = 30) -> float:
        """
        Max peak-to-trough drawdown as % of initial capital
        over the lookback period of trade results.
        """
        recent = self.repo.get_recent(n=50)
        if not recent:
            return 0.0

        # Use cumulative PnL in HKD
        equity = [0.0]
        for t in reversed(recent):
            equity.append(equity[-1] + (t.get("pnl_hkd") or 0.0))

        peak = equity[0]
        max_dd = 0.0
        for val in equity:
            if val > peak:
                peak = val
            dd = (peak - val) / (abs(peak) + 1e-9) * 100
            if dd > max_dd:
                max_dd = dd

        return round(max_dd, 2)

    def get_risk_state_summary(self) -> dict:
        """Return dict for inclusion in the daily report."""
        consecutive = self.get_consecutive_losses()
        coefficient = self.get_current_risk_coefficient()
        drawdown = self.get_max_drawdown()
        recent = self.repo.get_recent(n=10)
        total_trades = len(recent)
        wins = sum(1 for t in recent if (t.get("pnl_points") or 0) > 0)

        return {
            "consecutive_losses": consecutive,
            "risk_coefficient": coefficient,
            "max_drawdown_pct": drawdown,
            "recent_win_rate": round(wins / total_trades * 100, 1) if total_trades > 0 else 0.0,
            "total_recent_trades": total_trades,
            "size_reduced": coefficient < 1.0,
            "warning": (
                f"⚠️ 已連續虧損{consecutive}次，倉位調減至{coefficient*100:.0f}%"
                if coefficient < 1.0 else ""
            ),
        }
