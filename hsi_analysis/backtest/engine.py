"""Event-driven backtesting engine."""
from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

import pandas as pd

from .strategy import BaseStrategy, HSIFrameworkStrategy
from .stats import BacktestStats, compute_stats

logger = logging.getLogger(__name__)

STRATEGY_REGISTRY = {
    "framework": HSIFrameworkStrategy,
}


class BacktestEngine:
    """
    Iterates over historical daily bars, calls strategy.on_bar() each day,
    and collects trade records for statistics.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        strategy: BaseStrategy,
        initial_capital: float = 1_000_000,
        contract_type: str = "mini",   # "big" or "mini"
        contracts: int = 1,
        commission_hkd: float = 60,    # round-trip HKD per contract (typical broker)
    ):
        self.df = df.copy()
        self.df.columns = [c.lower() for c in self.df.columns]
        self.strategy = strategy
        self.capital = initial_capital
        self.contract_type = contract_type
        self.contracts = contracts
        self.commission = commission_hkd
        self.multiplier = 50 if contract_type == "big" else 10
        self.trades: List[dict] = []

    def run(
        self,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> BacktestStats:
        """Execute the backtest loop and return statistics."""
        df = self.df.copy()
        df.index = pd.to_datetime(df.index)

        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]

        if df.empty:
            logger.warning("No data in backtest range")
            return compute_stats([], self.capital)

        self.strategy.reset()
        open_trade: Optional[dict] = None

        for i in range(1, len(df)):
            bar = df.iloc[i]
            history = df.iloc[:i]
            signal = self.strategy.on_bar(bar, history)

            if signal in ("buy", "sell") and open_trade is None:
                open_trade = {
                    "entry_bar": i,
                    "entry_price": float(bar["close"]),
                    "direction": "long" if signal == "buy" else "short",
                    "entry_date": df.index[i].date(),
                }

            elif signal in ("close_long", "close_short") and open_trade is not None:
                exit_price = float(bar["close"])
                entry_price = open_trade["entry_price"]
                direction = open_trade["direction"]
                pnl_points = (
                    (exit_price - entry_price)
                    if direction == "long"
                    else (entry_price - exit_price)
                )
                pnl_hkd = (
                    pnl_points * self.multiplier * self.contracts
                    - self.commission * self.contracts
                )
                trade_record = {
                    **open_trade,
                    "exit_bar": i,
                    "exit_price": exit_price,
                    "exit_date": df.index[i].date(),
                    "pnl_points": round(pnl_points, 0),
                    "pnl_hkd": round(pnl_hkd, 0),
                    "contracts": self.contracts,
                    "contract_type": self.contract_type,
                }
                self.trades.append(trade_record)
                open_trade = None

        # Close any remaining open trade at last bar
        if open_trade is not None:
            last_bar = df.iloc[-1]
            exit_price = float(last_bar["close"])
            entry_price = open_trade["entry_price"]
            direction = open_trade["direction"]
            pnl_points = (
                (exit_price - entry_price)
                if direction == "long"
                else (entry_price - exit_price)
            )
            pnl_hkd = pnl_points * self.multiplier * self.contracts - self.commission
            self.trades.append({
                **open_trade,
                "exit_bar": len(df) - 1,
                "exit_price": exit_price,
                "exit_date": df.index[-1].date(),
                "pnl_points": round(pnl_points, 0),
                "pnl_hkd": round(pnl_hkd, 0),
                "contracts": self.contracts,
                "contract_type": self.contract_type,
                "note": "force-closed at end of backtest",
            })

        return compute_stats(self.trades, self.capital)

    @classmethod
    def from_name(
        cls,
        strategy_name: str,
        df: pd.DataFrame,
        initial_capital: float = 1_000_000,
        strategy_params: dict = None,
        **kwargs,
    ) -> "BacktestEngine":
        """Factory: create engine from registered strategy name."""
        strat_cls = STRATEGY_REGISTRY.get(strategy_name)
        if strat_cls is None:
            raise ValueError(
                f"Unknown strategy '{strategy_name}'. "
                f"Available: {list(STRATEGY_REGISTRY.keys())}"
            )
        strategy = strat_cls(strategy_params or {})
        return cls(df, strategy, initial_capital=initial_capital, **kwargs)
