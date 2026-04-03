"""Load and expose typed configuration from config.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

import yaml


@dataclass
class GeneralConfig:
    timezone: str
    report_output_dir: str
    db_path: str
    cache_dir: str


@dataclass
class FuturesConfig:
    hsi_ticker: str
    hsi_futures_front: str
    mini_futures_front: str
    a50_ticker: str
    hstech_ticker: str
    vix_ticker: str
    big_lot_multiplier: int
    mini_lot_multiplier: int
    tick_size: int
    monthly_mid_lookback_days: int


@dataclass
class RiskConfig:
    default_account_size: float
    max_risk_per_trade_pct: float
    max_daily_loss_pct: float
    consecutive_loss_limit: int
    risk_coefficient_reduction: float
    min_risk_reward: float


@dataclass
class TechnicalConfig:
    fibonacci_levels: List[float]
    framework_band_atr_multiplier: float
    overshoot_extension: float
    macd_fast: int
    macd_slow: int
    macd_signal: int
    rsi_period: int
    kdj_period: int
    atr_period: int
    swing_order: int
    sr_cluster_tolerance: float


@dataclass
class SchedulerConfig:
    pre_market_time: str
    post_market_time: str


@dataclass
class Settings:
    general: GeneralConfig
    futures: FuturesConfig
    risk: RiskConfig
    technical: TechnicalConfig
    scheduler: SchedulerConfig


_settings: Optional[Settings] = None


def load_settings(config_path: str = "config.yaml") -> Settings:
    """Load config.yaml and return a typed Settings instance."""
    global _settings
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    g = raw["general"]
    fu = raw["futures"]
    ri = raw["risk"]
    te = raw["technical"]
    sc = raw["scheduler"]

    _settings = Settings(
        general=GeneralConfig(
            timezone=g["timezone"],
            report_output_dir=g["report_output_dir"],
            db_path=g["db_path"],
            cache_dir=g["cache_dir"],
        ),
        futures=FuturesConfig(
            hsi_ticker=fu["hsi_ticker"],
            hsi_futures_front=fu["hsi_futures_front"],
            mini_futures_front=fu["mini_futures_front"],
            a50_ticker=fu["a50_ticker"],
            hstech_ticker=fu["hstech_ticker"],
            vix_ticker=fu["vix_ticker"],
            big_lot_multiplier=fu["big_lot_multiplier"],
            mini_lot_multiplier=fu["mini_lot_multiplier"],
            tick_size=fu["tick_size"],
            monthly_mid_lookback_days=fu["monthly_mid_lookback_days"],
        ),
        risk=RiskConfig(
            default_account_size=ri["default_account_size"],
            max_risk_per_trade_pct=ri["max_risk_per_trade_pct"],
            max_daily_loss_pct=ri["max_daily_loss_pct"],
            consecutive_loss_limit=ri["consecutive_loss_limit"],
            risk_coefficient_reduction=ri["risk_coefficient_reduction"],
            min_risk_reward=ri["min_risk_reward"],
        ),
        technical=TechnicalConfig(
            fibonacci_levels=te["fibonacci_levels"],
            framework_band_atr_multiplier=te["framework_band_atr_multiplier"],
            overshoot_extension=te["overshoot_extension"],
            macd_fast=te["macd_fast"],
            macd_slow=te["macd_slow"],
            macd_signal=te["macd_signal"],
            rsi_period=te["rsi_period"],
            kdj_period=te["kdj_period"],
            atr_period=te["atr_period"],
            swing_order=te["swing_order"],
            sr_cluster_tolerance=te["sr_cluster_tolerance"],
        ),
        scheduler=SchedulerConfig(
            pre_market_time=sc["pre_market_time"],
            post_market_time=sc["post_market_time"],
        ),
    )
    return _settings


def get_settings() -> Settings:
    """Return the singleton Settings instance, loading from default path if needed."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
