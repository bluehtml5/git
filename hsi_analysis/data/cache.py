"""SQLite-backed OHLCV cache to avoid redundant yfinance fetches."""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd

from ..storage.database import DatabaseManager


class PriceCache:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def get(
        self,
        ticker: str,
        start: date,
        end: date,
        interval: str,
    ) -> Optional[pd.DataFrame]:
        """Return cached DataFrame if all trading dates in range are present."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT timestamp, open, high, low, close, volume
                   FROM price_cache
                   WHERE ticker=? AND interval=?
                     AND timestamp >= ? AND timestamp <= ?
                   ORDER BY timestamp""",
                (ticker, interval, start.isoformat(), end.isoformat()),
            ).fetchall()
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        return df

    def put(self, ticker: str, interval: str, df: pd.DataFrame) -> None:
        """Insert or replace OHLCV bars into the cache."""
        if df is None or df.empty:
            return
        df = df.copy()
        df.index = pd.to_datetime(df.index)

        rows = []
        for ts, row in df.iterrows():
            rows.append((
                ticker,
                interval,
                ts.isoformat(),
                float(row.get("Open", row.get("open", 0))),
                float(row.get("High", row.get("high", 0))),
                float(row.get("Low", row.get("low", 0))),
                float(row.get("Close", row.get("close", 0))),
                float(row.get("Volume", row.get("volume", 0))),
            ))

        with self.db.get_connection() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO price_cache
                   (ticker, interval, timestamp, open, high, low, close, volume)
                   VALUES (?,?,?,?,?,?,?,?)""",
                rows,
            )
            conn.commit()

    def invalidate(self, ticker: str, trade_date: date) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                "DELETE FROM price_cache WHERE ticker=? AND timestamp LIKE ?",
                (ticker, f"{trade_date.isoformat()}%"),
            )
            conn.commit()
