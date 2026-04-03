"""Tests for risk management calculations."""
import pytest
from hsi_analysis.risk.manager import RiskManager
from hsi_analysis.config.settings import RiskConfig, FuturesConfig


def make_rm():
    rc = RiskConfig(
        default_account_size=1_000_000,
        max_risk_per_trade_pct=1.0,
        max_daily_loss_pct=3.0,
        consecutive_loss_limit=3,
        risk_coefficient_reduction=0.5,
        min_risk_reward=2.0,
    )
    fc = FuturesConfig(
        hsi_ticker="^HSI",
        hsi_futures_front="HSI=F",
        mini_futures_front="MHI=F",
        a50_ticker="XU050=F",
        hstech_ticker="^HSTECH",
        vix_ticker="^VIX",
        big_lot_multiplier=50,
        mini_lot_multiplier=10,
        tick_size=1,
        monthly_mid_lookback_days=22,
    )
    return RiskManager(rc, fc)


def test_position_sizing_mini_within_risk():
    rm = make_rm()
    # 200-point stop on mini: 200 * 10 = 2000 HKD per contract
    # 1% of 1M = 10,000 HKD → should allow 5 mini contracts
    sizing = rm.calculate_position_size(
        account_size=1_000_000,
        entry_price=20000,
        stop_loss_price=19800,
        risk_coefficient=1.0,
        prefer_mini=True,
    )
    assert sizing.mini_contracts == 5
    assert sizing.risk_amount_hkd <= 10_500  # small tolerance


def test_position_sizing_reduced_by_coefficient():
    rm = make_rm()
    full = rm.calculate_position_size(1_000_000, 20000, 19800, 1.0)
    halved = rm.calculate_position_size(1_000_000, 20000, 19800, 0.5)
    assert halved.mini_contracts <= full.mini_contracts
    assert halved.adjusted is True


def test_stop_loss_long_below_entry():
    rm = make_rm()
    stop = rm.calculate_stop_loss(20000, "long", atr=300)
    assert stop < 20000


def test_stop_loss_short_above_entry():
    rm = make_rm()
    stop = rm.calculate_stop_loss(20000, "short", atr=300)
    assert stop > 20000


def test_validate_rr_acceptable():
    rm = make_rm()
    ok, rr = rm.validate_risk_reward(20000, 19800, 20600)
    assert ok is True
    assert rr == 3.0


def test_validate_rr_unacceptable():
    rm = make_rm()
    ok, rr = rm.validate_risk_reward(20000, 19800, 20100)
    assert ok is False
    assert rr == 0.5


def test_calculate_target_long():
    rm = make_rm()
    t = rm.calculate_target(20000, 19800, "long", rr_ratio=2.0)
    assert t == 20400  # 200 pts risk × 2 = 400 pts gain


def test_zero_stop_returns_zero_sizing():
    rm = make_rm()
    sizing = rm.calculate_position_size(1_000_000, 20000, 20000)
    assert sizing.big_contracts == 0
    assert sizing.mini_contracts == 0
