"""SQLite schema creation and connection management."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_CREATE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS price_cache (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker    TEXT    NOT NULL,
        interval  TEXT    NOT NULL,
        timestamp TEXT    NOT NULL,
        open      REAL,
        high      REAL,
        low       REAL,
        close     REAL,
        volume    REAL,
        UNIQUE(ticker, interval, timestamp)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_snapshots (
        trade_date       TEXT PRIMARY KEY,
        ao_big           REAL,
        ao_mini          REAL,
        dh               REAL,
        dl               REAL,
        settlement       REAL,
        monthly_mid      REAL,
        upper_band       REAL,
        lower_band       REAL,
        basis            REAL,
        spot_close       REAL,
        vix              REAL,
        a50_change_pct   REAL,
        hstech_change_pct REAL,
        volume           REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS oi_records (
        trade_date      TEXT PRIMARY KEY,
        net_long        INTEGER,
        net_short       INTEGER,
        net_position    INTEGER,
        oi_change       INTEGER,
        interpretation  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS technical_signals (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_date  TEXT    NOT NULL,
        timeframe   TEXT    NOT NULL,
        macd_line   REAL,
        macd_signal REAL,
        macd_hist   REAL,
        rsi         REAL,
        kdj_k       REAL,
        kdj_d       REAL,
        kdj_j       REAL,
        atr         REAL,
        structure   TEXT,
        trend       TEXT,
        close       REAL,
        UNIQUE(trade_date, timeframe)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_results (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_date    TEXT    NOT NULL,
        direction     TEXT,
        entry_price   REAL,
        exit_price    REAL,
        pnl_points    INTEGER,
        contract_type TEXT,
        contracts     INTEGER,
        pnl_hkd       REAL,
        notes         TEXT
    )
    """,
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_price_cache_ticker_interval ON price_cache(ticker, interval)",
    "CREATE INDEX IF NOT EXISTS idx_tech_signals_date ON technical_signals(trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_trade_results_date ON trade_results(trade_date)",
]


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialise(self) -> None:
        """Create all tables and indexes. Safe to call repeatedly."""
        with self.get_connection() as conn:
            for stmt in _CREATE_STATEMENTS:
                conn.execute(stmt)
            for idx in _INDEXES:
                conn.execute(idx)
            # Record schema version
            conn.execute(
                "INSERT OR IGNORE INTO schema_version(version) VALUES(?)",
                (SCHEMA_VERSION,),
            )
            conn.commit()

    def get_schema_version(self) -> int:
        try:
            with self.get_connection() as conn:
                row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
                return row[0] if row and row[0] is not None else 0
        except sqlite3.OperationalError:
            return 0
