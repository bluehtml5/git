"""
CLI entry point for the HSI Futures Analysis System.

Usage:
  python -m hsi_analysis report
  python -m hsi_analysis backtest --start 2023-01-01
  python -m hsi_analysis schedule
  python -m hsi_analysis init-db
  python -m hsi_analysis fetch --days 90
"""
from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from typing import Optional

import click

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _build_components(config_path: str):
    """Construct and wire all system components."""
    from .config.settings import load_settings
    from .storage.database import DatabaseManager
    from .storage.repository import (
        OIRepository,
        SignalsRepository,
        SnapshotRepository,
        TradeRepository,
    )
    from .data.cache import PriceCache
    from .data.fetcher import MarketDataFetcher
    from .risk.manager import RiskManager
    from .risk.tracker import RiskTracker
    from .scenarios.generator import ScenarioGenerator
    from .report.builder import ReportBuilder
    from .report.formatter import ReportFormatter

    settings = load_settings(config_path)

    db = DatabaseManager(settings.general.db_path)
    db.initialise()

    cache = PriceCache(db)
    snap_repo = SnapshotRepository(db)
    oi_repo = OIRepository(db)
    sig_repo = SignalsRepository(db)
    trade_repo = TradeRepository(db)

    fetcher = MarketDataFetcher(cache=cache, use_cache=True)
    risk_mgr = RiskManager(settings.risk, settings.futures)
    risk_tracker = RiskTracker(trade_repo, settings.risk)
    scenario_gen = ScenarioGenerator(settings, risk_mgr)

    builder = ReportBuilder(
        settings=settings,
        fetcher=fetcher,
        risk_manager=risk_mgr,
        risk_tracker=risk_tracker,
        scenario_gen=scenario_gen,
        snapshot_repo=snap_repo,
        oi_repo=oi_repo,
        signals_repo=sig_repo,
    )
    formatter = ReportFormatter()

    return settings, builder, formatter, fetcher, trade_repo


# ──────────────────────────────────────────────────────────────────────────────

@click.group()
@click.option(
    "--config",
    default="config.yaml",
    show_default=True,
    help="Path to config.yaml",
)
@click.pass_context
def cli(ctx, config):
    """🇭🇰 HSI Futures Daily Analysis System（恒生指數期貨分析系統）"""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


@cli.command("report")
@click.option("--date", "report_date", default=None, help="Date YYYY-MM-DD (default: today)")
@click.option("--save/--no-save", default=True, show_default=True, help="Write markdown file")
@click.option("--print/--no-print", "print_terminal", default=True, show_default=True, help="Print to terminal")
@click.pass_context
def cmd_report(ctx, report_date: Optional[str], save: bool, print_terminal: bool):
    """Generate daily analysis report."""
    settings, builder, formatter, _, _ = _build_components(ctx.obj["config"])

    target_date = date.fromisoformat(report_date) if report_date else date.today()
    click.echo(f"生成 {target_date} 分析報告…")

    report = builder.build(report_date=target_date)

    if print_terminal:
        formatter.print_terminal(report)

    if save:
        filepath = formatter.save_to_file(report, settings.general.report_output_dir)
        click.echo(f"✅ 報告已儲存: {filepath}")


@cli.command("backtest")
@click.option("--start", required=True, help="Start date YYYY-MM-DD")
@click.option("--end", default=None, help="End date YYYY-MM-DD (default: today)")
@click.option(
    "--strategy",
    default="framework",
    show_default=True,
    help="Strategy name (framework)",
)
@click.option(
    "--capital",
    default=1_000_000,
    show_default=True,
    type=float,
    help="Initial capital in HKD",
)
@click.option(
    "--contract",
    default="mini",
    show_default=True,
    type=click.Choice(["big", "mini"]),
    help="Contract type",
)
@click.pass_context
def cmd_backtest(ctx, start, end, strategy, capital, contract):
    """Run historical backtest and print performance statistics."""
    from .backtest.engine import BacktestEngine
    from .data.fetcher import MarketDataFetcher
    from .config.settings import load_settings

    settings = load_settings(ctx.obj["config"])
    from .storage.database import DatabaseManager
    from .data.cache import PriceCache

    db = DatabaseManager(settings.general.db_path)
    db.initialise()
    cache = PriceCache(db)
    fetcher = MarketDataFetcher(cache=cache)

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end) if end else date.today()

    click.echo(f"獲取 {start_date} 至 {end_date} 歷史數據…")
    df = fetcher.fetch_hsi_spot(start_date, end_date)

    if df is None or df.empty:
        click.echo("❌ 無法獲取歷史數據", err=True)
        sys.exit(1)

    click.echo(f"回測中… 策略: {strategy}，合約: {contract}，資本: HK${capital:,.0f}")
    engine = BacktestEngine.from_name(
        strategy, df,
        initial_capital=capital,
        contract_type=contract,
    )
    stats = engine.run(start=start_date, end=end_date)
    click.echo(stats.summary_text())


@cli.command("schedule")
@click.pass_context
def cmd_schedule(ctx):
    """Start the scheduler daemon (pre-market 08:30 + post-market 16:30 HKT)."""
    settings, builder, formatter, _, _ = _build_components(ctx.obj["config"])
    from .scheduler.jobs import start_scheduler
    click.echo("啟動排程系統（Ctrl+C 停止）…")
    start_scheduler(builder, formatter)


@cli.command("init-db")
@click.pass_context
def cmd_init_db(ctx):
    """Initialize the SQLite database schema."""
    from .config.settings import load_settings
    from .storage.database import DatabaseManager

    settings = load_settings(ctx.obj["config"])
    db = DatabaseManager(settings.general.db_path)
    db.initialise()
    click.echo(f"✅ 資料庫已初始化: {settings.general.db_path}")


@cli.command("fetch")
@click.option("--days", default=90, show_default=True, type=int, help="Historical days to prefetch")
@click.pass_context
def cmd_fetch(ctx, days):
    """Pre-fetch and cache historical price data."""
    from .config.settings import load_settings
    from .storage.database import DatabaseManager
    from .data.cache import PriceCache
    from .data.fetcher import MarketDataFetcher

    settings = load_settings(ctx.obj["config"])
    db = DatabaseManager(settings.general.db_path)
    db.initialise()
    cache = PriceCache(db)
    fetcher = MarketDataFetcher(cache=cache)

    end = date.today()
    start = end - timedelta(days=days)
    fu = settings.futures

    tickers = [
        (fu.hsi_ticker, "HSI spot"),
        (fu.hsi_futures_front, "HSI big futures"),
        (fu.mini_futures_front, "HSI mini futures"),
        (fu.a50_ticker, "A50"),
        (fu.hstech_ticker, "HSTECH"),
        (fu.vix_ticker, "VIX"),
    ]

    for ticker, label in tickers:
        click.echo(f"  獲取 {label} ({ticker})…", nl=False)
        try:
            df = fetcher._yf_download(ticker, start, end)
            bars = len(df) if df is not None else 0
            click.echo(f" {bars} 條日線數據")
        except Exception as e:
            click.echo(f" ❌ 失敗: {e}")

    click.echo(f"✅ 歷史數據預載完成（最近 {days} 天）")


@cli.command("record-trade")
@click.option("--direction", required=True, type=click.Choice(["long", "short"]))
@click.option("--entry", required=True, type=float)
@click.option("--exit", "exit_price", required=True, type=float)
@click.option("--contract", default="mini", type=click.Choice(["big", "mini"]))
@click.option("--contracts", default=1, type=int)
@click.option("--notes", default="", help="Optional trade notes")
@click.pass_context
def cmd_record_trade(ctx, direction, entry, exit_price, contract, contracts, notes):
    """Record a completed trade result for risk tracking."""
    from .config.settings import load_settings
    from .storage.database import DatabaseManager
    from .storage.repository import TradeRepository

    settings = load_settings(ctx.obj["config"])
    db = DatabaseManager(settings.general.db_path)
    db.initialise()
    repo = TradeRepository(db)

    pnl_pts = int(exit_price - entry) if direction == "long" else int(entry - exit_price)
    repo.record_result(
        trade_date=date.today(),
        direction=direction,
        entry_price=entry,
        exit_price=exit_price,
        pnl_points=pnl_pts,
        contract_type=contract,
        contracts=contracts,
        notes=notes,
    )
    multiplier = 50 if contract == "big" else 10
    pnl_hkd = pnl_pts * multiplier * contracts
    result = "盈利" if pnl_pts > 0 else "虧損"
    click.echo(
        f"✅ 交易記錄已儲存: {result} {abs(pnl_pts)} 點 "
        f"(HK${pnl_hkd:+,.0f})"
    )


def main():
    cli()


if __name__ == "__main__":
    main()
