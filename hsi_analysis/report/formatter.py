"""Render DailyReport → Chinese Markdown string and Rich terminal output."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..data.models import DailyReport


def _hk_num(value: float) -> str:
    return f"{value:,.0f}"


def _pts(value: float) -> str:
    return f"{value:+.0f}"


def _pct(value: float) -> str:
    return f"{value:+.2f}%"


def _trend_zh(trend: str) -> str:
    return {"bullish": "偏多↑", "bearish": "偏空↓", "ranging": "橫行→"}.get(trend, trend)


def _struct_desc(structure: str) -> str:
    return {
        "HH/HL": "較高高點/較高低點（上升趨勢結構）",
        "LH/LL": "較低高點/較低低點（下跌趨勢結構）",
        "HH/LL": "較高高點/較低低點（擴張形態）",
        "LH/HL": "較低高點/較高低點（收窄形態）",
        "unknown": "結構不明確",
    }.get(structure, structure)


class ReportFormatter:
    def __init__(self, template_dir: Optional[str] = None):
        if template_dir is None:
            template_dir = str(Path(__file__).parent / "templates")
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["hk"] = _hk_num
        self.env.filters["pts"] = _pts
        self.env.filters["pct"] = _pct
        self.env.filters["trend_zh"] = _trend_zh
        self.env.filters["struct"] = _struct_desc

    def render(self, report: DailyReport) -> str:
        template = self.env.get_template("daily_report.md.jinja")
        return template.render(r=report)

    def save_to_file(self, report: DailyReport, output_dir: str = "reports") -> str:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        filename = f"{report.report_date.isoformat()}_hsi_daily.md"
        filepath = str(Path(output_dir) / filename)
        content = self.render(report)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    def print_terminal(self, report: DailyReport) -> None:
        """Print a Rich-formatted summary to the terminal."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich import box
            from rich.panel import Panel
            from rich.text import Text
        except ImportError:
            print(self.render(report))
            return

        console = Console()
        r = report
        s = r.snapshot

        console.print()
        console.rule(f"[bold cyan]恒生指數期貨每日分析  {r.report_date}[/bold cyan]")

        # Price table
        price_tbl = Table(box=box.SIMPLE_HEAVY, title="價格框架")
        price_tbl.add_column("項目", style="cyan")
        price_tbl.add_column("大期", justify="right")
        price_tbl.add_column("細期", justify="right")
        price_tbl.add_row("AO 開市價", _hk_num(s.ao_big), _hk_num(s.ao_mini))
        price_tbl.add_row("日高 DH", _hk_num(s.dh), "—")
        price_tbl.add_row("日低 DL", _hk_num(s.dl), "—")
        price_tbl.add_row("月中 M", _hk_num(s.monthly_mid), "—")
        price_tbl.add_row("上軌", _hk_num(s.upper_band), "—")
        price_tbl.add_row("下軌", _hk_num(s.lower_band), "—")
        price_tbl.add_row("基差", _pts(s.basis), "—")
        console.print(price_tbl)

        # Indicators
        ind_tbl = Table(box=box.SIMPLE, title="技術指標")
        ind_tbl.add_column("指標", style="cyan")
        ind_tbl.add_column("日線", justify="right")
        ind_tbl.add_column("4小時", justify="right")
        ind_tbl.add_column("1小時", justify="right")
        for label, attr in [("MACD Hist", "macd_hist"), ("RSI", "rsi"), ("KDJ-J", "kdj_j"), ("ATR", "atr")]:
            ind_tbl.add_row(
                label,
                f"{getattr(r.signals_1d, attr):.1f}",
                f"{getattr(r.signals_4h, attr):.1f}",
                f"{getattr(r.signals_1h, attr):.1f}",
            )
        ind_tbl.add_row("趨勢", _trend_zh(r.signals_1d.trend), _trend_zh(r.signals_4h.trend), _trend_zh(r.signals_1h.trend))
        ind_tbl.add_row("結構", r.signals_1d.structure, r.signals_4h.structure, r.signals_1h.structure)
        console.print(ind_tbl)

        # OI
        oi = r.oi_record
        oi_color = "green" if oi.net_position > 0 else "red"
        console.print(Panel(
            f"[{oi_color}]淨倉: {oi.net_position:+,d} 張  |  變化: {oi.oi_change:+,d}[/{oi_color}]\n{oi.interpretation}",
            title="期指淨倉 (T+1)",
        ))

        # Scenarios
        for sc in r.scenarios:
            ts = sc.trade_setup
            direction_color = "green" if ts.direction == "long" else "red"
            direction_zh = "揸" if ts.direction == "long" else "沽"
            console.print(Panel(
                f"[bold]觸發條件:[/bold] {sc.trigger_condition}\n"
                f"[{direction_color}]{direction_zh} {_hk_num(ts.entry_price)}  "
                f"止蝕 {ts.stop_points}點  "
                f"目標 {ts.target_points}點  "
                f"R:R 1:{ts.risk_reward:.1f}[/{direction_color}]\n"
                f"[dim]{sc.rationale}[/dim]",
                title=f"情景{sc.rank} [{sc.label}]",
            ))

        # Risk state
        rs = r.risk_state
        if rs.get("warning"):
            console.print(f"[bold red]{rs['warning']}[/bold red]")

        # Market strength
        ms = r.market_strength
        console.print(
            f"市場強度: [bold]{ms.overall}[/bold]  "
            f"成交量: {ms.volume_signal}  "
            f"持倉: {ms.oi_signal}  "
            f"基差: {ms.basis_signal}  "
            f"波動率: {ms.volatility_signal}"
        )

        if r.wave_context:
            console.print(f"[dim italic]{r.wave_context}[/dim italic]")

        if r.data_notes:
            for note in r.data_notes:
                console.print(f"[yellow]{note}[/yellow]")

        console.rule()
        console.print()
