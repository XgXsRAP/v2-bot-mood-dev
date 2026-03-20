"""
Real-Time Order Book Dashboard
BTC (or any coin) - BUY (Green) / SELL (Red)

Uses Hyperliquid's PUBLIC API directly - NO API key needed!
Run alongside the bot as a side monitor.

Usage:
    python orderbook_dashboard.py              # BTC default
    python orderbook_dashboard.py ETH          # Any coin
    python orderbook_dashboard.py SOL 5        # SOL, 5s refresh
"""

import os
import sys
import time
import requests
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================
SYMBOL = sys.argv[1].upper() if len(sys.argv) > 1 else "BTC"
REFRESH_SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 2
MAX_LEVELS = 15
BAR_WIDTH = 40

HYPERLIQUID_API = "https://api.hyperliquid.xyz/info"
# ============================================

try:
    from rich.console import Console, Group
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.live import Live
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def fetch_orderbook(symbol):
    """Fetch L2 orderbook directly from Hyperliquid (free, no auth)"""
    resp = requests.post(HYPERLIQUID_API, json={
        "type": "l2Book",
        "coin": symbol
    }, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # Hyperliquid returns: {"levels": [[ {"px","sz","n"}, ...], [...]]}
    # levels[0] = bids (sorted high->low), levels[1] = asks (sorted low->high)
    raw_levels = data.get("levels", [[], []])

    bids = [{"px": lv["px"], "sz": lv["sz"], "n": lv["n"]} for lv in raw_levels[0]]
    asks = [{"px": lv["px"], "sz": lv["sz"], "n": lv["n"]} for lv in raw_levels[1]]

    best_bid = float(bids[0]["px"]) if bids else 0
    best_ask = float(asks[0]["px"]) if asks else 0
    mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
    spread = best_ask - best_bid
    spread_bps = round((spread / mid_price) * 10000, 2) if mid_price else 0

    return {
        "bids": bids,
        "asks": asks,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid_price": mid_price,
        "spread": spread,
        "spread_bps": spread_bps,
    }


def format_price(price):
    p = float(price)
    if p >= 1000:
        return f"${p:,.2f}"
    elif p >= 1:
        return f"${p:,.4f}"
    else:
        return f"${p:,.6f}"


def format_size(size):
    s = float(size)
    if s >= 1000:
        return f"{s:,.1f}"
    elif s >= 1:
        return f"{s:,.3f}"
    else:
        return f"{s:,.5f}"


def format_usd(value):
    if value >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"
    elif value >= 1_000:
        return f"${value / 1_000:,.1f}K"
    else:
        return f"${value:,.2f}"


def build_dashboard():
    """Build the rich dashboard for one refresh cycle"""
    try:
        ob = fetch_orderbook(SYMBOL)
    except Exception as e:
        return Panel(f"[red]Error: {e}[/red]", title="ERROR")

    bids = ob["bids"][:MAX_LEVELS]
    asks = ob["asks"][:MAX_LEVELS]

    # Max USD value for bar scaling
    all_usd = []
    for lv in bids + asks:
        all_usd.append(float(lv["px"]) * float(lv["sz"]))
    max_usd = max(all_usd) if all_usd else 1

    total_bid_usd = sum(float(b["px"]) * float(b["sz"]) for b in bids)
    total_ask_usd = sum(float(a["px"]) * float(a["sz"]) for a in asks)
    total_depth = total_bid_usd + total_ask_usd
    bid_pct = (total_bid_usd / total_depth * 100) if total_depth > 0 else 50
    ask_pct = 100 - bid_pct

    # ── ASKS (sells) ──
    ask_table = Table(show_header=True, header_style="bold red", box=None, pad_edge=False)
    ask_table.add_column("Orders", justify="center", width=7)
    ask_table.add_column("Size", justify="right", width=12)
    ask_table.add_column("Price", justify="right", width=14)
    ask_table.add_column("USD Value", justify="right", width=12)
    ask_table.add_column("Depth", justify="left", width=BAR_WIDTH + 2)

    ask_rows = []
    for lv in asks:
        px, sz, n = float(lv["px"]), float(lv["sz"]), lv["n"]
        usd_val = px * sz
        bar_len = int((usd_val / max_usd) * BAR_WIDTH) if max_usd > 0 else 0
        ask_rows.append((
            f"[dim]{n}[/dim]",
            f"[red]{format_size(sz)}[/red]",
            f"[bold red]{format_price(px)}[/bold red]",
            f"[red]{format_usd(usd_val)}[/red]",
            f"[red]{'█' * bar_len}[/red]"
        ))

    for row in reversed(ask_rows):
        ask_table.add_row(*row)

    # ── SPREAD ──
    spread_text = Text()
    spread_text.append(f"\n  {'─' * 60}\n", style="dim white")
    spread_text.append(f"  ◆ MID: ", style="bold white")
    spread_text.append(format_price(ob["mid_price"]), style="bold yellow")
    spread_text.append(f"   SPREAD: ", style="dim white")
    spread_text.append(f"{ob['spread_bps']} bps", style="bold yellow")
    spread_text.append(f"   ({ob['spread']:.2f})", style="dim")
    spread_text.append(f"\n  {'─' * 60}\n", style="dim white")

    # ── BIDS (buys) ──
    bid_table = Table(show_header=True, header_style="bold green", box=None, pad_edge=False)
    bid_table.add_column("Orders", justify="center", width=7)
    bid_table.add_column("Size", justify="right", width=12)
    bid_table.add_column("Price", justify="right", width=14)
    bid_table.add_column("USD Value", justify="right", width=12)
    bid_table.add_column("Depth", justify="left", width=BAR_WIDTH + 2)

    for lv in bids:
        px, sz, n = float(lv["px"]), float(lv["sz"]), lv["n"]
        usd_val = px * sz
        bar_len = int((usd_val / max_usd) * BAR_WIDTH) if max_usd > 0 else 0
        bid_table.add_row(
            f"[dim]{n}[/dim]",
            f"[green]{format_size(sz)}[/green]",
            f"[bold green]{format_price(px)}[/bold green]",
            f"[green]{format_usd(usd_val)}[/green]",
            f"[green]{'█' * bar_len}[/green]"
        )

    # ── PRESSURE BAR ──
    pressure_w = 50
    buy_bars = int((bid_pct / 100) * pressure_w)
    sell_bars = pressure_w - buy_bars

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
    header.append(f"Bid: {format_price(ob['best_bid'])}", style="bold green")
    header.append(f"  │  ", style="dim")
    header.append(f"Ask: {format_price(ob['best_ask'])}", style="bold red")
    header.append(f"  │  ", style="dim")
    header.append(now, style="dim")

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
        subtitle=f"[dim]Hyperliquid Direct API (FREE) │ {len(bids)} bids │ {len(asks)} asks[/dim]",
        border_style="cyan",
    )


def run_simple():
    """Fallback without rich library"""
    while True:
        os.system('clear' if os.name != 'nt' else 'cls')
        try:
            ob = fetch_orderbook(SYMBOL)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(REFRESH_SECONDS)
            continue

        bids = ob["bids"][:MAX_LEVELS]
        asks = ob["asks"][:MAX_LEVELS]
        now = datetime.now().strftime("%H:%M:%S")

        print(f"\n{'=' * 60}")
        print(f"  {SYMBOL} ORDER BOOK  │  {now}  │  Spread: {ob['spread_bps']} bps")
        print(f"{'=' * 60}")

        print(f"\n  {'SELLS (ASKS)':^56}")
        print(f"  {'Price':>14}  {'Size':>12}  {'USD':>12}  {'Orders':>6}")
        print(f"  {'-' * 50}")
        for lv in reversed(asks):
            px, sz = float(lv["px"]), float(lv["sz"])
            print(f"  {format_price(px):>14}  {format_size(sz):>12}  {format_usd(px * sz):>12}  {lv['n']:>6}")

        print(f"\n  {'◆ MID: ' + format_price(ob['mid_price']):^56}")
        print()

        print(f"  {'BUYS (BIDS)':^56}")
        print(f"  {'Price':>14}  {'Size':>12}  {'USD':>12}  {'Orders':>6}")
        print(f"  {'-' * 50}")
        for lv in bids:
            px, sz = float(lv["px"]), float(lv["sz"])
            print(f"  {format_price(px):>14}  {format_size(sz):>12}  {format_usd(px * sz):>12}  {lv['n']:>6}")

        total_bid = sum(float(b["px"]) * float(b["sz"]) for b in bids)
        total_ask = sum(float(a["px"]) * float(a["sz"]) for a in asks)
        total = total_bid + total_ask
        bid_pct = (total_bid / total * 100) if total > 0 else 50

        print(f"\n  BUY {bid_pct:.1f}% ({format_usd(total_bid)})  │  SELL {100 - bid_pct:.1f}% ({format_usd(total_ask)})")
        print(f"\n  Hyperliquid Direct API (FREE) │ Refreshing every {REFRESH_SECONDS}s │ Ctrl+C to exit")

        time.sleep(REFRESH_SECONDS)


def main():
    print(f"Starting {SYMBOL} orderbook dashboard (Hyperliquid direct - no API key needed)...")

    if HAS_RICH:
        console = Console()
        try:
            with Live(build_dashboard(), console=console, refresh_per_second=1, screen=True) as live:
                while True:
                    time.sleep(REFRESH_SECONDS)
                    live.update(build_dashboard())
        except KeyboardInterrupt:
            console.print("\n[dim]Dashboard stopped.[/dim]")
    else:
        print("(Install 'rich' for the fancy version: pip install rich)")
        try:
            run_simple()
        except KeyboardInterrupt:
            print("\nDashboard stopped.")


if __name__ == "__main__":
    main()
