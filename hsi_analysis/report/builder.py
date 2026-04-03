"""
ReportBuilder: orchestrates all analysis modules → DailyReport.
This is the central coordinator — it holds no analysis logic itself.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import List, Optional

import pandas as pd

from ..config.settings import Settings
from ..data.fetcher import MarketDataFetcher
from ..data.models import (
    ConfirmationChecklist,
    DailyReport,
    FuturesSnapshot,
    MarketStrength,
    OIRecord,
    SupportResistanceZone,
    TechnicalSignals,
)
from ..analysis.indicators import build_technical_signals
from ..analysis.structure import (
    build_sr_zones,
    detect_swing_points,
    identify_round_numbers,
)
from ..analysis.fibonacci import find_key_fibs
from ..analysis.framework import (
    assess_basis_signal,
    compute_basis,
    compute_framework_bands,
    compute_monthly_mid,
    get_ao_prices,
)
from ..analysis.elliott import label_elliott_waves, get_wave_context_summary
from ..risk.manager import RiskManager
from ..risk.tracker import RiskTracker
from ..scenarios.generator import ScenarioGenerator
from ..storage.repository import OIRepository, SignalsRepository, SnapshotRepository

logger = logging.getLogger(__name__)


class ReportBuilder:
    def __init__(
        self,
        settings: Settings,
        fetcher: MarketDataFetcher,
        risk_manager: RiskManager,
        risk_tracker: RiskTracker,
        scenario_gen: ScenarioGenerator,
        snapshot_repo: SnapshotRepository,
        oi_repo: OIRepository,
        signals_repo: SignalsRepository,
    ):
        self.settings = settings
        self.fetcher = fetcher
        self.rm = risk_manager
        self.tracker = risk_tracker
        self.scenario_gen = scenario_gen
        self.snap_repo = snapshot_repo
        self.oi_repo = oi_repo
        self.sig_repo = signals_repo

    def build(self, report_date: Optional[date] = None) -> DailyReport:
        """
        Main orchestration:
        1. Fetch price data (spot + futures + related)
        2. Compute monthly mid and framework bands
        3. Extract AO prices from today's open
        4. Fetch OI record (T+1, may be prior day)
        5. Build indicators for 1d / 4h / 1h
        6. Detect swing points → S/R zones + Fibonacci levels
        7. Elliott Wave suggestion
        8. Assess external factors
        9. Generate 3 scenarios
        10. Assemble DailyReport and persist
        """
        if report_date is None:
            report_date = date.today()

        data_notes: List[str] = []
        tc = self.settings.technical
        fu = self.settings.futures

        # ── 1. Fetch price data ─────────────────────────────────────────
        end = report_date
        start_daily = end - timedelta(days=200)
        start_1h = end - timedelta(days=59)

        df_spot = self._safe_fetch(
            lambda: self.fetcher.fetch_hsi_spot(start_daily, end),
            "^HSI spot",
            data_notes,
        )
        df_big = self._safe_fetch(
            lambda: self.fetcher.fetch_futures_big(start_daily, end),
            "HSI big futures",
            data_notes,
        )
        df_mini = self._safe_fetch(
            lambda: self.fetcher.fetch_futures_mini(start_daily, end),
            "HSI mini futures",
            data_notes,
        )
        related = self._safe_fetch(
            lambda: self.fetcher.fetch_related_indices(start_daily, end),
            "related indices",
            data_notes,
            default={},
        )

        # Use futures for analysis; fall back to spot
        df_main = df_big if (df_big is not None and not df_big.empty) else df_spot
        if df_main is None or df_main.empty:
            raise RuntimeError("No price data available — cannot build report")

        # ── 2. Framework: monthly mid + bands ──────────────────────────
        monthly_mid = compute_monthly_mid(df_main, fu.monthly_mid_lookback_days)
        sig_1d_temp = build_technical_signals(
            df_main, "1d", report_date,
            tc.macd_fast, tc.macd_slow, tc.macd_signal,
            tc.rsi_period, tc.kdj_period, tc.atr_period,
        )
        atr = sig_1d_temp.atr or max(1.0, (df_main["high"].iloc[-1] - df_main["low"].iloc[-1]))
        lower_band, upper_band = compute_framework_bands(
            monthly_mid, atr, tc.framework_band_atr_multiplier
        )

        # ── 3. AO prices ────────────────────────────────────────────────
        ao_big, ao_mini = get_ao_prices(df_big, df_mini, report_date)
        if ao_big == 0.0 and not df_main.empty:
            ao_big = float(df_main["open"].iloc[-1])
            ao_mini = ao_big
            data_notes.append("AO價格使用日線開盤位替代（yfinance無日內數據）")

        # ── 4. Day high / low / settlement ─────────────────────────────
        last = df_main.iloc[-1]
        dh = float(last["high"])
        dl = float(last["low"])
        settlement = float(last["close"])
        spot_close = float(df_spot["close"].iloc[-1]) if (df_spot is not None and not df_spot.empty) else settlement
        basis = compute_basis(settlement, spot_close)

        # ── 5. Related indices ─────────────────────────────────────────
        vix = 0.0
        a50_chg = 0.0
        hstech_chg = 0.0
        if related:
            vix = self._last_close(related.get("vix"))
            a50_chg = self._pct_change(related.get("a50"))
            hstech_chg = self._pct_change(related.get("hstech"))

        snapshot = FuturesSnapshot(
            trade_date=report_date,
            ao_big=ao_big,
            ao_mini=ao_mini,
            dh=dh,
            dl=dl,
            settlement=settlement,
            monthly_mid=monthly_mid,
            upper_band=upper_band,
            lower_band=lower_band,
            basis=basis,
            spot_close=spot_close,
            vix=vix,
            a50_change_pct=a50_chg,
            hstech_change_pct=hstech_chg,
            volume=float(last.get("volume", 0)),
        )

        # ── 6. OI record (T+1 — may be prior day) ──────────────────────
        oi_date = report_date - timedelta(days=1)
        oi_record = self.fetcher.fetch_hkex_oi(oi_date)
        if oi_record is None:
            oi_record = OIRecord(
                trade_date=oi_date,
                net_long=0, net_short=0, net_position=0, oi_change=0,
                interpretation="HKEX OI數據暫未獲取",
            )
        else:
            data_notes.append(f"期指淨倉數據為前交易日（{oi_date}）—— HKEX T+1發佈")
        self.oi_repo.save(oi_record)

        # ── 7. Technical indicators (1d / 4h / 1h) ────────────────────
        sig_1d = build_technical_signals(
            df_main, "1d", report_date,
            tc.macd_fast, tc.macd_slow, tc.macd_signal,
            tc.rsi_period, tc.kdj_period, tc.atr_period,
        )
        df_1h = self._safe_fetch(
            lambda: self.fetcher.fetch_1h_data(fu.hsi_ticker),
            "1h data",
            data_notes,
        )
        df_4h = self.fetcher.resample_to_4h(df_1h) if df_1h is not None else None
        sig_4h = build_technical_signals(
            df_4h, "4h", report_date,
            tc.macd_fast, tc.macd_slow, tc.macd_signal,
            tc.rsi_period, tc.kdj_period, tc.atr_period,
        ) if (df_4h is not None and not df_4h.empty) else self._empty_signals("4h", report_date)
        sig_1h = build_technical_signals(
            df_1h, "1h", report_date,
            tc.macd_fast, tc.macd_slow, tc.macd_signal,
            tc.rsi_period, tc.kdj_period, tc.atr_period,
        ) if (df_1h is not None and not df_1h.empty) else self._empty_signals("1h", report_date)

        for sig in (sig_1d, sig_4h, sig_1h):
            self.sig_repo.save(sig)

        # ── 8. S/R zones ───────────────────────────────────────────────
        sh_idx, sl_idx = detect_swing_points(df_main, order=tc.swing_order)
        struct_zones = build_sr_zones(df_main, sh_idx, sl_idx, tc.sr_cluster_tolerance)
        fib_zones = find_key_fibs(df_main, lookback_bars=60, current_price=settlement)
        round_zones = identify_round_numbers(settlement, step=200)
        # Add framework bands as S/R zones
        band_zones: List[SupportResistanceZone] = [
            SupportResistanceZone(lower_band, "support", 4, "framework"),
            SupportResistanceZone(monthly_mid, "support" if settlement > monthly_mid else "resistance", 3, "framework"),
            SupportResistanceZone(upper_band, "resistance", 4, "framework"),
        ]
        # Merge and sort by price
        all_zones = struct_zones + fib_zones + round_zones + band_zones
        all_zones.sort(key=lambda z: z.price)
        # Keep top 10 by strength near current price
        all_zones.sort(key=lambda z: (abs(z.price - settlement), -z.strength))
        sr_zones = all_zones[:12]
        sr_zones.sort(key=lambda z: z.price)

        # ── 9. Elliott Wave ────────────────────────────────────────────
        waves = label_elliott_waves(df_main, order=tc.swing_order)
        wave_context = get_wave_context_summary(waves, settlement)

        # ── 10. External factors ───────────────────────────────────────
        external_factors = self._assess_external_factors(
            vix, a50_chg, hstech_chg, basis, atr, sig_1d
        )

        # ── 11. Market strength ────────────────────────────────────────
        market_strength = self._assess_market_strength(
            sig_1d, oi_record, basis, atr, vix
        )
        confirmation = self._build_confirmation(sig_1d, sig_4h, sr_zones, settlement)

        # ── 12. Risk state ─────────────────────────────────────────────
        risk_state = self.tracker.get_risk_state_summary()
        risk_coeff = self.tracker.get_current_risk_coefficient()

        # ── 13. Scenarios ──────────────────────────────────────────────
        scenarios = self.scenario_gen.generate(
            snapshot, sig_1d, sig_4h, sr_zones,
            risk_coefficient=risk_coeff,
        )

        # ── 14. Persist snapshot ───────────────────────────────────────
        self.snap_repo.save(snapshot)

        return DailyReport(
            report_date=report_date,
            snapshot=snapshot,
            oi_record=oi_record,
            signals_1d=sig_1d,
            signals_4h=sig_4h,
            signals_1h=sig_1h,
            sr_zones=sr_zones,
            scenarios=scenarios,
            external_factors=external_factors,
            market_strength=market_strength,
            confirmation=confirmation,
            risk_state=risk_state,
            wave_context=wave_context,
            data_notes=data_notes,
        )

    # ──────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────

    def _safe_fetch(self, fn, label, notes, default=None):
        try:
            return fn()
        except Exception as e:
            logger.warning(f"Failed to fetch {label}: {e}")
            notes.append(f"⚠️ {label} 數據獲取失敗：{e}")
            return default

    def _last_close(self, df) -> float:
        if df is None or (hasattr(df, "empty") and df.empty):
            return 0.0
        try:
            return float(df["close"].iloc[-1])
        except Exception:
            return 0.0

    def _pct_change(self, df) -> float:
        if df is None or (hasattr(df, "empty") and df.empty) or len(df) < 2:
            return 0.0
        try:
            prev = float(df["close"].iloc[-2])
            last = float(df["close"].iloc[-1])
            return round((last - prev) / prev * 100, 2) if prev else 0.0
        except Exception:
            return 0.0

    def _empty_signals(self, timeframe: str, report_date: date) -> TechnicalSignals:
        from ..analysis.indicators import _empty_signals
        return _empty_signals(report_date, timeframe)

    def _assess_external_factors(
        self, vix, a50_chg, hstech_chg, basis, atr, sig_1d
    ) -> List[str]:
        factors = []

        if vix > 30:
            factors.append(f"VIX高企於 {vix:.1f}，市場恐慌情緒濃厚，波動率大，注意風險控制")
        elif vix > 20:
            factors.append(f"VIX {vix:.1f}，市場存在一定不確定性，操作宜謹慎")
        elif vix > 0:
            factors.append(f"VIX {vix:.1f}，市場情緒相對平穩")

        if a50_chg > 1.5:
            factors.append(f"A50期指升 {a50_chg:.1f}%，A股偏強，對港股有支撐")
        elif a50_chg < -1.5:
            factors.append(f"A50期指跌 {abs(a50_chg):.1f}%，A股偏弱，拖累港股情緒")
        elif a50_chg != 0:
            factors.append(f"A50期指 {a50_chg:+.1f}%，A股走勢中性")

        if hstech_chg > 2:
            factors.append(f"恒科指數升 {hstech_chg:.1f}%，科技股強勢，帶動大市")
        elif hstech_chg < -2:
            factors.append(f"恒科指數跌 {abs(hstech_chg):.1f}%，科技股受壓，留意大市方向")

        basis_str = assess_basis_signal(basis, atr)
        factors.append(f"期現基差 {basis:+.0f}點，{basis_str}")

        if sig_1d.rsi > 70:
            factors.append(f"日線RSI {sig_1d.rsi:.0f} 超買，短期或有回吐壓力")
        elif sig_1d.rsi < 30:
            factors.append(f"日線RSI {sig_1d.rsi:.0f} 超賣，短期存在反彈空間")

        if not factors:
            factors.append("外圍因素暫無重大異動，靜待市場自身方向確認")

        return factors

    def _assess_market_strength(
        self, sig_1d, oi_record, basis, atr, vix
    ) -> MarketStrength:
        # Volume signal
        vol_signal = "正常"  # simplified; would need historical average

        # OI signal
        if oi_record.oi_change > 5000:
            oi_signal = "增倉"
        elif oi_record.oi_change < -5000:
            oi_signal = "減倉"
        else:
            oi_signal = "持平"

        # Basis signal
        if abs(basis) > atr * 0.3:
            basis_signal = "升水" if basis > 0 else "貼水"
        else:
            basis_signal = "正常"

        # Volatility
        if vix > 25:
            vol_str = "高"
        elif vix > 15:
            vol_str = "中"
        else:
            vol_str = "低"

        # Overall
        bull_points = sum([
            sig_1d.trend == "bullish",
            sig_1d.macd_hist > 0,
            sig_1d.rsi > 50,
            oi_signal == "增倉",
        ])
        if bull_points >= 3:
            overall = "強"
        elif bull_points >= 2:
            overall = "中"
        else:
            overall = "弱"

        return MarketStrength(
            overall=overall,
            volume_signal=vol_signal,
            oi_signal=oi_signal,
            basis_signal=basis_signal,
            volatility_signal=vol_str,
        )

    def _build_confirmation(
        self, sig_1d, sig_4h, sr_zones, current_price
    ) -> ConfirmationChecklist:
        trend_aligned = sig_1d.trend == sig_4h.trend and sig_1d.trend != "ranging"
        # Key level: price within 0.5% of any high-strength zone
        near_key = any(
            abs(z.price - current_price) / current_price < 0.005 and z.strength >= 3
            for z in sr_zones
        )
        rr_ok = True  # checked per-scenario in generator
        return ConfirmationChecklist(
            trend_aligned=trend_aligned,
            key_level_broken=near_key,
            volume_confirms=False,   # would need intraday volume comparison
            timeframe_resonance=trend_aligned and (sig_1d.trend != "ranging"),
            rr_acceptable=rr_ok,
        )
