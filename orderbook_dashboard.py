"""
📊 Real-Time Order Book Dashboard
BTC (or any coin) - BUY (Green) / SELL (Red)

Run alongside the bot as a side monitor.
Refreshes every 2 seconds with live depth visualization.

Usage:
    python orderbook_dashboard.py              # BTC default
    python orderbook_dashboard.py ETH          # Any coin
    python orderbook_dashboard.py SOL 5        # SOL, 5s refresh
"""

import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ============================================
# CONFIGURATION
# ============================================
SYMBOL = sys.argv[1].upper() if len(sys.argv) > 1 else "BTC"
REFRESH_SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 2
MAX_LEVELS = 15  # max orderbook levels to show
BAR_WIDTH = 40   # width of the depth bars

# ============================================

from api import MoonDevAPI

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
    from rich.live import Live
    from rich.align import Align
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def format_price(price):
    """Format price with appropriate decimals"""
    p = float(price)
    if p >= 1000:
        return f"${p:,.2f}"
    elif p >= 1:
        return f"${p:,.4f}"
    else:
        return f"${p:,.6f}"


def format_size(size):
    """Format size compactly"""
    s = float(size)
    if s >= 1000:
        return f"{s:,.1f}"
    elif s >= 1:
        return f"{s:,.3f}"
    else:
        return f"{s:,.5f}"


def format_usd(value):
    """Format USD value"""
    if value >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"
    elif value >= 1_000:
        return f"${value / 1_000:,.1f}K"
    else:
        return f"${value:,.2f}"


def build_dashboard(api):
    """Build the rich dashboard for one refresh cycle"""
    console = Console()

    try:
        ob = api.get_orderbook(SYMBOL)
    except Exception as e:
        return Panel(f"[red]Error fetching orderbook: {e}[/red]", title="ERROR")

    levels = ob.get("levels", [[], []])
    bids = levels[0][:MAX_LEVELS] if len(levels) > 0 else []
    asks = levels[1][:MAX_LEVELS] if len(levels) > 1 else []

    best_bid = ob.get("best_bid", "N/A")
    best_ask = ob.get("best_ask", "N/A")
    mid_price = ob.get("mid_price", "N/A")
    spread = ob.get("spread", "N/A")
    spread_bps = ob.get("spread_bps", "N/A")

    # Calculate max size for bar scaling
    all_sizes = []
    for level in bids + asks:
        sz = float(level.get("sz", 0))
        px = float(level.get("px", 0))
        all_sizes.append(sz * px)  # USD value for scaling
    max_usd = max(all_sizes) if all_sizes else 1

    # Calculate total depth
    total_bid_usd = sum(float(b.get("sz", 0)) * float(b.get("px", 0)) for b in bids)
    total_ask_usd = sum(float(a.get("sz", 0)) * float(a.get("px", 0)) for a in asks)
    total_depth = total_bid_usd + total_ask_usd
    bid_pct = (total_bid_usd / total_depth * 100) if total_depth > 0 else 50
    ask_pct = (total_ask_usd / total_depth * 100) if total_depth > 0 else 50

    # ── ASKS (sells) - reversed so highest ask is on top ──
    ask_table = Table(show_header=True, header_style="bold red", box=None, pad_edge=False)
    ask_table.add_column("Orders", justify="center", width=7)
    ask_table.add_column("Size", justify="right", width=12)
    ask_table.add_column("Price", justify="right", width=14)
    ask_table.add_column("USD Value", justify="right", width=12)
    ask_table.add_column("Depth", justify="left", width=BAR_WIDTH + 2)

    ask_rows = []
    cumulative_ask = 0
    for level in asks:
        px = float(level.get("px", 0))
        sz = float(level.get("sz", 0))
        n = level.get("n", 0)
        usd_val = px * sz
        cumulative_ask += usd_val
        bar_len = int((usd_val / max_usd) * BAR_WIDTH) if max_usd > 0 else 0
        bar = "█" * bar_len

        ask_rows.append((
            f"[dim]{n}[/dim]",
            f"[red]{format_size(sz)}[/red]",
            f"[bold red]{format_price(px)}[/bold red]",
            f"[red]{format_usd(usd_val)}[/red]",
            f"[red]{bar}[/red]"
        ))

    # Show asks reversed (highest price on top)
    for row in reversed(ask_rows):
        ask_table.add_row(*row)

    # ── SPREAD LINE ──
    spread_text = Text()
    spread_text.append(f"\n  {'─' * 60}\n", style="dim white")
    spread_text.append(f"  ◆ MID: ", style="bold white")
    spread_text.append(f"{format_price(mid_price)}", style="bold yellow")
    spread_text.append(f"   SPREAD: ", style="dim white")
    spread_text.append(f"{spread_bps} bps", style="bold yellow")
    spread_text.append(f"   ({spread})", style="dim")
    spread_text.append(f"\n  {'─' * 60}\n", style="dim white")

    # ── BIDS (buys) ──
    bid_table = Table(show_header=True, header_style="bold green", box=None, pad_edge=False)
    bid_table.add_column("Orders", justify="center", width=7)
    bid_table.add_column("Size", justify="right", width=12)
    bid_table.add_column("Price", justify="right", width=14)
    bid_table.add_column("USD Value", justify="right", width=12)
    bid_table.add_column("Depth", justify="left", width=BAR_WIDTH + 2)

    cumulative_bid = 0
    for level in bids:
        px = float(level.get("px", 0))
        sz = float(level.get("sz", 0))
        n = level.get("n", 0)
        usd_val = px * sz
        cumulative_bid += usd_val
        bar_len = int((usd_val / max_usd) * BAR_WIDTH) if max_usd > 0 else 0
        bar = "█" * bar_len

        bid_table.add_row(
            f"[dim]{n}[/dim]",
            f"[green]{format_size(sz)}[/green]",
            f"[bold green]{format_price(px)}[/bold green]",
            f"[green]{format_usd(usd_val)}[/green]",
            f"[green]{bar}[/green]"
        )

    # ── BUY/SELL PRESSURE BAR ──
    pressure_bar_width = 50
    buy_bars = int((bid_pct / 100) * pressure_bar_width)
    sell_bars = pressure_bar_width - buy_bars

    pressure = Text()
    pressure.append(f"\n  BUY  ", style="bold green")
    pressure.append("█" * buy_bars, style="green")
    pressure.append("█" * sell_bars, style="red")
    pressure.append(f"  SELL", style="bold red")
    pressure.append(f"\n  {bid_pct:.1f}%", style="bold green")
    pressure.append(f"  {format_usd(total_bid_usd)} bids", style="green")
    pressure.append(f"  │  ", style="dim")
    pressure.append(f"{format_usd(total_ask_usd)} asks", style="red")
    pressure.append(f"  {ask_pct:.1f}%", style="bold red")

    # ── HEADER ──
    now = datetime.now().strftime("%H:%M:%S")
    header = Text()
    header.append(f"  {SYMBOL} ORDER BOOK", style="bold white")
    header.append(f"  │  ", style="dim")
    header.append(f"Best Bid: {format_price(best_bid)}", style="bold green")
    header.append(f"  │  ", style="dim")
    header.append(f"Best Ask: {format_price(best_ask)}", style="bold red")
    header.append(f"  │  ", style="dim")
    header.append(f"{now}", style="dim")

    # ── ASSEMBLE ──
    from rich.console import Group
    dashboard = Group(
        header,
        Text(f"  {'═' * 65}", style="dim cyan"),
        Text("  SELLS (ASKS)", style="bold red"),
        ask_table,
        spread_text,
        Text("  BUYS (BIDS)", style="bold green"),
        bid_table,
        Text(f"\n  {'═' * 65}", style="dim cyan"),
        pressure,
        Text(f"\n  Refreshing every {REFRESH_SECONDS}s │ Ctrl+C to exit", style="dim"),
    )

    return Panel(
        dashboard,
        title=f"[bold cyan]📊 {SYMBOL} ORDERBOOK[/bold cyan]",
        subtitle=f"[dim]Moon Dev API │ {ob.get('bid_depth', '?')} bids │ {ob.get('ask_depth', '?')} asks[/dim]",
        border_style="cyan",
    )


def run_simple(api):
    """Fallback without rich library"""
    while True:
        os.system('clear' if os.name != 'nt' else 'cls')
        try:
            ob = api.get_orderbook(SYMBOL)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(REFRESH_SECONDS)
            continue

        levels = ob.get("levels", [[], []])
        bids = levels[0][:MAX_LEVELS] if len(levels) > 0 else []
        asks = levels[1][:MAX_LEVELS] if len(levels) > 1 else []

        mid = ob.get("mid_price", "?")
        spread_bps = ob.get("spread_bps", "?")
        now = datetime.now().strftime("%H:%M:%S")

        print(f"\n{'=' * 60}")
        print(f"  {SYMBOL} ORDER BOOK  │  {now}  │  Spread: {spread_bps} bps")
        print(f"{'=' * 60}")

        print(f"\n  {'SELLS (ASKS)':^56}")
        print(f"  {'Price':>14}  {'Size':>12}  {'USD':>12}  {'Orders':>6}")
        print(f"  {'-' * 50}")
        for level in reversed(asks):
            px = float(level.get("px", 0))
            sz = float(level.get("sz", 0))
            n = level.get("n", 0)
            print(f"  {format_price(px):>14}  {format_size(sz):>12}  {format_usd(px * sz):>12}  {n:>6}")

        print(f"\n  {'◆ MID: ' + format_price(mid):^56}")
        print()

        print(f"  {'BUYS (BIDS)':^56}")
        print(f"  {'Price':>14}  {'Size':>12}  {'USD':>12}  {'Orders':>6}")
        print(f"  {'-' * 50}")
        for level in bids:
            px = float(level.get("px", 0))
            sz = float(level.get("sz", 0))
            n = level.get("n", 0)
            print(f"  {format_price(px):>14}  {format_size(sz):>12}  {format_usd(px * sz):>12}  {n:>6}")

        total_bid = sum(float(b.get("sz", 0)) * float(b.get("px", 0)) for b in bids)
        total_ask = sum(float(a.get("sz", 0)) * float(a.get("px", 0)) for a in asks)
        total = total_bid + total_ask
        bid_pct = (total_bid / total * 100) if total > 0 else 50

        print(f"\n  BUY {bid_pct:.1f}% ({format_usd(total_bid)})  │  SELL {100 - bid_pct:.1f}% ({format_usd(total_ask)})")
        print(f"\n  Refreshing every {REFRESH_SECONDS}s │ Ctrl+C to exit")

        time.sleep(REFRESH_SECONDS)


def main():
    api = MoonDevAPI()

    if not api.api_key:
        print("ERROR: Set MOONDEV_API_KEY in your .env file")
        sys.exit(1)

    print(f"Starting {SYMBOL} orderbook dashboard...")

    if HAS_RICH:
        console = Console()
        try:
            with Live(build_dashboard(api), console=console, refresh_per_second=1, screen=True) as live:
                while True:
                    time.sleep(REFRESH_SECONDS)
                    live.update(build_dashboard(api))
        except KeyboardInterrupt:
            console.print("\n[dim]Dashboard stopped.[/dim]")
    else:
        print("(Install 'rich' for the fancy version: pip install rich)")
        try:
            run_simple(api)
        except KeyboardInterrupt:
            print("\nDashboard stopped.")


if __name__ == "__main__":
    main()
