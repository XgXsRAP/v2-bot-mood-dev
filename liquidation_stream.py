"""
🌙 Moon Dev's Bitcoin Liquidation Stream - All Exchanges
Built with love by Moon Dev 🚀

Watches the live stream of Bitcoin liquidations across ALL exchanges:
- Hyperliquid
- Binance Futures
- Bybit
- OKX

Refreshes every 5 seconds with a beautiful terminal dashboard.

Author: Moon Dev
"""

import sys
import os
import time
from datetime import datetime, timedelta
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api import MoonDevAPI

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.columns import Columns
from rich.live import Live
from rich import box

# ==================== MOON DEV CONFIG ====================
REFRESH_SECONDS = 5

EXCHANGE_STYLE = {
    'hyperliquid': {'color': 'cyan', 'emoji': '💎', 'name': 'Hyperliquid'},
    'binance': {'color': 'yellow', 'emoji': '🟡', 'name': 'Binance'},
    'bybit': {'color': 'orange1', 'emoji': '🟠', 'name': 'Bybit'},
    'okx': {'color': 'bright_white', 'emoji': '⚪', 'name': 'OKX'},
}

BULL_COLOR = "bright_green"
BEAR_COLOR = "bright_red"
WARN_COLOR = "bright_yellow"


def format_usd(value):
    """Format USD - Moon Dev style"""
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


def get_exchange_style(exchange):
    ex_lower = exchange.lower()
    return EXCHANGE_STYLE.get(ex_lower, {'color': 'white', 'emoji': '🔹', 'name': exchange})


def is_btc(symbol):
    """Check if a symbol is Bitcoin"""
    s = str(symbol).upper().strip()
    return s in ['BTC', 'BTCUSDT', 'BTCUSD', 'BTC-USD', 'BTC-USDT', 'BTC-SWAP',
                 'BTCUSD_PERP', 'BTCUSDT-PERP', 'BTC-USD-SWAP', 'XBTUSD', 'XBTUSDT']


def create_header():
    """Moon Dev banner"""
    banner = """  ₿ ██████╗ ████████╗ ██████╗    ██╗     ██╗ ██████╗ ███████╗
    ██╔══██╗╚══██╔══╝██╔════╝    ██║     ██║██╔═══██╗██╔════╝
    ██████╔╝   ██║   ██║         ██║     ██║██║   ██║███████╗
    ██╔══██╗   ██║   ██║         ██║     ██║██║▄▄ ██║╚════██║
    ██████╔╝   ██║   ╚██████╗    ███████╗██║╚██████╔╝███████║
    ╚═════╝    ╚═╝    ╚═════╝    ╚══════╝╚═╝ ╚══▀▀═╝╚══════╝"""
    return Panel(
        Align.center(Text(banner, style="bold bright_yellow")),
        title="🌙 [bold bright_magenta]MOON DEV's BTC LIQUIDATION STREAM[/bold bright_magenta] 🌙",
        subtitle="[bold bright_cyan]All Exchanges: Hyperliquid • Binance • Bybit • OKX | Refreshes Every 5s[/bold bright_cyan]",
        border_style="bright_yellow",
        box=box.DOUBLE_EDGE,
        padding=(0, 1)
    )


def extract_liquidations(data, exchange_name):
    """Extract liquidation list from various response formats"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ['liquidations', 'data', 'events']:
            if key in data and isinstance(data[key], list):
                return data[key]
        # could be a stats dict with nested lists
        if 'stats' in data:
            return extract_liquidations(data['stats'], exchange_name)
    return []


def filter_btc(liq_list):
    """Filter liquidation list to BTC only"""
    return [liq for liq in liq_list if is_btc(liq.get('symbol', liq.get('coin', '')))]


def get_liq_timestamp(liq):
    """Parse liquidation timestamp to datetime"""
    ts = liq.get('timestamp', liq.get('time', liq.get('trade_time', '')))
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts)
    if isinstance(ts, str) and ts:
        if 'T' in ts:
            return datetime.fromisoformat(ts.replace('Z', '+00:00').split('+')[0][:19])
    return None


def filter_by_minutes(liq_list, minutes):
    """Filter liquidations to only those within the last N minutes"""
    cutoff = datetime.now() - timedelta(minutes=minutes)
    result = []
    for liq in liq_list:
        t = get_liq_timestamp(liq)
        if t is None or t >= cutoff:
            result.append(liq)
    return result


def build_dashboard(api, cycle_count, cumulative_stats):
    """Build the BTC liquidation stream dashboard"""
    output = []
    output.append(create_header())

    # ==================== FETCH FROM ALL EXCHANGES ====================
    all_btc_liqs = []
    exchange_counts = {}
    exchange_volumes = {}

    # Fetch from each exchange and combined endpoint
    fetchers = [
        ("hyperliquid", lambda: api.get_liquidations("1h")),
        ("binance", lambda: api.get_binance_liquidations("1h")),
        ("bybit", lambda: api.get_bybit_liquidations("1h")),
        ("okx", lambda: api.get_okx_liquidations("1h")),
    ]

    for exchange_name, fetcher in fetchers:
        try:
            data = fetcher()
        except Exception as e:
            print(f"🌙 Moon Dev: {exchange_name} API hiccup, skipping this cycle - {e}")
            data = []
        liq_list = extract_liquidations(data, exchange_name)
        btc_liqs = filter_btc(liq_list)

        # Tag with exchange
        for liq in btc_liqs:
            liq['_exchange'] = exchange_name

        all_btc_liqs.extend(btc_liqs)
        exchange_counts[exchange_name] = len(btc_liqs)

        vol = sum(float(liq.get('value', liq.get('usd_value', liq.get('value_usd',
                   liq.get('quantity', liq.get('usd_size', 0)))))) for liq in btc_liqs)
        exchange_volumes[exchange_name] = vol

    # Also try the combined endpoint for any we might have missed
    try:
        combined_data = api.get_all_liquidations("1h")
    except Exception as e:
        print(f"🌙 Moon Dev: Combined endpoint hiccup, skipping - {e}")
        combined_data = []
    combined_list = extract_liquidations(combined_data, "all")
    combined_btc = filter_btc(combined_list)

    # Merge (avoid exact duplicates by checking timestamp+value pairs)
    existing_keys = set()
    for liq in all_btc_liqs:
        key = (liq.get('timestamp', ''), str(liq.get('value', liq.get('usd_value', ''))))
        existing_keys.add(key)

    for liq in combined_btc:
        key = (liq.get('timestamp', ''), str(liq.get('value', liq.get('usd_value', ''))))
        if key not in existing_keys:
            exchange = liq.get('exchange', liq.get('source', 'unknown'))
            liq['_exchange'] = exchange
            all_btc_liqs.append(liq)

    # Sort by value descending
    all_btc_liqs.sort(
        key=lambda x: float(x.get('value', x.get('usd_value', x.get('value_usd',
                      x.get('quantity', x.get('usd_size', 0)))))),
        reverse=True
    )

    # Update cumulative stats
    total_vol = sum(exchange_volumes.values())
    total_count = len(all_btc_liqs)
    long_count = sum(1 for l in all_btc_liqs if str(l.get('side', l.get('direction', ''))).lower() in ['long', 'buy', 'b'])
    short_count = total_count - long_count

    cumulative_stats['cycles'] = cycle_count
    cumulative_stats['last_total'] = total_count
    cumulative_stats['last_volume'] = total_vol

    # ==================== SUMMARY BAR ====================
    summary = Text()
    summary.append("  ₿ BTC LIQUIDATION STREAM (1H)  ", style="bold bright_yellow")
    summary.append("| ", style="dim")
    summary.append(f"Total: {total_count}", style="bold white")
    summary.append(f" ({format_usd(total_vol)})", style="bold bright_yellow")
    summary.append(" | ", style="dim")
    summary.append(f"LONGS: {long_count}", style=BULL_COLOR)
    summary.append(" | ", style="dim")
    summary.append(f"SHORTS: {short_count}", style=BEAR_COLOR)

    if total_count > 0:
        long_pct = long_count / total_count * 100
        summary.append(" | ", style="dim")
        if long_pct > 60:
            summary.append(f"LONGS GETTING REKT ({long_pct:.0f}%)", style=f"bold {BEAR_COLOR}")
        elif long_pct < 40:
            summary.append(f"SHORTS GETTING REKT ({100-long_pct:.0f}%)", style=f"bold {BULL_COLOR}")
        else:
            summary.append(f"BALANCED ({long_pct:.0f}%L / {100-long_pct:.0f}%S)", style=WARN_COLOR)

    output.append(Panel(summary, border_style="bright_yellow", box=box.HEAVY, padding=(0, 0)))

    # ==================== MAIN LIQUIDATION TAPE ====================
    if all_btc_liqs:
        tape = Table(
            title=f"[bold bright_red]🔥 BTC LIQUIDATION FEED - ALL EXCHANGES (Last 1H) | {len(all_btc_liqs)} Events[/]",
            box=box.HEAVY_EDGE,
            border_style="bright_red",
            header_style="bold bright_white on dark_red",
            show_lines=True,
            padding=(0, 1),
            expand=True,
        )
        tape.add_column("#", style="dim", width=3)
        tape.add_column("EXCHANGE", justify="center", width=14)
        tape.add_column("SIDE", justify="center", width=10)
        tape.add_column("VALUE", style="bold bright_yellow", justify="right", width=14)
        tape.add_column("PRICE", justify="right", width=14)
        tape.add_column("QTY", justify="right", width=12)
        tape.add_column("TIME", style="dim", width=12)
        tape.add_column("IMPACT", justify="center", width=14)

        for i, liq in enumerate(all_btc_liqs[:30], 1):
            exchange = liq.get('_exchange', liq.get('exchange', liq.get('source', 'unknown')))
            style = get_exchange_style(exchange)
            ex_display = f"{style['emoji']} [{style['color']}]{style['name'][:8]}[/{style['color']}]"

            side = str(liq.get('side', liq.get('direction', '?'))).upper()
            if side in ['LONG', 'BUY', 'B']:
                side_display = f"[{BULL_COLOR}]📈 LONG[/]"
            else:
                side_display = f"[{BEAR_COLOR}]📉 SHORT[/]"

            value = float(liq.get('value', liq.get('usd_value', liq.get('value_usd',
                         liq.get('quantity', liq.get('usd_size', 0))))))
            price = float(liq.get('price', liq.get('px', 0)))
            qty = float(liq.get('quantity', liq.get('sz', liq.get('size', liq.get('amount', 0)))))
            timestamp = liq.get('timestamp', liq.get('time', ''))

            time_str = "N/A"
            if timestamp:
                if isinstance(timestamp, str) and 'T' in timestamp:
                    time_str = timestamp.split('T')[1].split('.')[0]
                elif isinstance(timestamp, (int, float)):
                    time_str = datetime.fromtimestamp(timestamp / 1000 if timestamp > 1e10 else timestamp).strftime("%H:%M:%S")
                else:
                    time_str = str(timestamp)[:8]

            # Impact visual
            if value >= 1_000_000:
                impact = f"[bold bright_yellow on red] 🐋🐋🐋 MEGA [/]"
            elif value >= 500_000:
                impact = f"[bold bright_yellow] 🐋🐋 WHALE [/]"
            elif value >= 100_000:
                impact = f"[bold bright_yellow] 🐋 BIG [/]"
            elif value >= 50_000:
                impact = f"[{WARN_COLOR}] ⚡ NOTABLE [/]"
            else:
                impact = f"[dim] · normal [/]"

            # Rank emoji
            rank = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else str(i)

            qty_str = f"{qty:,.4f}" if qty < 10 else f"{qty:,.2f}" if qty < 1000 else f"{qty:,.0f}"

            tape.add_row(
                rank, ex_display, side_display,
                f"[bold]{format_usd(value)}[/]",
                format_price(price), qty_str,
                time_str, impact,
            )

        output.append(tape)
    else:
        output.append(Panel(
            "[dim]  No BTC liquidations found in the last hour. The market is calm... for now. 🌙[/]",
            border_style="dim", padding=(0, 1)
        ))

    # ==================== LONG/SHORT RATIO BAR ====================
    if total_count > 0:
        long_pct = long_count / total_count
        bar_width = 50
        long_bars = int(long_pct * bar_width)
        short_bars = bar_width - long_bars

        ratio_text = Text()
        ratio_text.append("  📈 LONGS ", style=f"bold {BULL_COLOR}")
        ratio_text.append("█" * long_bars, style=BULL_COLOR)
        ratio_text.append("█" * short_bars, style=BEAR_COLOR)
        ratio_text.append(" SHORTS 📉", style=f"bold {BEAR_COLOR}")
        output.append(Panel(
            Align.center(ratio_text),
            title=f"[bold white]Long/Short Ratio: {long_pct*100:.1f}% / {(1-long_pct)*100:.1f}%[/]",
            border_style="bright_magenta",
            padding=(0, 0)
        ))

    # ==================== TIMEFRAME COMPARISON (DAY TRADING: 1m, 5m, 10m, 15m) ====================
    # Fetch 10m data once for 1m/5m/10m, and 1h data for 15m (then chop)
    try:
        raw_10m = api.get_all_liquidations("10m")
    except Exception as e:
        print(f"🌙 Moon Dev: 10m fetch hiccup - {e}")
        raw_10m = []
    btc_10m_all = filter_btc(extract_liquidations(raw_10m, "all"))

    try:
        raw_1h = api.get_all_liquidations("1h")
    except Exception as e:
        print(f"🌙 Moon Dev: 1h fetch hiccup - {e}")
        raw_1h = []
    btc_1h_all = filter_btc(extract_liquidations(raw_1h, "all"))

    tf_table = Table(
        title="[bold bright_cyan]⏰ BTC LIQUIDATIONS BY TIMEFRAME (DAY TRADING VIEW)[/]",
        box=box.HEAVY_EDGE,
        border_style="bright_cyan",
        header_style="bold bright_white on dark_blue",
        show_lines=True,
        padding=(0, 1),
        expand=True,
    )
    tf_table.add_column("TIMEFRAME", style="bold", justify="center", width=12)
    tf_table.add_column("TOTAL VOL", style="bold bright_yellow", justify="right", width=16)
    tf_table.add_column("📈 LONGS LIQUIDATED", style=BULL_COLOR, justify="right", width=20)
    tf_table.add_column("📉 SHORTS LIQUIDATED", style=BEAR_COLOR, justify="right", width=20)

    for minutes, label, source in [
        (1, "⚡ 1 MIN", btc_10m_all),
        (5, "🔥 5 MIN", btc_10m_all),
        (10, "📊 10 MIN", btc_10m_all),
        (15, "🌊 15 MIN", btc_1h_all),
    ]:
        btc_tf = filter_by_minutes(source, minutes)
        get_val = lambda l: float(l.get('value', l.get('usd_value', l.get('value_usd', l.get('usd_size', 0)))))
        is_long_side = lambda l: str(l.get('side', l.get('direction', ''))).lower() in ['long', 'buy', 'b']
        vol = sum(get_val(l) for l in btc_tf)
        long_vol = sum(get_val(l) for l in btc_tf if is_long_side(l))
        short_vol = vol - long_vol
        tf_table.add_row(label, format_usd(vol), format_usd(long_vol), format_usd(short_vol))

    output.append(tf_table)

    # ==================== FOOTER ====================
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    footer = Text()
    footer.append(f"  🌙 Moon Dev's BTC Liquidation Stream", style="bold bright_yellow")
    footer.append(f" | ", style="dim")
    footer.append(f"Refresh: {REFRESH_SECONDS}s", style="dim")
    footer.append(f" | Cycle: #{cycle_count}", style="bold white")
    footer.append(f" | {now}", style="dim")
    footer.append(f" | moondev.com", style="bold bright_magenta")
    footer.append(f" | Ctrl+C to exit", style="dim")
    output.append(Panel(footer, border_style="bright_yellow", box=box.ROUNDED, padding=(0, 0)))

    return Group(*output)


def main():
    """🌙 Moon Dev's BTC Liquidation Stream - All Exchanges"""
    console = Console()
    console.clear()
    console.print(create_header())
    console.print("\n[bold bright_yellow]  🌙 Moon Dev:[/] Initializing BTC Liquidation Stream...")

    api = MoonDevAPI()
    if not api.api_key:
        console.print("[bold red]  ❌ No API key found! Set MOONDEV_API_KEY in your .env file[/]")
        return

    console.print(f"[bold {BULL_COLOR}]  ✅ Moon Dev API connected[/]")
    console.print(f"[bold bright_yellow]  ₿  Streaming: BTC liquidations across ALL exchanges[/]")
    console.print(f"[bold bright_cyan]  🔄 Refresh rate: {REFRESH_SECONDS}s[/]")
    console.print(f"[dim]  📡 Watching: Hyperliquid, Binance, Bybit, OKX[/]\n")

    cycle_count = 0
    cumulative_stats = {}

    with Live(console=console, refresh_per_second=1, vertical_overflow="visible") as live:
        while True:
            cycle_count += 1
            try:
                dashboard = build_dashboard(api, cycle_count, cumulative_stats)
                live.update(dashboard)
            except Exception as e:
                console.print(f"[bold yellow]  🌙 Moon Dev: Dashboard cycle #{cycle_count} hiccup, retrying next cycle - {e}[/]")
            time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    print("🌙 Moon Dev's BTC Liquidation Stream - Starting up...")
    print("🌙 Moon Dev says: Watching Bitcoin liquidations across every exchange. Let's see who's getting rekt.\n")
    main()
