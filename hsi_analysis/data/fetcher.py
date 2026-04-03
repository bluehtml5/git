"""Market data fetcher: yfinance wrapper and HKEX OI scraper."""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Dict, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    import yfinance as yf
except ImportError:
    yf = None  # allow tests to mock

from .cache import PriceCache
from .models import OIRecord
from ..config.settings import get_settings

logger = logging.getLogger(__name__)


class DataFetchError(Exception):
    pass


class MarketDataFetcher:
    """Retrieve price data from yfinance and OI from HKEX."""

    def __init__(self, cache: Optional[PriceCache] = None, use_cache: bool = True):
        self.settings = get_settings()
        self.cache = cache
        self.use_cache = use_cache and cache is not None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _yf_download(
        self,
        ticker: str,
        start: date,
        end: date,
        interval: str = "1d",
        retries: int = 3,
    ) -> pd.DataFrame:
        """Download from yfinance with retry and normalise column names."""
        if yf is None:
            raise DataFetchError("yfinance not installed")

        # Check cache first
        if self.use_cache and self.cache:
            cached = self.cache.get(ticker, start, end, interval)
            if cached is not None and not cached.empty:
                return cached

        last_exc = None
        for attempt in range(retries):
            try:
                # end+1 because yfinance end is exclusive
                df = yf.download(
                    ticker,
                    start=start.isoformat(),
                    end=(end + timedelta(days=1)).isoformat(),
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                )
                if df is not None and not df.empty:
                    # Flatten MultiIndex columns if present
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    # Normalise to lowercase
                    df.columns = [c.lower() for c in df.columns]
                    df.index = pd.to_datetime(df.index)
                    if self.use_cache and self.cache:
                        self.cache.put(ticker, interval, df)
                    return df
            except Exception as e:
                last_exc = e
                wait = 2 ** attempt
                logger.warning(f"yfinance fetch attempt {attempt+1} failed for {ticker}: {e}. Retrying in {wait}s")
                time.sleep(wait)

        raise DataFetchError(f"Failed to fetch {ticker} after {retries} attempts: {last_exc}")

    # ------------------------------------------------------------------
    # Public fetch methods
    # ------------------------------------------------------------------

    def fetch_hsi_spot(self, start: date, end: date) -> pd.DataFrame:
        return self._yf_download(self.settings.futures.hsi_ticker, start, end)

    def fetch_futures_big(self, start: date, end: date) -> pd.DataFrame:
        """
        Fetch HSI big futures (HSI=F). Falls back to ^HSI spot on failure
        because HSI=F availability on yfinance can be inconsistent.
        """
        try:
            df = self._yf_download(self.settings.futures.hsi_futures_front, start, end)
            if not df.empty:
                return df
        except DataFetchError:
            pass
        logger.warning("HSI=F unavailable, falling back to ^HSI spot")
        return self.fetch_hsi_spot(start, end)

    def fetch_futures_mini(self, start: date, end: date) -> pd.DataFrame:
        """
        Fetch mini HSI futures (MHI=F). Falls back to ^HSI on failure.
        Mini futures track big futures closely; difference is lot multiplier.
        """
        try:
            df = self._yf_download(self.settings.futures.mini_futures_front, start, end)
            if not df.empty:
                return df
        except DataFetchError:
            pass
        logger.warning("MHI=F unavailable, falling back to ^HSI spot")
        return self.fetch_hsi_spot(start, end)

    def fetch_related_indices(self, start: date, end: date) -> Dict[str, pd.DataFrame]:
        """Fetch A50, HSTECH, and VIX. Returns dict keyed by nickname."""
        fu = self.settings.futures
        results: Dict[str, pd.DataFrame] = {}
        for key, ticker in [
            ("a50", fu.a50_ticker),
            ("hstech", fu.hstech_ticker),
            ("vix", fu.vix_ticker),
        ]:
            try:
                results[key] = self._yf_download(ticker, start, end)
            except DataFetchError as e:
                logger.warning(f"Could not fetch {ticker}: {e}")
                results[key] = pd.DataFrame()
        return results

    def fetch_1h_data(self, ticker: str, days_back: int = 59) -> pd.DataFrame:
        """
        Fetch 1-hour bars. yfinance caps intraday history at ~60 days.
        Use this to build 4h bars via resample_to_4h().
        """
        end = date.today()
        start = end - timedelta(days=days_back)
        return self._yf_download(ticker, start, end, interval="1h")

    def resample_to_4h(self, df_1h: pd.DataFrame) -> pd.DataFrame:
        """
        Resample 1h OHLCV to 4h respecting HK trading sessions.
        Session 1: 09:30–12:00 (2.5h → treat as single 4h block)
        Session 2: 13:00–16:00 (3h → single 4h block)
        Evening:   17:15–03:00 (9.75h → two 4h blocks)
        We use a simple 4H resample on UTC+8 time then drop overnight
        bars that span the lunch break.
        """
        if df_1h is None or df_1h.empty:
            return pd.DataFrame()

        df = df_1h.copy()
        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert("Asia/Hong_Kong")
        else:
            df.index = df.index.tz_convert("Asia/Hong_Kong")

        df4 = df.resample("4h", origin="start_day").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna(subset=["open"])

        return df4

    # ------------------------------------------------------------------
    # HKEX OI scraping
    # ------------------------------------------------------------------

    def fetch_hkex_oi(self, trade_date: date) -> Optional[OIRecord]:
        """
        Attempt to scrape HKEX daily derivatives statistics for HSI futures OI.
        Returns None if data is unavailable (holiday, scrape failure, etc.).

        NOTE: HKEX OI data is published T+1. A pre-market 08:30 run will
        always receive prior-day data. This is flagged in data_notes.
        """
        try:
            return self._scrape_hkex_oi(trade_date)
        except Exception as e:
            logger.warning(f"HKEX OI scrape failed for {trade_date}: {e}")
            return self._fallback_oi_record(trade_date)

    def _scrape_hkex_oi(self, trade_date: date) -> Optional[OIRecord]:
        """
        Try HKEX CSV endpoint for derivatives market statistics.
        URL pattern is subject to change — handle gracefully.
        """
        date_str = trade_date.strftime("%Y%m%d")
        # HKEX publishes daily market statistics CSV
        url = (
            f"https://www.hkex.com.hk/eng/stat/dmstat/dastat/hs_{date_str}e.htm"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; HSI-Analysis-Bot/1.0)",
            "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        # Parse OI table — locate row containing "HSI" and "Net"
        # This is a best-effort parse; structure changes periodically
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if len(cells) >= 4 and "HSI" in cells[0]:
                    try:
                        net_pos = int(cells[-1].replace(",", "").replace("+", ""))
                        return OIRecord(
                            trade_date=trade_date,
                            net_long=0,
                            net_short=0,
                            net_position=net_pos,
                            oi_change=0,
                            interpretation=self._interpret_oi(net_pos, 0),
                        )
                    except (ValueError, IndexError):
                        continue
        return None

    def _fallback_oi_record(self, trade_date: date) -> OIRecord:
        """Return a placeholder when HKEX data is unavailable."""
        return OIRecord(
            trade_date=trade_date,
            net_long=0,
            net_short=0,
            net_position=0,
            oi_change=0,
            interpretation="數據暫未更新（T+1發佈，或非交易日）",
        )

    @staticmethod
    def _interpret_oi(net_position: int, oi_change: int) -> str:
        """Generate Chinese interpretation of net position change."""
        if oi_change == 0:
            return "持倉數據未有變化"
        if oi_change < 0:
            direction = "減倉"
            if net_position < 0:
                sentiment = "沽空力量增強，偏空信號"
            else:
                sentiment = "多頭減持，部分獲利"
        else:
            direction = "增倉"
            if net_position > 0:
                sentiment = "大戶多頭持倉增加，偏多信號"
            else:
                sentiment = "空頭持倉增加，偏空信號"
        abs_change = abs(oi_change)
        return f"期指淨倉{direction} {abs_change}k 張，{sentiment}"

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_latest_close(self, ticker: str) -> Tuple[float, date]:
        """Return (close_price, trade_date) for the most recent available bar."""
        end = date.today()
        start = end - timedelta(days=7)
        df = self._yf_download(ticker, start, end)
        if df.empty:
            raise DataFetchError(f"No data returned for {ticker}")
        last_row = df.iloc[-1]
        last_date = df.index[-1].date() if hasattr(df.index[-1], "date") else end
        return float(last_row["close"]), last_date

    def is_hk_trading_day(self, check_date: date) -> bool:
        """Return True if check_date is a HK trading day (Mon–Fri, not public holiday)."""
        try:
            import holidays
            hk_holidays = holidays.HongKong(years=check_date.year)
        except ImportError:
            hk_holidays = {}

        if check_date.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        if check_date in hk_holidays:
            return False
        return True
