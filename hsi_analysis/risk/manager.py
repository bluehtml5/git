"""Position sizing, stop-loss calculation, and risk-reward validation."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from ..config.settings import FuturesConfig, RiskConfig


@dataclass
class PositionSizing:
    big_contracts: int
    mini_contracts: int
    risk_amount_hkd: float
    risk_pct_of_account: float
    stop_points: int
    adjusted: bool  # True if reduced by consecutive loss rule


class RiskManager:
    """Calculates position sizes and validates trade setups."""

    def __init__(self, risk_config: RiskConfig, futures_config: FuturesConfig):
        self.rc = risk_config
        self.fc = futures_config

    def calculate_position_size(
        self,
        account_size: float,
        entry_price: float,
        stop_loss_price: float,
        risk_coefficient: float = 1.0,
        prefer_mini: bool = True,
    ) -> PositionSizing:
        """
        Core position sizing:
          risk_per_trade = account × max_risk_pct × risk_coefficient
          points_at_risk = |entry − stop|
          big_lots = floor(risk / (points × big_multiplier))
          mini_lots = floor(risk / (points × mini_multiplier))

        prefer_mini=True: suggest mini contracts first (lower capital requirement).
        """
        stop_points = abs(round(entry_price - stop_loss_price))
        if stop_points == 0:
            return PositionSizing(0, 0, 0.0, 0.0, 0, False)

        max_risk_hkd = account_size * (self.rc.max_risk_per_trade_pct / 100) * risk_coefficient
        adjusted = risk_coefficient < 1.0

        big_risk_per = stop_points * self.fc.big_lot_multiplier
        mini_risk_per = stop_points * self.fc.mini_lot_multiplier

        big_contracts = max(0, math.floor(max_risk_hkd / big_risk_per)) if not prefer_mini else 0
        mini_contracts = max(0, math.floor(max_risk_hkd / mini_risk_per))

        if prefer_mini and mini_contracts == 0:
            # Even one mini is too risky — fall back to fractional suggestion
            mini_contracts = 1

        actual_risk_hkd = (
            (big_contracts * big_risk_per + mini_contracts * mini_risk_per)
            if not prefer_mini
            else mini_contracts * mini_risk_per
        )
        risk_pct = (actual_risk_hkd / account_size) * 100

        return PositionSizing(
            big_contracts=big_contracts,
            mini_contracts=mini_contracts,
            risk_amount_hkd=actual_risk_hkd,
            risk_pct_of_account=risk_pct,
            stop_points=int(stop_points),
            adjusted=adjusted,
        )

    def calculate_stop_loss(
        self,
        entry_price: float,
        direction: str,
        atr: float,
        atr_multiplier: float = 1.5,
        nearest_sr_level: Optional[float] = None,
    ) -> float:
        """
        Stop loss = entry ± max(atr_multiplier × ATR, distance to nearest S/R).
        HSI: stops placed beyond round numbers for cleaner execution.
        """
        atr_stop = atr * atr_multiplier
        if nearest_sr_level is not None:
            sr_distance = abs(entry_price - nearest_sr_level)
            offset = max(atr_stop, sr_distance * 1.05)  # 5% beyond S/R
        else:
            offset = atr_stop

        # Round to nearest 10 for HSI
        offset = round(offset / 10) * 10

        if direction == "long":
            return round(entry_price - offset, 0)
        else:
            return round(entry_price + offset, 0)

    def calculate_target(
        self,
        entry_price: float,
        stop_loss_price: float,
        direction: str,
        rr_ratio: float = 2.0,
    ) -> float:
        """Calculate profit target based on risk-reward ratio."""
        risk = abs(entry_price - stop_loss_price)
        reward = risk * rr_ratio
        if direction == "long":
            return round(entry_price + reward, 0)
        else:
            return round(entry_price - reward, 0)

    def validate_risk_reward(
        self,
        entry: float,
        stop: float,
        target: float,
        min_rr: Optional[float] = None,
    ) -> Tuple[bool, float]:
        """Returns (is_acceptable, actual_rr_ratio)."""
        if min_rr is None:
            min_rr = self.rc.min_risk_reward
        risk = abs(entry - stop)
        reward = abs(target - entry)
        if risk == 0:
            return False, 0.0
        rr = reward / risk
        return rr >= min_rr, round(rr, 2)

    def format_trade_suggestion(
        self,
        direction: str,
        entry: float,
        stop: float,
        target1: float,
        target2: float,
        sizing: PositionSizing,
    ) -> str:
        """Format a Chinese-language trade suggestion string."""
        action = "揸" if direction == "long" else "沽"
        stop_pts = abs(round(entry - stop))
        t1_pts = abs(round(target1 - entry))
        side = "Set" + (" 買入" if direction == "long" else " 賣出")
        return (
            f"{side} {entry:,.0f} {action}，"
            f"定 {stop_pts} 點止蝕（{stop:,.0f}），"
            f"{t1_pts} 點食糊（{target1:,.0f}）"
            f"｜細期 {sizing.mini_contracts} 張"
            f"{'（倉位已調減）' if sizing.adjusted else ''}"
        )
