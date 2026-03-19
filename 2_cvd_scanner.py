"""
🌙 Moon Dev's CVD (Cumulative Volume Delta) Scanner
Built with love by Moon Dev 🚀

THE order flow cheat code. See who's aggressive. See divergences.
Nobody else has this tick data. This is alpha.

Usage:
    python 28_cvd_scanner.py

Author: Moon Dev
"""

import sys
import os
import time
from datetime import datetime
from collections import defaultdict

# Add parent directory to path so we can import api.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api import MoonDevAPI

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.layout import Layout
from rich.live import Live
from rich import box
from rich.align import Align

# ==================== MOON DEV CONFIGURATION ====================
SYMBOLS = ["BTC", "ETH", "HYPE", "SOL", "XRP"]
SYMBOL_EMOJIS = {"BTC": "₿", "ETH": "Ξ", "HYPE": "⚡", "SOL": "◎", "XRP": "✕"}
REFRESH_SECONDS = 5
TICK_DURATION = "1h"  # pull last hour of ticks for richer CVD sparklines
SPARKLINE_WIDTH = 30
CVD_BAR_WIDTH = 24

# Colors for the vibes
BULL_COLOR = "bright_green"
BEAR_COLOR = "bright_red"
NEUTRAL_COLOR = "bright_yellow"
STRONG_BULL = "bold bright_green"
STRONG_BEAR = "bold bright_red"
DIVERGENCE_COLOR = "bold bright_magenta"


def format_price(price):
    """Format price with commas and proper decimals - Moon Dev style"""
    if price is None or price == 0:
        return "N/A"
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:,.4f}"
    else:
        return f"${price:,.6f}"


def format_volume(value):
    """Format volume with K/M/B suffixes - Moon Dev style"""
    if value is None:
        return "$0"
    neg = value < 0
    value = abs(value)
    if value >= 1_000_000_000:
        result = f"${value/1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        result = f"${value/1_000_000:.2f}M"
    elif value >= 1_000:
        result = f"${value/1_000:.1f}K"
    else:
        result = f"${value:.0f}"
    return f"-{result}" if neg else result


def create_sparkline(prices, width=SPARKLINE_WIDTH):
    """Create ASCII sparkline from price data - Moon Dev's mini chart"""
    if not prices or len(prices) < 2:
        return "▄" * width, "dim"

    min_p = min(prices)
    max_p = max(prices)
    if max_p == min_p:
        return "▄" * min(len(prices), width), "dim"

    chars = "▁▂▃▄▅▆▇█"
    step = max(1, len(prices) // width)
    sampled = prices[::step][:width]
    sparkline = ""
    for p in sampled:
        normalized = (p - min_p) / (max_p - min_p)
        idx = int(normalized * (len(chars) - 1))
        sparkline += chars[idx]

    # Color based on trend
    color = BULL_COLOR if prices[-1] > prices[0] else BEAR_COLOR if prices[-1] < prices[0] else "dim"
    return sparkline, color


def create_cvd_sparkline(deltas, width=SPARKLINE_WIDTH):
    """Create ASCII sparkline from CVD data - shows accumulation of delta"""
    if not deltas or len(deltas) < 2:
        return "▄" * width, "dim"

    # Build cumulative from deltas
    cumulative = []
    running = 0
    for d in deltas:
        running += d
        cumulative.append(running)

    min_c = min(cumulative)
    max_c = max(cumulative)
    if max_c == min_c:
        return "▄" * min(len(cumulative), width), "dim"

    chars = "▁▂▃▄▅▆▇█"
    step = max(1, len(cumulative) // width)
    sampled = cumulative[::step][:width]
    sparkline = ""
    for c in sampled:
        normalized = (c - min_c) / (max_c - min_c)
        idx = int(normalized * (len(chars) - 1))
        sparkline += chars[idx]

    color = BULL_COLOR if cumulative[-1] > 0 else BEAR_COLOR
    return sparkline, color


def create_pressure_bar(buy_pct, width=CVD_BAR_WIDTH):
    """Create visual buy/sell pressure bar with gradient feel"""
    filled = int(width * buy_pct)
    empty = width - filled

    if buy_pct >= 0.60:
        buy_char = "█"
        color = STRONG_BULL
        label = "BUYERS DOMINATE"
    elif buy_pct >= 0.55:
        buy_char = "█"
        color = BULL_COLOR
        label = "BUYERS LEAN"
    elif buy_pct <= 0.40:
        buy_char = "█"
        color = STRONG_BEAR
        label = "SELLERS DOMINATE"
    elif buy_pct <= 0.45:
        buy_char = "█"
        color = BEAR_COLOR
        label = "SELLERS LEAN"
    else:
        buy_char = "█"
        color = NEUTRAL_COLOR
        label = "CONTESTED"

    bar = f"[{BULL_COLOR}]{buy_char * filled}[/][{BEAR_COLOR}]{'█' * empty}[/]"
    return bar, f"{buy_pct*100:.1f}%", label, color


def compute_tick_cvd(ticks):
    """
    Compute CVD from tick data using the tick rule:
    - Price uptick = aggressive buy (buyer lifted the ask)
    - Price downtick = aggressive sell (seller hit the bid)
    - Unchanged = use last known direction

    Returns: cvd_value, price_change_pct, deltas list, prices list
    """
    if not ticks or len(ticks) < 2:
        return 0, 0, [], []

    prices = [t.get('p', t.get('price', 0)) for t in ticks]
    cvd = 0
    deltas = []
    last_direction = 0  # 0 = neutral, 1 = buy, -1 = sell

    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        if diff > 0:
            last_direction = 1
            delta = 1
        elif diff < 0:
            last_direction = -1
            delta = -1
        else:
            delta = last_direction  # use last known direction

        cvd += delta
        deltas.append(delta)

    price_change = ((prices[-1] - prices[0]) / prices[0] * 100) if prices[0] != 0 else 0
    return cvd, price_change, deltas, prices


def detect_divergence(price_change, cvd_value):
    """
    Detect divergence between price and CVD.
    Returns: (divergence_type, signal_text, color)
    """
    if abs(price_change) < 0.01 and abs(cvd_value) < 5:
        return None, "", "dim"

    # Price up but CVD negative = bearish divergence (sellers aggressive, price still up)
    if price_change > 0.02 and cvd_value < -10:
        return "BEARISH_DIV", "BEARISH DIV", DIVERGENCE_COLOR

    # Price down but CVD positive = bullish divergence (buyers aggressive, price still down)
    if price_change < -0.02 and cvd_value > 10:
        return "BULLISH_DIV", "BULLISH DIV", DIVERGENCE_COLOR

    # Strong alignment
    if price_change > 0.05 and cvd_value > 20:
        return "STRONG_BULL", "STRONG BULL", STRONG_BULL

    if price_change < -0.05 and cvd_value < -20:
        return "STRONG_BEAR", "STRONG BEAR", STRONG_BEAR

    # Mild alignment
    if price_change > 0 and cvd_value > 0:
        return "BULLISH", "BULLISH", BULL_COLOR

    if price_change < 0 and cvd_value < 0:
        return "BEARISH", "BEARISH", BEAR_COLOR

    return "NEUTRAL", "NEUTRAL", NEUTRAL_COLOR


def create_header():
    """Create the Moon Dev CVD Scanner banner"""
    banner = """   ██████╗██╗   ██╗██████╗     ███████╗ ██████╗ █████╗ ███╗   ██╗███╗   ██╗███████╗██████╗
  ██╔════╝██║   ██║██╔══██╗    ██╔════╝██╔════╝██╔══██╗████╗  ██║████╗  ██║██╔════╝██╔══██╗
  ██║     ██║   ██║██║  ██║    ███████╗██║     ███████║██╔██╗ ██║██╔██╗ ██║█████╗  ██████╔╝
  ██║     ╚██╗ ██╔╝██║  ██║    ╚════██║██║     ██╔══██║██║╚██╗██║██║╚██╗██║██╔══╝  ██╔══██╗
  ╚██████╗ ╚████╔╝ ██████╔╝    ███████║╚██████╗██║  ██║██║ ╚████║██║ ╚████║███████╗██║  ██║
   ╚═════╝  ╚═══╝  ╚═════╝     ╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝"""
    return Panel(
        Align.center(Text(banner, style="bold bright_cyan")),
        title="🌙 [bold bright_magenta]MOON DEV's CVD SCANNER[/bold bright_magenta] 🌙",
        subtitle="[bold bright_yellow]Cumulative Volume Delta | Order Flow Alpha | Tick-Level Intelligence[/bold bright_yellow]",
        border_style="bright_cyan",
        box=box.DOUBLE_EDGE,
        padding=(0, 1)
    )


def create_legend():
    """Create a compact legend explaining signals"""
    legend = Text()
    legend.append("  SIGNALS: ", style="bold white")
    legend.append("██ ", style=STRONG_BULL)
    legend.append("STRONG BULL  ", style="dim")
    legend.append("██ ", style=BULL_COLOR)
    legend.append("BULLISH  ", style="dim")
    legend.append("██ ", style=NEUTRAL_COLOR)
    legend.append("CONTESTED  ", style="dim")
    legend.append("██ ", style=BEAR_COLOR)
    legend.append("BEARISH  ", style="dim")
    legend.append("██ ", style=STRONG_BEAR)
    legend.append("STRONG BEAR  ", style="dim")
    legend.append("██ ", style=DIVERGENCE_COLOR)
    legend.append("DIVERGENCE (alpha!)", style="dim")
    return Panel(legend, border_style="bright_cyan", box=box.ROUNDED, padding=(0, 0))


def build_dashboard(api, console, cycle_count):
    """Build the full CVD dashboard - Moon Dev's alpha machine"""

    # ==================== FETCH ALL DATA ====================
    # Tick data for each symbol (CVD calculation)
    tick_data = {}
    for symbol in SYMBOLS:
        tick_response = api.get_ticks(symbol, TICK_DURATION, limit=10000)
        if tick_response and isinstance(tick_response, dict):
            tick_data[symbol] = tick_response.get('ticks', [])

    # Order flow data (real buy/sell side data)
    orderflow = api.get_orderflow()
    of_stats = api.get_orderflow_stats()

    # Imbalance across timeframes
    imbalances = {}
    for tf in ['5m', '15m', '1h', '4h']:
        imb = api.get_imbalance(tf)
        if imb:
            imbalances[tf] = imb

    # Recent trades for live flow
    trades_data = api.get_trades()
    trades = []
    if isinstance(trades_data, dict):
        trades = trades_data.get('trades', [])
    elif isinstance(trades_data, list):
        trades = trades_data

    # Latest prices
    latest_data = api.get_tick_latest()
    latest_prices = latest_data.get('prices', {}) if latest_data else {}

    # ==================== BUILD OUTPUT ====================
    output = []

    # Header
    output.append(create_header())
    output.append(create_legend())

    # ==================== OVERVIEW STATS BAR ====================
    if of_stats:
        total_trades = of_stats.get('total_trades', 0)
        total_vol = of_stats.get('total_volume_usd', 0)
        buy_vol = of_stats.get('buy_volume_usd', 0)
        sell_vol = of_stats.get('sell_volume_usd', 0)
        tps = of_stats.get('trades_per_second', 0)
        overall_buy_pct = (buy_vol / total_vol) if total_vol > 0 else 0.5

        overview = Text()
        overview.append("  🌙 Moon Dev CVD Scanner ", style="bold bright_cyan")
        overview.append("| ", style="dim")
        overview.append(f"Trades: ", style="dim")
        overview.append(f"{total_trades:,}", style="bold white")
        overview.append(" | Vol: ", style="dim")
        overview.append(f"{format_volume(total_vol)}", style="bold bright_yellow")
        overview.append(" | ", style="dim")
        overview.append(f"BUY {format_volume(buy_vol)}", style=BULL_COLOR)
        overview.append(" vs ", style="dim")
        overview.append(f"SELL {format_volume(sell_vol)}", style=BEAR_COLOR)
        overview.append(" | ", style="dim")
        overview.append(f"{tps:.1f} trades/sec", style="bold white")
        overview.append(" | ", style="dim")

        if overall_buy_pct >= 0.55:
            overview.append(f"BUYERS {overall_buy_pct*100:.0f}%", style=STRONG_BULL)
        elif overall_buy_pct <= 0.45:
            overview.append(f"SELLERS {(1-overall_buy_pct)*100:.0f}%", style=STRONG_BEAR)
        else:
            overview.append(f"BALANCED {overall_buy_pct*100:.0f}%", style=NEUTRAL_COLOR)

        output.append(Panel(overview, border_style="bright_yellow", box=box.HEAVY, padding=(0, 0)))

    # ==================== MAIN CVD TABLE (THE ALPHA) ====================
    cvd_table = Table(
        title="[bold bright_magenta]⚡ TICK-LEVEL CVD ANALYSIS ⚡[/]  [dim]Nobody else has this data[/]",
        box=box.HEAVY_EDGE,
        border_style="bright_magenta",
        header_style="bold bright_white on dark_magenta",
        show_lines=True,
        padding=(0, 1),
        expand=True,
    )

    cvd_table.add_column("COIN", style="bold bright_white", justify="center", width=6)
    cvd_table.add_column("PRICE", style="bold bright_white", justify="right", width=14)
    cvd_table.add_column("CHG%", justify="right", width=8)
    cvd_table.add_column("CVD", justify="right", width=8)
    cvd_table.add_column("PRICE ACTION", justify="center", width=SPARKLINE_WIDTH + 2)
    cvd_table.add_column("CVD FLOW", justify="center", width=SPARKLINE_WIDTH + 2)
    cvd_table.add_column("SIGNAL", justify="center", width=14)
    cvd_table.add_column("TICKS", style="dim", justify="right", width=6)

    for symbol in SYMBOLS:
        emoji = SYMBOL_EMOJIS.get(symbol, "•")
        ticks = tick_data.get(symbol, [])
        price = latest_prices.get(symbol, 0)

        cvd_value, price_change, deltas, prices = compute_tick_cvd(ticks)

        # Price sparkline
        price_spark, price_color = create_sparkline(prices)
        # CVD sparkline
        cvd_spark, cvd_color = create_cvd_sparkline(deltas)

        # Detect divergence
        div_type, signal_text, signal_color = detect_divergence(price_change, cvd_value)

        # Price change display
        if price_change > 0:
            chg_str = f"[{BULL_COLOR}]+{price_change:.3f}%[/]"
        elif price_change < 0:
            chg_str = f"[{BEAR_COLOR}]{price_change:.3f}%[/]"
        else:
            chg_str = "[dim]0.000%[/]"

        # CVD value display
        if cvd_value > 0:
            cvd_str = f"[{BULL_COLOR}]+{cvd_value}[/]"
        elif cvd_value < 0:
            cvd_str = f"[{BEAR_COLOR}]{cvd_value}[/]"
        else:
            cvd_str = "[dim]0[/]"

        # Signal with flash for divergences
        if div_type and "DIV" in div_type:
            signal_display = f"[{signal_color}]>>> {signal_text} <<<[/]"
        elif div_type and "STRONG" in div_type:
            signal_display = f"[{signal_color}]{signal_text}[/]"
        else:
            signal_display = f"[{signal_color}]{signal_text}[/]"

        cvd_table.add_row(
            f"{emoji} {symbol}",
            format_price(price),
            chg_str,
            cvd_str,
            f"[{price_color}]{price_spark}[/]",
            f"[{cvd_color}]{cvd_spark}[/]",
            signal_display,
            f"{len(ticks):,}",
        )

    output.append(cvd_table)

    # ==================== ORDER FLOW PRESSURE BY COIN ====================
    if orderflow:
        by_coin = orderflow.get('by_coin', {})
        if by_coin:
            pressure_table = Table(
                title="[bold bright_cyan]🔥 REAL-TIME BUY/SELL PRESSURE BY COIN[/]  [dim]Who is the aggressor?[/]",
                box=box.HEAVY_EDGE,
                border_style="bright_cyan",
                header_style="bold bright_white on dark_blue",
                show_lines=True,
                padding=(0, 1),
                expand=True,
            )
            pressure_table.add_column("COIN", style="bold", justify="center", width=6)
            pressure_table.add_column("BUY ◄══════ PRESSURE BAR ══════► SELL", justify="center", width=CVD_BAR_WIDTH + 8)
            pressure_table.add_column("BUY%", justify="center", width=7)
            pressure_table.add_column("DELTA", justify="right", width=12)
            pressure_table.add_column("VERDICT", justify="center", width=18)

            for symbol in SYMBOLS:
                emoji = SYMBOL_EMOJIS.get(symbol, "•")
                coin_data = by_coin.get(symbol, {})
                buy_pressure = coin_data.get('buy_pressure', 0.5)
                delta = coin_data.get('cumulative_delta', 0)

                bar, pct_str, label, color = create_pressure_bar(buy_pressure)

                # Delta display
                if delta > 0:
                    delta_str = f"[{BULL_COLOR}]+{format_volume(delta)}[/]"
                elif delta < 0:
                    delta_str = f"[{BEAR_COLOR}]{format_volume(delta)}[/]"
                else:
                    delta_str = "[dim]$0[/]"

                pressure_table.add_row(
                    f"{emoji} {symbol}",
                    bar,
                    f"[{color}]{pct_str}[/]",
                    delta_str,
                    f"[{color}]{label}[/]",
                )

            output.append(pressure_table)

    # ==================== MULTI-TIMEFRAME CVD ====================
    if orderflow:
        windows = orderflow.get('windows', {})
        if windows:
            tf_table = Table(
                title="[bold bright_yellow]📊 MULTI-TIMEFRAME ORDER FLOW[/]  [dim]Zoom in and out on aggression[/]",
                box=box.HEAVY_EDGE,
                border_style="bright_yellow",
                header_style="bold bright_white on rgb(100,80,0)",
                show_lines=True,
                padding=(0, 1),
                expand=True,
            )
            tf_table.add_column("TIMEFRAME", style="bold bright_white", justify="center", width=10)
            tf_table.add_column("BUY ◄══ PRESSURE ══► SELL", justify="center", width=CVD_BAR_WIDTH + 8)
            tf_table.add_column("BUY%", justify="center", width=7)
            tf_table.add_column("CUM DELTA", justify="right", width=12)
            tf_table.add_column("DOMINANT", justify="center", width=16)

            for tf in ['5m', '15m', '1h', '4h']:
                data = windows.get(tf, {})
                buy_pressure = data.get('buy_pressure', 0.5)
                delta = data.get('cumulative_delta', 0)
                dominant = data.get('dominant_side', 'NEUTRAL')

                bar, pct_str, label, color = create_pressure_bar(buy_pressure)

                if delta > 0:
                    delta_str = f"[{BULL_COLOR}]+{format_volume(delta)}[/]"
                elif delta < 0:
                    delta_str = f"[{BEAR_COLOR}]{format_volume(delta)}[/]"
                else:
                    delta_str = "[dim]$0[/]"

                if dominant == 'BUY':
                    dom_str = f"[{STRONG_BULL}]BUYERS ▲[/]"
                elif dominant == 'SELL':
                    dom_str = f"[{STRONG_BEAR}]SELLERS ▼[/]"
                else:
                    dom_str = f"[{NEUTRAL_COLOR}]NEUTRAL ═[/]"

                tf_label = {"5m": "⚡ 5 MIN", "15m": "🔥 15 MIN", "1h": "📊 1 HOUR", "4h": "🌊 4 HOUR"}.get(tf, tf)
                tf_table.add_row(tf_label, bar, f"[{color}]{pct_str}[/]", delta_str, dom_str)

            output.append(tf_table)

    # ==================== PER-COIN MULTI-TIMEFRAME CVD HEATMAP (THE REAL ALPHA) ====================
    if imbalances:
        heatmap_table = Table(
            title="[bold bright_white on dark_red]🎯 DOLLAR CVD HEATMAP BY COIN × TIMEFRAME 🎯[/]  [dim]Real $ aggression across time[/]",
            box=box.HEAVY_EDGE,
            border_style="bright_red",
            header_style="bold bright_white on dark_red",
            show_lines=True,
            padding=(0, 1),
            expand=True,
        )
        heatmap_table.add_column("COIN", style="bold bright_white", justify="center", width=6)

        for tf in ['5m', '15m', '1h', '4h']:
            heatmap_table.add_column(f"{tf} NET $", justify="right", width=12)
            heatmap_table.add_column(f"{tf} BIAS", justify="center", width=10)

        for symbol in SYMBOLS:
            emoji = SYMBOL_EMOJIS.get(symbol, "•")
            row = [f"{emoji} {symbol}"]

            for tf in ['5m', '15m', '1h', '4h']:
                imb = imbalances.get(tf, {})
                by_coin = imb.get('by_coin', {})
                coin_imb = by_coin.get(symbol, {})

                buy_vol = coin_imb.get('buy_volume_usd', 0)
                sell_vol = coin_imb.get('sell_volume_usd', 0)
                net = coin_imb.get('net_imbalance_usd', buy_vol - sell_vol)
                ratio = coin_imb.get('imbalance_ratio', 0)

                # Net $ display with color intensity
                if net > 0:
                    if ratio > 0.5:
                        net_str = f"[{STRONG_BULL}]+{format_volume(net)}[/]"
                    else:
                        net_str = f"[{BULL_COLOR}]+{format_volume(net)}[/]"
                elif net < 0:
                    if ratio < -0.5:
                        net_str = f"[{STRONG_BEAR}]{format_volume(net)}[/]"
                    else:
                        net_str = f"[{BEAR_COLOR}]{format_volume(net)}[/]"
                else:
                    net_str = "[dim]$0[/]"

                # Visual bias indicator with bars
                if ratio > 0.5:
                    bias = f"[{STRONG_BULL}]▲▲▲ BUY[/]"
                elif ratio > 0.2:
                    bias = f"[{BULL_COLOR}]▲▲  BUY[/]"
                elif ratio > 0.05:
                    bias = f"[{BULL_COLOR}]▲   BUY[/]"
                elif ratio < -0.5:
                    bias = f"[{STRONG_BEAR}]▼▼▼ SELL[/]"
                elif ratio < -0.2:
                    bias = f"[{BEAR_COLOR}]▼▼  SELL[/]"
                elif ratio < -0.05:
                    bias = f"[{BEAR_COLOR}]▼   SELL[/]"
                else:
                    bias = f"[{NEUTRAL_COLOR}]═   FLAT[/]"

                row.append(net_str)
                row.append(bias)

            heatmap_table.add_row(*row)

        output.append(heatmap_table)

    # ==================== LIVE TRADE TAPE (LAST 15 TRADES) ====================
    if trades:
        tape_table = Table(
            title="[bold bright_green]💹 LIVE TRADE TAPE[/]  [dim]Real-time aggressor flow[/]",
            box=box.HEAVY_EDGE,
            border_style="bright_green",
            header_style="bold bright_white on dark_green",
            show_lines=False,
            padding=(0, 1),
            expand=True,
        )
        tape_table.add_column("TIME", style="dim", justify="center", width=10)
        tape_table.add_column("COIN", style="bold bright_white", justify="center", width=6)
        tape_table.add_column("SIDE", justify="center", width=12)
        tape_table.add_column("SIZE", justify="right", width=12)
        tape_table.add_column("PRICE", justify="right", width=14)
        tape_table.add_column("VALUE", style="bold bright_yellow", justify="right", width=12)
        tape_table.add_column("FLOW", justify="center", width=12)

        for trade in trades[:15]:
            timestamp = trade.get('timestamp', '')
            coin = trade.get('coin', '?')
            side = trade.get('side', '?').upper()
            size = float(trade.get('size', trade.get('sz', 0)))
            price = float(trade.get('price', trade.get('px', 0)))
            value = float(trade.get('value_usd', trade.get('value', size * price)))

            time_str = "N/A"
            if timestamp:
                if isinstance(timestamp, str) and 'T' in timestamp:
                    time_str = timestamp.split('T')[1].split('.')[0]
                elif isinstance(timestamp, (int, float)):
                    time_str = datetime.fromtimestamp(timestamp / 1000 if timestamp > 1e10 else timestamp).strftime("%H:%M:%S")

            if side in ["BUY", "B"]:
                side_display = f"[{STRONG_BULL}]▲ BUY[/]"
                flow_display = f"[{BULL_COLOR}]{'█' * min(int(value / 10000) + 1, 10)}[/]"
            else:
                side_display = f"[{STRONG_BEAR}]▼ SELL[/]"
                flow_display = f"[{BEAR_COLOR}]{'█' * min(int(value / 10000) + 1, 10)}[/]"

            # Highlight whales
            if value >= 100_000:
                value_str = f"[bold bright_yellow on red] 🐋 {format_volume(value)} [/]"
            elif value >= 50_000:
                value_str = f"[bold bright_yellow]{format_volume(value)}[/]"
            else:
                value_str = format_volume(value)

            tape_table.add_row(
                time_str,
                f"{SYMBOL_EMOJIS.get(coin, '•')}{coin}",
                side_display,
                f"{size:,.4f}" if size < 1000 else f"{size:,.2f}",
                format_price(price),
                value_str,
                flow_display,
            )

        output.append(tape_table)

    # ==================== DIVERGENCE ALERTS ====================
    alerts = []
    for symbol in SYMBOLS:
        emoji = SYMBOL_EMOJIS.get(symbol, "•")
        ticks = tick_data.get(symbol, [])
        cvd_value, price_change, deltas, prices = compute_tick_cvd(ticks)
        div_type, signal_text, signal_color = detect_divergence(price_change, cvd_value)

        # Tick-level divergence
        if div_type and "DIV" in div_type:
            if "BULLISH" in div_type:
                alert_text = f"  {emoji} {symbol}: Price DOWN {price_change:+.3f}% but CVD is POSITIVE (+{cvd_value}) - Buyers aggressive despite price drop = potential ACCUMULATION"
                alerts.append(f"[{DIVERGENCE_COLOR}]{alert_text}[/]")
            else:
                alert_text = f"  {emoji} {symbol}: Price UP {price_change:+.3f}% but CVD is NEGATIVE ({cvd_value}) - Sellers aggressive despite price rise = potential DISTRIBUTION"
                alerts.append(f"[{DIVERGENCE_COLOR}]{alert_text}[/]")

        # Dollar-level divergence: check if 5m and 1h disagree (timeframe flip)
        if imbalances.get('5m') and imbalances.get('1h'):
            short_coin = imbalances['5m'].get('by_coin', {}).get(symbol, {})
            long_coin = imbalances['1h'].get('by_coin', {}).get(symbol, {})
            short_ratio = short_coin.get('imbalance_ratio', 0)
            long_ratio = long_coin.get('imbalance_ratio', 0)
            short_net = short_coin.get('net_imbalance_usd', 0)
            long_net = long_coin.get('net_imbalance_usd', 0)

            # Short-term buyers flipping against long-term sellers (or vice versa)
            if short_ratio > 0.3 and long_ratio < -0.2:
                alert_text = f"  {emoji} {symbol}: 5m BUYING (+{format_volume(short_net)}) vs 1h SELLING ({format_volume(long_net)}) - Short-term reversal attempt against trend"
                alerts.append(f"[bold bright_yellow]{alert_text}[/]")
            elif short_ratio < -0.3 and long_ratio > 0.2:
                alert_text = f"  {emoji} {symbol}: 5m SELLING ({format_volume(short_net)}) vs 1h BUYING (+{format_volume(long_net)}) - Short-term pullback in uptrend"
                alerts.append(f"[bold bright_yellow]{alert_text}[/]")

    if alerts:
        alert_content = Text()
        alert_content.append("  🚨 DIVERGENCE DETECTED - THIS IS ALPHA 🚨\n\n", style="bold bright_magenta blink")
        for alert in alerts:
            alert_content.append(alert + "\n")
        output.append(Panel(
            alert_content,
            title="[bold bright_magenta]⚡ DIVERGENCE ALERTS ⚡[/]",
            border_style="bright_magenta",
            box=box.DOUBLE_EDGE,
            padding=(0, 1)
        ))
    else:
        output.append(Panel(
            "  [dim]No divergences detected right now. Price and CVD are aligned. Watching...[/]",
            title="[dim]Divergence Monitor[/]",
            border_style="dim",
            box=box.ROUNDED,
            padding=(0, 0)
        ))

    # ==================== FOOTER ====================
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    footer = Text()
    footer.append(f"  🌙 Moon Dev's CVD Scanner", style="bold bright_cyan")
    footer.append(f" | ", style="dim")
    footer.append(f"Refresh: {REFRESH_SECONDS}s", style="dim")
    footer.append(f" | ", style="dim")
    footer.append(f"Cycle: #{cycle_count}", style="bold white")
    footer.append(f" | ", style="dim")
    footer.append(f"{now}", style="dim")
    footer.append(f" | ", style="dim")
    footer.append(f"moondev.com", style="bold bright_magenta")
    footer.append(f" | ", style="dim")
    footer.append(f"Ctrl+C to exit", style="dim")
    output.append(Panel(footer, border_style="bright_cyan", box=box.ROUNDED, padding=(0, 0)))

    return Group(*output)


def main():
    """🌙 Moon Dev's CVD Scanner - The Order Flow Cheat Code"""
    console = Console()

    # Init
    console.clear()
    console.print(create_header())
    console.print("\n[bold bright_cyan]  🌙 Moon Dev:[/] Initializing CVD Scanner...")

    api = MoonDevAPI()
    if not api.api_key:
        console.print("[bold red]  ❌ No API key found! Set MOONDEV_API_KEY in your .env file[/]")
        return

    console.print(f"[bold bright_green]  ✅ Moon Dev API connected[/]")
    console.print(f"[bold bright_yellow]  ⚡ Scanning: {', '.join(SYMBOLS)}[/]")
    console.print(f"[bold bright_cyan]  🔄 Refresh rate: {REFRESH_SECONDS}s[/]")
    console.print(f"[dim]  📡 Pulling tick data nobody else has access to...[/]\n")

    cycle_count = 0

    # Use Rich Live for smooth in-place updates (no flicker, no scroll reset)
    with Live(console=console, refresh_per_second=1, vertical_overflow="visible") as live:
        while True:
            cycle_count += 1
            dashboard = build_dashboard(api, console, cycle_count)
            live.update(dashboard)
            time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    print("🌙 Moon Dev's CVD Scanner - Starting up...")
    print("🌙 Moon Dev says: This is the order flow cheat code. Let's go.\n")
    main()
