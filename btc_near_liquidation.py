"""
🌙 Moon Dev's Bitcoin Positions Near Liquidation Monitor
Built with love by Moon Dev 🚀

Shows BTC positions close to their liquidation price on Hyperliquid.
Bottom: totals within 1% and 2%, plus the 3 closest longs and 3 closest shorts.
Refreshes every 5 seconds. Built for hand traders who gamble.

Author: Moon Dev
"""

import sys
import os
import time
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api import MoonDevAPI

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.live import Live
from rich import box

# ==================== MOON DEV CONFIG ====================
REFRESH_SECONDS = 5

BULL_COLOR = "bright_green"
BEAR_COLOR = "bright_red"
WARN_COLOR = "bright_yellow"
DANGER_COLOR = "bold bright_red"


def format_usd(value):
    if value is None or value == 0:
        return "$0"
    if abs(value) >= 1_000_000_000:
        return f"${value/1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"${value/1_000:.1f}K"
    return f"${value:,.0f}"


def format_price(price):
    if price is None or price == 0:
        return "N/A"
    return f"${price:,.2f}"


def distance_color(pct):
    if pct <= 1.0:
        return DANGER_COLOR
    elif pct <= 2.0:
        return BEAR_COLOR
    elif pct <= 5.0:
        return WARN_COLOR
    return "dim"


def get_val(pos):
    """Get position value - uses 'value' field from API"""
    return float(pos.get('value', pos.get('position_value', pos.get('value_usd', 0))))


def get_dist(pos):
    return float(pos.get('distance_pct', 100))


def get_entry(pos):
    return float(pos.get('entry_price', pos.get('entry_px', 0)))


def get_liq(pos):
    return float(pos.get('liq_price', pos.get('liquidation_price', pos.get('liquidation_px', 0))))


def get_pnl(pos):
    return float(pos.get('pnl', pos.get('unrealized_pnl', 0)))


def create_header():
    banner = """  ₿ ██████╗ ████████╗ ██████╗    ██╗     ██╗ ██████╗     ██╗    ██╗ █████╗ ████████╗ ██████╗██╗  ██╗
    ██╔══██╗╚══██╔══╝██╔════╝    ██║     ██║██╔═══██╗    ██║    ██║██╔══██╗╚══██╔══╝██╔════╝██║  ██║
    ██████╔╝   ██║   ██║         ██║     ██║██║   ██║    ██║ █╗ ██║███████║   ██║   ██║     ███████║
    ██╔══██╗   ██║   ██║         ██║     ██║██║▄▄ ██║    ██║███╗██║██╔══██║   ██║   ██║     ██╔══██║
    ██████╔╝   ██║   ╚██████╗    ███████╗██║╚██████╔╝    ╚███╔███╔╝██║  ██║   ██║   ╚██████╗██║  ██║
    ╚═════╝    ╚═╝    ╚═════╝    ╚══════╝╚═╝ ╚══▀▀═╝     ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝"""
    return Panel(
        Align.center(Text(banner, style="bold bright_yellow")),
        title="🌙 [bold bright_magenta]MOON DEV's BTC LIQUIDATION WATCH[/bold bright_magenta] 🌙",
        subtitle="[bold bright_cyan]Positions Close to Liquidation | Hyperliquid | Refreshes Every 5s[/bold bright_cyan]",
        border_style="bright_yellow",
        box=box.DOUBLE_EDGE,
        padding=(0, 1)
    )


def build_position_table(positions, title_str, side_color, header_bg):
    """Build a clean position table - no wallet, no leverage, no danger column"""
    if not positions:
        return None

    table = Table(
        title=f"[bold {side_color}]{title_str} ({len(positions)})[/]",
        box=box.HEAVY_EDGE,
        border_style=side_color,
        header_style=f"bold bright_white on {header_bg}",
        show_lines=True,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("SIZE", style="bold bright_yellow", justify="right", width=14)
    table.add_column("LIQ PRICE", justify="right", width=14)
    table.add_column("DISTANCE", justify="right", width=10)

    for i, pos in enumerate(positions[:25], 1):
        value = get_val(pos)
        liq_price = get_liq(pos)
        dist = get_dist(pos)

        color = distance_color(dist)

        table.add_row(
            str(i),
            format_usd(value),
            f"[{color}]{format_price(liq_price)}[/]",
            f"[{color}]{dist:.2f}%[/]",
        )

    return table


def build_closest_table(longs, shorts):
    """Build the 3 closest longs + 3 closest shorts mini table"""
    # Sort by distance ascending
    sorted_longs = sorted(longs, key=get_dist)[:3]
    sorted_shorts = sorted(shorts, key=get_dist)[:3]

    table = Table(
        title="[bold bright_magenta]🎯 3 CLOSEST LONGS + 3 CLOSEST SHORTS TO LIQUIDATION[/]",
        box=box.DOUBLE_EDGE,
        border_style="bright_magenta",
        header_style="bold bright_white on dark_magenta",
        show_lines=True,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("SIDE", justify="center", width=8)
    table.add_column("SIZE", style="bold bright_yellow", justify="right", width=14)
    table.add_column("LIQ PRICE", justify="right", width=14)
    table.add_column("DISTANCE", justify="right", width=10)

    for pos in sorted_longs:
        value = get_val(pos)
        liq_price = get_liq(pos)
        dist = get_dist(pos)
        color = distance_color(dist)

        table.add_row(
            f"[{BULL_COLOR}]📈 LONG[/]",
            format_usd(value),
            f"[{color}]{format_price(liq_price)}[/]",
            f"[{color}]{dist:.2f}%[/]",
        )

    for pos in sorted_shorts:
        value = get_val(pos)
        liq_price = get_liq(pos)
        dist = get_dist(pos)
        color = distance_color(dist)

        table.add_row(
            f"[{BEAR_COLOR}]📉 SHORT[/]",
            format_usd(value),
            f"[{color}]{format_price(liq_price)}[/]",
            f"[{color}]{dist:.2f}%[/]",
        )

    return table


def build_dashboard(api, cycle_count):
    """Build the BTC near-liquidation dashboard"""
    output = []
    output.append(create_header())

    # ==================== FETCH BTC POSITIONS ====================
    all_data = api.get_all_positions()

    btc_data = {}
    if isinstance(all_data, dict) and 'symbols' in all_data:
        btc_data = all_data['symbols'].get('BTC', {})

    longs = btc_data.get('longs', [])
    shorts = btc_data.get('shorts', [])

    # ==================== SUMMARY PANEL ====================
    total_long_value = sum(get_val(p) for p in longs)
    total_short_value = sum(get_val(p) for p in shorts)

    summary = Text()
    summary.append("  ₿ BTC POSITIONS NEAR LIQUIDATION  ", style="bold bright_yellow")
    summary.append("| ", style="dim")
    summary.append(f"LONGS: {len(longs)}", style=BULL_COLOR)
    summary.append(f" ({format_usd(total_long_value)})", style=BULL_COLOR)
    summary.append(" | ", style="dim")
    summary.append(f"SHORTS: {len(shorts)}", style=BEAR_COLOR)
    summary.append(f" ({format_usd(total_short_value)})", style=BEAR_COLOR)
    summary.append(" | ", style="dim")
    summary.append(f"Total: {len(longs) + len(shorts)} positions", style="bold white")
    output.append(Panel(summary, border_style="bright_yellow", box=box.HEAVY, padding=(0, 0)))

    # ==================== LONGS TABLE ====================
    long_table = build_position_table(longs, "📈 BTC LONG POSITIONS NEAR LIQUIDATION", BULL_COLOR, "dark_green")
    if long_table:
        output.append(long_table)

    # ==================== SHORTS TABLE ====================
    short_table = build_position_table(shorts, "📉 BTC SHORT POSITIONS NEAR LIQUIDATION", BEAR_COLOR, "dark_red")
    if short_table:
        output.append(short_table)

    # ==================== WITHIN 1% AND 2% TOTALS ====================
    longs_1pct = [p for p in longs if get_dist(p) <= 1.0]
    longs_2pct = [p for p in longs if get_dist(p) <= 2.0]
    shorts_1pct = [p for p in shorts if get_dist(p) <= 1.0]
    shorts_2pct = [p for p in shorts if get_dist(p) <= 2.0]

    longs_1pct_val = sum(get_val(p) for p in longs_1pct)
    longs_2pct_val = sum(get_val(p) for p in longs_2pct)
    shorts_1pct_val = sum(get_val(p) for p in shorts_1pct)
    shorts_2pct_val = sum(get_val(p) for p in shorts_2pct)

    totals_table = Table(
        title="[bold bright_magenta]🎯 BTC POSITIONS CLOSE TO LIQUIDATION - TOTALS[/]",
        box=box.DOUBLE_EDGE,
        border_style="bright_magenta",
        header_style="bold bright_white on dark_magenta",
        show_lines=True,
        padding=(0, 1),
        expand=True,
    )
    totals_table.add_column("ZONE", style="bold bright_white", justify="center", width=20)
    totals_table.add_column("📈 LONG COUNT", style=BULL_COLOR, justify="right", width=14)
    totals_table.add_column("📈 LONG VALUE", style=BULL_COLOR, justify="right", width=16)
    totals_table.add_column("📉 SHORT COUNT", style=BEAR_COLOR, justify="right", width=14)
    totals_table.add_column("📉 SHORT VALUE", style=BEAR_COLOR, justify="right", width=16)
    totals_table.add_column("TOTAL VALUE", style="bold bright_yellow", justify="right", width=16)

    totals_table.add_row(
        f"[{DANGER_COLOR}]🔥 WITHIN 1%[/]",
        f"{len(longs_1pct)}", f"{format_usd(longs_1pct_val)}",
        f"{len(shorts_1pct)}", f"{format_usd(shorts_1pct_val)}",
        f"[bold bright_yellow]{format_usd(longs_1pct_val + shorts_1pct_val)}[/]",
    )
    totals_table.add_row(
        f"[{BEAR_COLOR}]🔥🔥 WITHIN 2%[/]",
        f"{len(longs_2pct)}", f"{format_usd(longs_2pct_val)}",
        f"{len(shorts_2pct)}", f"{format_usd(shorts_2pct_val)}",
        f"[bold bright_yellow]{format_usd(longs_2pct_val + shorts_2pct_val)}[/]",
    )

    output.append(totals_table)

    # ==================== 3 CLOSEST LONGS + 3 CLOSEST SHORTS ====================
    if longs or shorts:
        output.append(build_closest_table(longs, shorts))

    # ==================== FOOTER ====================
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    footer = Text()
    footer.append(f"  🌙 Moon Dev's BTC Liquidation Watch", style="bold bright_yellow")
    footer.append(f" | Refresh: {REFRESH_SECONDS}s", style="dim")
    footer.append(f" | Cycle: #{cycle_count}", style="bold white")
    footer.append(f" | {now}", style="dim")
    footer.append(f" | moondev.com", style="bold bright_magenta")
    footer.append(f" | Ctrl+C to exit", style="dim")
    output.append(Panel(footer, border_style="bright_yellow", box=box.ROUNDED, padding=(0, 0)))

    return Group(*output)


def main():
    """🌙 Moon Dev's BTC Near-Liquidation Monitor"""
    console = Console()
    console.clear()
    console.print(create_header())
    console.print("\n[bold bright_yellow]  🌙 Moon Dev:[/] Initializing BTC Liquidation Watch...")

    api = MoonDevAPI()
    if not api.api_key:
        console.print("[bold red]  ❌ No API key found! Set MOONDEV_API_KEY in your .env file[/]")
        return

    console.print(f"[bold {BULL_COLOR}]  ✅ Moon Dev API connected[/]")
    console.print(f"[bold bright_yellow]  ₿  Watching: BTC positions near liquidation[/]")
    console.print(f"[bold bright_cyan]  🔄 Refresh rate: {REFRESH_SECONDS}s[/]\n")

    cycle_count = 0

    with Live(console=console, refresh_per_second=1, vertical_overflow="visible") as live:
        while True:
            cycle_count += 1
            dashboard = build_dashboard(api, cycle_count)
            live.update(dashboard)
            time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    print("🌙 Moon Dev's BTC Liquidation Watch - Starting up...")
    print("🌙 Moon Dev says: Let's see who's about to get liquidated on Bitcoin.\n")
    main()
