"""APScheduler job definitions for pre/post-market daily runs."""
from __future__ import annotations

import logging
from datetime import date

import pytz

from ..config.settings import get_settings
from ..report.builder import ReportBuilder
from ..report.formatter import ReportFormatter

logger = logging.getLogger(__name__)
HK_TZ = pytz.timezone("Asia/Hong_Kong")


def _is_hk_trading_day(check_date: date) -> bool:
    """Return True if check_date is a weekday and not an HK public holiday."""
    try:
        import holidays
        hk_holidays = holidays.HongKong(years=check_date.year)
        is_holiday = check_date in hk_holidays
    except ImportError:
        is_holiday = False  # graceful fallback if library missing

    return check_date.weekday() < 5 and not is_holiday


def pre_market_job(builder: ReportBuilder, formatter: ReportFormatter) -> None:
    """
    Run at 08:30 HK time each weekday.
    Fetches prior-day closing prices (yfinance data for T-1 is available by ~8am).
    OI data is T+1 — always reflects the previous trading day.
    """
    today = date.today()
    if not _is_hk_trading_day(today):
        logger.info(f"Skipping pre-market job: {today} is not a HK trading day")
        return

    logger.info(f"Running pre-market analysis for {today}")
    try:
        report = builder.build(report_date=today)
        formatter.print_terminal(report)
        settings = get_settings()
        filepath = formatter.save_to_file(report, settings.general.report_output_dir)
        logger.info(f"Pre-market report saved: {filepath}")
    except Exception as e:
        logger.error(f"Pre-market job failed: {e}", exc_info=True)


def post_market_job(builder: ReportBuilder, formatter: ReportFormatter) -> None:
    """
    Run at 16:30 HK time each weekday (after 4:00pm main session close).
    Re-runs with final session prices to update DH/DL/settlement.
    NOTE: Evening T session (17:15-03:00) is not captured by this job.
    """
    today = date.today()
    if not _is_hk_trading_day(today):
        logger.info(f"Skipping post-market job: {today} is not a HK trading day")
        return

    logger.info(f"Running post-market update for {today}")
    try:
        report = builder.build(report_date=today)
        settings = get_settings()
        filepath = formatter.save_to_file(report, settings.general.report_output_dir)
        logger.info(f"Post-market report saved: {filepath}")
    except Exception as e:
        logger.error(f"Post-market job failed: {e}", exc_info=True)


def start_scheduler(builder: ReportBuilder, formatter: ReportFormatter) -> None:
    """Initialize APScheduler and block until interrupted."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        raise ImportError("apscheduler is required. Run: pip install apscheduler")

    settings = get_settings()
    pre_h, pre_m = [int(x) for x in settings.scheduler.pre_market_time.split(":")]
    post_h, post_m = [int(x) for x in settings.scheduler.post_market_time.split(":")]

    scheduler = BlockingScheduler(timezone=HK_TZ)

    scheduler.add_job(
        lambda: pre_market_job(builder, formatter),
        CronTrigger(day_of_week="mon-fri", hour=pre_h, minute=pre_m, timezone=HK_TZ),
        id="pre_market",
        name="Pre-market HSI analysis",
        misfire_grace_time=300,
    )
    scheduler.add_job(
        lambda: post_market_job(builder, formatter),
        CronTrigger(day_of_week="mon-fri", hour=post_h, minute=post_m, timezone=HK_TZ),
        id="post_market",
        name="Post-market HSI update",
        misfire_grace_time=300,
    )

    logger.info(
        f"Scheduler started. "
        f"Pre-market: {settings.scheduler.pre_market_time} HKT, "
        f"Post-market: {settings.scheduler.post_market_time} HKT"
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
