"""
Build exactly 3 daily scenarios: 偏多 (bullish) / 中性 (neutral) / 偏空 (bearish).
Each scenario includes a concrete TradeSetup with entry, stop, and targets.
"""
from __future__ import annotations

from typing import List, Optional

from ..data.models import (
    FuturesSnapshot,
    Scenario,
    SupportResistanceZone,
    TechnicalSignals,
    TradeSetup,
)
from ..risk.manager import RiskManager, PositionSizing
from ..config.settings import Settings


class ScenarioGenerator:
    def __init__(self, settings: Settings, risk_manager: RiskManager):
        self.settings = settings
        self.rm = risk_manager

    def generate(
        self,
        snapshot: FuturesSnapshot,
        signals_1d: TechnicalSignals,
        signals_4h: TechnicalSignals,
        sr_zones: List[SupportResistanceZone],
        risk_coefficient: float = 1.0,
        account_size: Optional[float] = None,
    ) -> List[Scenario]:
        """
        Returns exactly 3 Scenario objects ordered by estimated probability.
        Probability is qualitative based on signal alignment — NOT statistical.
        Always verify with live market context before trading.
        """
        if account_size is None:
            account_size = self.settings.risk.default_account_size

        current = snapshot.settlement or snapshot.ao_big
        atr = signals_1d.atr or (snapshot.dh - snapshot.dl)
        trend_1d = signals_1d.trend
        trend_4h = signals_4h.trend

        supports = sorted(
            [z for z in sr_zones if z.zone_type == "support"],
            key=lambda z: abs(z.price - current),
        )
        resistances = sorted(
            [z for z in sr_zones if z.zone_type == "resistance"],
            key=lambda z: abs(z.price - current),
        )

        nearest_support = supports[0].price if supports else current - atr * 1.5
        nearest_resist = resistances[0].price if resistances else current + atr * 1.5
        second_support = supports[1].price if len(supports) > 1 else nearest_support - atr
        second_resist = resistances[1].price if len(resistances) > 1 else nearest_resist + atr

        # Build the three scenarios
        bullish = self._build_bullish(
            current, nearest_support, nearest_resist, second_resist,
            atr, trend_1d, trend_4h, signals_1d, risk_coefficient,
            account_size,
        )
        neutral = self._build_neutral(
            current, nearest_support, nearest_resist, atr,
            trend_1d, risk_coefficient, account_size,
        )
        bearish = self._build_bearish(
            current, nearest_support, nearest_resist, second_support,
            atr, trend_1d, trend_4h, signals_1d, risk_coefficient,
            account_size,
        )

        # Order by trend alignment
        if trend_1d == "bullish" and trend_4h in ("bullish", "ranging"):
            order = [bullish, neutral, bearish]
        elif trend_1d == "bearish" and trend_4h in ("bearish", "ranging"):
            order = [bearish, neutral, bullish]
        else:
            order = [neutral, bullish, bearish]

        for i, sc in enumerate(order, start=1):
            sc.rank = i

        return order

    # ------------------------------------------------------------------

    def _build_bullish(
        self,
        current, support, resist, resist2,
        atr, trend_1d, trend_4h, signals, risk_coeff, account,
    ) -> Scenario:
        entry = round(support + atr * 0.2, 0)
        stop = self.rm.calculate_stop_loss(entry, "long", atr, nearest_sr_level=support)
        t1 = resist
        t2 = resist2
        sizing = self.rm.calculate_position_size(account, entry, stop, risk_coeff)
        _, rr = self.rm.validate_risk_reward(entry, stop, t1)
        stop_pts = int(abs(entry - stop))
        t1_pts = int(abs(t1 - entry))

        trend_note = "日線MACD金叉" if signals.macd_hist > 0 else "MACD待確認"
        return Scenario(
            rank=1,
            label="偏多",
            trigger_condition=(
                f"大市守穩 {support:,.0f} 支撐位，{trend_note}，"
                f"RSI {signals.rsi:.0f} 未超買，"
                f"突破 {resist:,.0f} 阻力後確認"
            ),
            price_target=t2,
            key_level=support,
            trade_setup=TradeSetup(
                direction="long",
                entry_price=entry,
                stop_loss=stop,
                target_1=t1,
                target_2=t2,
                risk_reward=rr,
                stop_points=stop_pts,
                target_points=t1_pts,
                position_size_big=sizing.big_contracts,
                position_size_mini=sizing.mini_contracts,
                rationale=f"守支撐反彈，目標{resist:,.0f}–{resist2:,.0f}",
            ),
            probability_note="日線及4小時趨勢一致偏多時機率最高",
        )

    def _build_neutral(
        self,
        current, support, resist, atr, trend_1d, risk_coeff, account,
    ) -> Scenario:
        # Fade at extremes within the framework band
        mid = round((support + resist) / 2, 0)
        entry_long = support + atr * 0.3
        entry_short = resist - atr * 0.3
        stop_long = self.rm.calculate_stop_loss(entry_long, "long", atr)
        _, rr_long = self.rm.validate_risk_reward(entry_long, stop_long, mid)
        sizing = self.rm.calculate_position_size(account, entry_long, stop_long, risk_coeff)
        stop_pts = int(abs(entry_long - stop_long))
        t_pts = int(abs(mid - entry_long))

        return Scenario(
            rank=2,
            label="中性",
            trigger_condition=(
                f"大市在 {support:,.0f}–{resist:,.0f} 區間橫行，"
                f"低吸 {entry_long:,.0f} 附近，高沽 {entry_short:,.0f} 附近，"
                f"中位 {mid:,.0f} 為目標"
            ),
            price_target=mid,
            key_level=mid,
            trade_setup=TradeSetup(
                direction="long",
                entry_price=entry_long,
                stop_loss=stop_long,
                target_1=mid,
                target_2=resist,
                risk_reward=rr_long,
                stop_points=stop_pts,
                target_points=t_pts,
                position_size_big=sizing.big_contracts,
                position_size_mini=sizing.mini_contracts,
                rationale=f"區間操作：低吸{entry_long:,.0f}，目標中位{mid:,.0f}",
            ),
            probability_note="外圍方向不明、成交縮量時適用",
        )

    def _build_bearish(
        self,
        current, support, resist, support2,
        atr, trend_1d, trend_4h, signals, risk_coeff, account,
    ) -> Scenario:
        entry = round(resist - atr * 0.2, 0)
        stop = self.rm.calculate_stop_loss(entry, "short", atr, nearest_sr_level=resist)
        t1 = support
        t2 = support2
        sizing = self.rm.calculate_position_size(account, entry, stop, risk_coeff)
        _, rr = self.rm.validate_risk_reward(entry, stop, t1)
        stop_pts = int(abs(entry - stop))
        t1_pts = int(abs(t1 - entry))

        trend_note = "MACD死叉" if signals.macd_hist < 0 else "MACD偏弱"
        return Scenario(
            rank=3,
            label="偏空",
            trigger_condition=(
                f"大市失守 {support:,.0f} 支撐位，{trend_note}，"
                f"RSI {signals.rsi:.0f} 偏弱，"
                f"跌穿 {support:,.0f} 確認後沽空"
            ),
            price_target=t2,
            key_level=resist,
            trade_setup=TradeSetup(
                direction="short",
                entry_price=entry,
                stop_loss=stop,
                target_1=t1,
                target_2=t2,
                risk_reward=rr,
                stop_points=stop_pts,
                target_points=t1_pts,
                position_size_big=sizing.big_contracts,
                position_size_mini=sizing.mini_contracts,
                rationale=f"失守支撐轉沽，目標{support:,.0f}–{support2:,.0f}",
            ),
            probability_note="日線趨勢偏空且外圍利淡時機率提升",
        )
