"""Base strategy class and default HSI framework band strategy."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd


class BaseStrategy(ABC):
    """Abstract base for all backtest strategies."""

    def __init__(self, params: dict):
        self.params = params
        self.position = 0       # +1 long, -1 short, 0 flat
        self.entry_price: Optional[float] = None
        self.stop_loss: Optional[float] = None
        self.target: Optional[float] = None

    @abstractmethod
    def on_bar(self, bar: pd.Series, history: pd.DataFrame) -> Optional[str]:
        """
        Called on each new bar.
        Return one of: "buy", "sell", "close_long", "close_short", None
        """
        ...

    def get_position(self) -> int:
        return self.position

    def reset(self) -> None:
        self.position = 0
        self.entry_price = None
        self.stop_loss = None
        self.target = None


class HSIFrameworkStrategy(BaseStrategy):
    """
    Default strategy: buy near lower framework band, sell near upper band.
    Trend filter: only long if daily MACD histogram > 0, only short if < 0.

    Parameters (via params dict):
      atr_multiplier: float = 1.5   (band width)
      lookback: int = 22            (monthly mid lookback)
      stop_atr: float = 1.5         (stop as ATR multiple)
      target_rr: float = 2.0        (target as R:R multiple)
    """

    def __init__(self, params: dict = None):
        super().__init__(params or {})
        self.atr_mult = self.params.get("atr_multiplier", 1.5)
        self.lookback = self.params.get("lookback", 22)
        self.stop_atr = self.params.get("stop_atr", 1.5)
        self.target_rr = self.params.get("target_rr", 2.0)

    def on_bar(self, bar: pd.Series, history: pd.DataFrame) -> Optional[str]:
        if len(history) < self.lookback + 26:
            return None

        close = float(bar.get("close", 0))
        high_col = "high"
        low_col = "low"
        close_col = "close"

        recent = history.tail(self.lookback)
        m = (float(recent[high_col].max()) + float(recent[low_col].min())) / 2

        # ATR approximation
        tr = history.tail(self.lookback)[close_col].diff().abs()
        atr = float(tr.mean()) * 2  # rough ATR proxy

        lower_band = m - self.atr_mult * atr
        upper_band = m + self.atr_mult * atr

        # MACD filter (EMA 12/26)
        ema12 = history[close_col].ewm(span=12).mean()
        ema26 = history[close_col].ewm(span=26).mean()
        macd_hist = float((ema12 - ema26).iloc[-1])

        if self.position == 0:
            # Entry: price touches lower band and MACD turning positive
            if close <= lower_band * 1.005 and macd_hist > 0:
                self.entry_price = close
                self.stop_loss = close - self.stop_atr * atr
                self.target = close + self.target_rr * self.stop_atr * atr
                self.position = 1
                return "buy"
            # Short: price at upper band and MACD turning negative
            elif close >= upper_band * 0.995 and macd_hist < 0:
                self.entry_price = close
                self.stop_loss = close + self.stop_atr * atr
                self.target = close - self.target_rr * self.stop_atr * atr
                self.position = -1
                return "sell"

        elif self.position == 1:
            # Exit long: hit target or stop
            if close >= self.target or close <= self.stop_loss:
                self.position = 0
                return "close_long"

        elif self.position == -1:
            # Exit short: hit target or stop
            if close <= self.target or close >= self.stop_loss:
                self.position = 0
                return "close_short"

        return None
