"""Core dataclasses used throughout the HSI analysis system."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional


@dataclass
class PriceBar:
    """OHLCV bar for any timeframe."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    ticker: str
    timeframe: str  # "1d", "4h", "1h"


@dataclass
class FuturesSnapshot:
    """Complete daily snapshot for HSI futures."""
    trade_date: date
    ao_big: float           # 大期 AO opening price
    ao_mini: float          # 細期 AO opening price
    dh: float               # day high (日高)
    dl: float               # day low (日低)
    settlement: float       # settlement / close price
    monthly_mid: float      # M — monthly mid price
    upper_band: float       # 上軌
    lower_band: float       # 下軌
    basis: float            # 期現基差 (futures − spot)
    spot_close: float       # HSI spot index close
    vix: float = 0.0
    a50_change_pct: float = 0.0
    hstech_change_pct: float = 0.0
    volume: float = 0.0


@dataclass
class OIRecord:
    """Open interest / net position record from HKEX."""
    trade_date: date
    net_long: int           # dealer net long contracts
    net_short: int
    net_position: int       # net_long − net_short (positive = net long)
    oi_change: int          # change vs prior day
    interpretation: str     # 中文解讀


@dataclass
class TechnicalSignals:
    """Computed indicator values for a given date and timeframe."""
    trade_date: date
    timeframe: str          # "1d", "4h", "1h"
    macd_line: float
    macd_signal: float
    macd_hist: float
    rsi: float
    kdj_k: float
    kdj_d: float
    kdj_j: float
    atr: float
    structure: str          # "HH/HL" | "LH/LL" | "HH/LL" | "LH/HL"
    trend: str              # "bullish" | "bearish" | "ranging"
    close: float = 0.0


@dataclass
class SupportResistanceZone:
    """A single support or resistance price zone."""
    price: float
    zone_type: str          # "support" | "resistance"
    strength: int           # 1–5
    source: str             # "fibonacci" | "structure" | "framework" | "round_number"
    overshoot_target: Optional[float] = None


@dataclass
class TradeSetup:
    """Concrete trade setup with entry, stop, and targets."""
    direction: str          # "long" | "short"
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward: float
    stop_points: int
    target_points: int
    position_size_big: int
    position_size_mini: int
    rationale: str


@dataclass
class Scenario:
    """One of three daily scenarios (偏多 / 中性 / 偏空)."""
    rank: int               # 1 = most likely
    label: str              # "偏多" | "中性" | "偏空"
    trigger_condition: str  # Chinese description
    price_target: float
    key_level: float
    trade_setup: TradeSetup
    probability_note: str = ""


@dataclass
class MarketStrength:
    """Market strength assessment checklist."""
    overall: str            # "強" | "中" | "弱"
    volume_signal: str      # "放量" | "縮量" | "正常"
    oi_signal: str          # "增倉" | "減倉" | "持平"
    basis_signal: str       # "升水" | "貼水" | "正常"
    volatility_signal: str  # "高" | "中" | "低"


@dataclass
class ConfirmationChecklist:
    """Multi-factor confirmation before trade entry."""
    trend_aligned: bool
    key_level_broken: bool
    volume_confirms: bool
    timeframe_resonance: bool
    rr_acceptable: bool

    def score(self) -> int:
        return sum([
            self.trend_aligned,
            self.key_level_broken,
            self.volume_confirms,
            self.timeframe_resonance,
            self.rr_acceptable,
        ])


@dataclass
class DailyReport:
    """Top-level report container passed to the formatter."""
    report_date: date
    snapshot: FuturesSnapshot
    oi_record: OIRecord
    signals_1d: TechnicalSignals
    signals_4h: TechnicalSignals
    signals_1h: TechnicalSignals
    sr_zones: List[SupportResistanceZone]
    scenarios: List[Scenario]           # exactly 3
    external_factors: List[str]         # Chinese-language factor notes
    market_strength: MarketStrength
    confirmation: ConfirmationChecklist
    risk_state: dict                    # from RiskTracker
    wave_context: str = ""              # Elliott Wave summary (建議)
    data_notes: List[str] = field(default_factory=list)  # warnings (T+1 lag, roll etc.)
