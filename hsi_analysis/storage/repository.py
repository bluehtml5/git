"""CRUD operations for all database tables."""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from .database import DatabaseManager
from ..data.models import FuturesSnapshot, OIRecord, TechnicalSignals


class SnapshotRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def save(self, snap: FuturesSnapshot) -> None:
        sql = """
        INSERT OR REPLACE INTO daily_snapshots
          (trade_date, ao_big, ao_mini, dh, dl, settlement, monthly_mid,
           upper_band, lower_band, basis, spot_close, vix,
           a50_change_pct, hstech_change_pct, volume)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        with self.db.get_connection() as conn:
            conn.execute(sql, (
                snap.trade_date.isoformat(),
                snap.ao_big, snap.ao_mini, snap.dh, snap.dl,
                snap.settlement, snap.monthly_mid,
                snap.upper_band, snap.lower_band,
                snap.basis, snap.spot_close, snap.vix,
                snap.a50_change_pct, snap.hstech_change_pct, snap.volume,
            ))
            conn.commit()

    def get_by_date(self, trade_date: date) -> Optional[FuturesSnapshot]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM daily_snapshots WHERE trade_date=?",
                (trade_date.isoformat(),),
            ).fetchone()
        if row is None:
            return None
        return FuturesSnapshot(
            trade_date=date.fromisoformat(row["trade_date"]),
            ao_big=row["ao_big"] or 0.0,
            ao_mini=row["ao_mini"] or 0.0,
            dh=row["dh"] or 0.0,
            dl=row["dl"] or 0.0,
            settlement=row["settlement"] or 0.0,
            monthly_mid=row["monthly_mid"] or 0.0,
            upper_band=row["upper_band"] or 0.0,
            lower_band=row["lower_band"] or 0.0,
            basis=row["basis"] or 0.0,
            spot_close=row["spot_close"] or 0.0,
            vix=row["vix"] or 0.0,
            a50_change_pct=row["a50_change_pct"] or 0.0,
            hstech_change_pct=row["hstech_change_pct"] or 0.0,
            volume=row["volume"] or 0.0,
        )

    def get_range(self, start: date, end: date) -> List[FuturesSnapshot]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM daily_snapshots WHERE trade_date BETWEEN ? AND ? ORDER BY trade_date",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        result = []
        for row in rows:
            result.append(FuturesSnapshot(
                trade_date=date.fromisoformat(row["trade_date"]),
                ao_big=row["ao_big"] or 0.0,
                ao_mini=row["ao_mini"] or 0.0,
                dh=row["dh"] or 0.0,
                dl=row["dl"] or 0.0,
                settlement=row["settlement"] or 0.0,
                monthly_mid=row["monthly_mid"] or 0.0,
                upper_band=row["upper_band"] or 0.0,
                lower_band=row["lower_band"] or 0.0,
                basis=row["basis"] or 0.0,
                spot_close=row["spot_close"] or 0.0,
                vix=row["vix"] or 0.0,
                a50_change_pct=row["a50_change_pct"] or 0.0,
                hstech_change_pct=row["hstech_change_pct"] or 0.0,
                volume=row["volume"] or 0.0,
            ))
        return result


class OIRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def save(self, record: OIRecord) -> None:
        sql = """
        INSERT OR REPLACE INTO oi_records
          (trade_date, net_long, net_short, net_position, oi_change, interpretation)
        VALUES (?,?,?,?,?,?)
        """
        with self.db.get_connection() as conn:
            conn.execute(sql, (
                record.trade_date.isoformat(),
                record.net_long, record.net_short,
                record.net_position, record.oi_change,
                record.interpretation,
            ))
            conn.commit()

    def get_by_date(self, trade_date: date) -> Optional[OIRecord]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM oi_records WHERE trade_date=?",
                (trade_date.isoformat(),),
            ).fetchone()
        if row is None:
            return None
        return OIRecord(
            trade_date=date.fromisoformat(row["trade_date"]),
            net_long=row["net_long"] or 0,
            net_short=row["net_short"] or 0,
            net_position=row["net_position"] or 0,
            oi_change=row["oi_change"] or 0,
            interpretation=row["interpretation"] or "",
        )

    def get_recent(self, n: int = 5) -> List[OIRecord]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM oi_records ORDER BY trade_date DESC LIMIT ?", (n,)
            ).fetchall()
        return [
            OIRecord(
                trade_date=date.fromisoformat(r["trade_date"]),
                net_long=r["net_long"] or 0,
                net_short=r["net_short"] or 0,
                net_position=r["net_position"] or 0,
                oi_change=r["oi_change"] or 0,
                interpretation=r["interpretation"] or "",
            )
            for r in rows
        ]


class SignalsRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def save(self, sig: TechnicalSignals) -> None:
        sql = """
        INSERT OR REPLACE INTO technical_signals
          (trade_date, timeframe, macd_line, macd_signal, macd_hist,
           rsi, kdj_k, kdj_d, kdj_j, atr, structure, trend, close)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        with self.db.get_connection() as conn:
            conn.execute(sql, (
                sig.trade_date.isoformat(), sig.timeframe,
                sig.macd_line, sig.macd_signal, sig.macd_hist,
                sig.rsi, sig.kdj_k, sig.kdj_d, sig.kdj_j,
                sig.atr, sig.structure, sig.trend, sig.close,
            ))
            conn.commit()

    def get_latest(self, timeframe: str) -> Optional[TechnicalSignals]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM technical_signals WHERE timeframe=? ORDER BY trade_date DESC LIMIT 1",
                (timeframe,),
            ).fetchone()
        if row is None:
            return None
        return TechnicalSignals(
            trade_date=date.fromisoformat(row["trade_date"]),
            timeframe=row["timeframe"],
            macd_line=row["macd_line"] or 0.0,
            macd_signal=row["macd_signal"] or 0.0,
            macd_hist=row["macd_hist"] or 0.0,
            rsi=row["rsi"] or 50.0,
            kdj_k=row["kdj_k"] or 50.0,
            kdj_d=row["kdj_d"] or 50.0,
            kdj_j=row["kdj_j"] or 50.0,
            atr=row["atr"] or 0.0,
            structure=row["structure"] or "unknown",
            trend=row["trend"] or "ranging",
            close=row["close"] or 0.0,
        )


class TradeRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def record_result(
        self,
        trade_date: date,
        direction: str,
        entry_price: float,
        exit_price: float,
        pnl_points: int,
        contract_type: str = "mini",
        contracts: int = 1,
        notes: str = "",
    ) -> None:
        multiplier = 50 if contract_type == "big" else 10
        pnl_hkd = pnl_points * multiplier * contracts
        sql = """
        INSERT INTO trade_results
          (trade_date, direction, entry_price, exit_price,
           pnl_points, contract_type, contracts, pnl_hkd, notes)
        VALUES (?,?,?,?,?,?,?,?,?)
        """
        with self.db.get_connection() as conn:
            conn.execute(sql, (
                trade_date.isoformat(), direction,
                entry_price, exit_price,
                pnl_points, contract_type, contracts, pnl_hkd, notes,
            ))
            conn.commit()

    def get_recent(self, n: int = 20) -> List[dict]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM trade_results ORDER BY trade_date DESC LIMIT ?", (n,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_pnl_points(self) -> List[int]:
        """Return all pnl_points in chronological order for stats calculation."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT pnl_points FROM trade_results ORDER BY id"
            ).fetchall()
        return [r[0] for r in rows]
