"""
🌙 Moon Dev's BTC-Only CVD (Cumulative Volume Delta) Scanner
Built with love by Moon Dev 🚀

THE order flow cheat code for Bitcoin. Tick-level CVD, multi-timeframe
pressure, dollar imbalance, live trade tape, divergence alerts - all BTC.

Usage:
    python 32_btc_cvd_scanner.py

Author: Moon Dev
"""

import sys
import os
import time
from datetime import datetime, timezone

# Add parent directory to path so we can import api.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api import MoonDevAPI

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich import box
from rich.align import Align

# ==================== MOON DEV CONFIGURATION ====================
REFRESH_SECONDS = 5
SPARKLINE_WIDTH = 40
CVD_BAR_WIDTH = 30

# 🌙 Moon Dev - Intraday timeframes for 5-min market trading
# API only has 10m+ ticks and 5m+ imbalance, so we fetch 1h and chop it up
DISPLAY_TIMEFRAMES = ["1m", "3m", "5m", "10m", "15m"]
TF_SECONDS = {"1m": 60, "3m": 180, "5m": 300, "10m": 600, "15m": 900}

# Colors
BULL_COLOR = "bright_green"
BEAR_COLOR = "bright_red"
NEUTRAL_COLOR = "bright_yellow"
STRONG_BULL = "bold bright_green"
STRONG_BEAR = "bold bright_red"
DIVERGENCE_COLOR = "bold bright_magenta"


def format_price(price):
    if price is None or price == 0:
        return "N/A"
    return f"${price:,.2f}"


def format_volume(value):
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
    if not prices or len(prices) < 2:
        return "▄" * width, "dim"
    min_p, max_p = min(prices), max(prices)
    if max_p == min_p:
        return "▄" * min(len(prices), width), "dim"
    chars = "▁▂▃▄▅▆▇█"
    step = max(1, len(prices) // width)
    sampled = prices[::step][:width]
    sparkline = ""
    for p in sampled:
        normalized = (p - min_p) / (max_p - min_p)
        sparkline += chars[int(normalized * (len(chars) - 1))]
    color = BULL_COLOR if prices[-1] > prices[0] else BEAR_COLOR if prices[-1] < prices[0] else "dim"
    return sparkline, color


def create_cvd_sparkline(deltas, width=SPARKLINE_WIDTH):
    if not deltas or len(deltas) < 2:
        return "▄" * width, "dim"
    cumulative = []
    running = 0
    for d in deltas:
        running += d
        cumulative.append(running)
    min_c, max_c = min(cumulative), max(cumulative)
    if max_c == min_c:
        return "▄" * min(len(cumulative), width), "dim"
    chars = "▁▂▃▄▅▆▇█"
    step = max(1, len(cumulative) // width)
    sampled = cumulative[::step][:width]
    sparkline = ""
    for c in sampled:
        normalized = (c - min_c) / (max_c - min_c)
        sparkline += chars[int(normalized * (len(chars) - 1))]
    color = BULL_COLOR if cumulative[-1] > 0 else BEAR_COLOR
    return sparkline, color


def create_pressure_bar(buy_pct, width=CVD_BAR_WIDTH):
    filled = int(width * buy_pct)
    empty = width - filled
    if buy_pct >= 0.60:
        color, label = STRONG_BULL, "BUYERS DOMINATE"
    elif buy_pct >= 0.55:
        color, label = BULL_COLOR, "BUYERS LEAN"
    elif buy_pct <= 0.40:
        color, label = STRONG_BEAR, "SELLERS DOMINATE"
    elif buy_pct <= 0.45:
        color, label = BEAR_COLOR, "SELLERS LEAN"
    else:
        color, label = NEUTRAL_COLOR, "CONTESTED"
    bar = f"[{BULL_COLOR}]{'█' * filled}[/][{BEAR_COLOR}]{'█' * empty}[/]"
    return bar, f"{buy_pct*100:.1f}%", label, color


def slice_ticks_by_time(ticks, seconds):
    """🌙 Moon Dev - Chop tick data to last N seconds using timestamp field 't'"""
    if not ticks:
        return ticks
    # t field is Unix ms timestamp
    now_ms = time.time() * 1000
    cutoff = now_ms - (seconds * 1000)
    return [t for t in ticks if t.get('t', 0) >= cutoff]


def compute_tick_imbalance(ticks):
    """🌙 Moon Dev - Build buy/sell dollar imbalance from raw ticks using tick rule"""
    if not ticks or len(ticks) < 2:
        return {'buy_volume_usd': 0, 'sell_volume_usd': 0, 'net_imbalance_usd': 0, 'imbalance_ratio': 0}
    buy_vol = 0
    sell_vol = 0
    last_direction = 0
    for i in range(1, len(ticks)):
        p = ticks[i].get('p', ticks[i].get('price', 0))
        prev_p = ticks[i-1].get('p', ticks[i-1].get('price', 0))
        diff = p - prev_p
        if diff > 0:
            last_direction = 1
        elif diff < 0:
            last_direction = -1
        if last_direction >= 0:
            buy_vol += p
        else:
            sell_vol += p
    total = buy_vol + sell_vol
    net = buy_vol - sell_vol
    ratio = (net / total) if total > 0 else 0
    return {'buy_volume_usd': buy_vol, 'sell_volume_usd': sell_vol, 'net_imbalance_usd': net, 'imbalance_ratio': ratio}


def compute_tick_cvd(ticks):
    if not ticks or len(ticks) < 2:
        return 0, 0, [], []
    prices = [t.get('p', t.get('price', 0)) for t in ticks]
    cvd = 0
    deltas = []
    last_direction = 0
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        if diff > 0:
            last_direction = 1
            delta = 1
        elif diff < 0:
            last_direction = -1
            delta = -1
        else:
            delta = last_direction
        cvd += delta
        deltas.append(delta)
    price_change = ((prices[-1] - prices[0]) / prices[0] * 100) if prices[0] != 0 else 0
    return cvd, price_change, deltas, prices


def detect_divergence(price_change, cvd_value):
    if abs(price_change) < 0.01 and abs(cvd_value) < 5:
        return None, "", "", "dim"
    if price_change > 0.02 and cvd_value < -10:
        # 🌙 Moon Dev - Price up but sellers aggressive = distribution = expect DOWN
        return "BEARISH_DIV", "BEARISH DIV", "EXPECT DOWN", DIVERGENCE_COLOR
    if price_change < -0.02 and cvd_value > 10:
        # 🌙 Moon Dev - Price down but buyers aggressive = accumulation = expect UP
        return "BULLISH_DIV", "BULLISH DIV", "EXPECT UP", DIVERGENCE_COLOR
    if price_change > 0.05 and cvd_value > 20:
        return "STRONG_BULL", "STRONG BULL", "UP", STRONG_BULL
    if price_change < -0.05 and cvd_value < -20:
        return "STRONG_BEAR", "STRONG BEAR", "DOWN", STRONG_BEAR
    if price_change > 0 and cvd_value > 0:
        return "BULLISH", "BULLISH", "UP", BULL_COLOR
    if price_change < 0 and cvd_value < 0:
        return "BEARISH", "BEARISH", "DOWN", BEAR_COLOR
    return "NEUTRAL", "NEUTRAL", "FLAT", NEUTRAL_COLOR


def create_header():
    banner = """  ₿  ██████╗ ████████╗ ██████╗     ██████╗██╗   ██╗██████╗
     ██╔══██╗╚══██╔══╝██╔════╝    ██╔════╝██║   ██║██╔══██╗
     ██████╔╝   ██║   ██║         ██║     ██║   ██║██║  ██║
     ██╔══██╗   ██║   ██║         ██║     ╚██╗ ██╔╝██║  ██║
     ██████╔╝   ██║   ╚██████╗    ╚██████╗ ╚████╔╝ ██████╔╝
     ╚═════╝    ╚═╝    ╚═════╝     ╚═════╝  ╚═══╝  ╚═════╝"""
    return Panel(
        Align.center(Text(banner, style="bold bright_yellow")),
        title="🌙 [bold bright_magenta]MOON DEV's BTC CVD SCANNER[/bold bright_magenta] 🌙",
        subtitle="[bold bright_cyan]Bitcoin Order Flow Alpha | Tick-Level CVD | Multi-Timeframe[/bold bright_cyan]",
        border_style="bright_yellow",
        box=box.DOUBLE_EDGE,
        padding=(0, 1)
    )


def create_legend():
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
    return Panel(legend, border_style="bright_yellow", box=box.ROUNDED, padding=(0, 0))


def build_dashboard(api, console, cycle_count):
    """Build the BTC-only CVD dashboard"""
    output = []
    output.append(create_header())
    output.append(create_legend())

    # ==================== FETCH BTC DATA ====================
    # 🌙 Moon Dev - Fetch 1h of ticks once, then chop into intraday windows
    all_ticks = []
    tick_response = api.get_ticks("BTC", "1h", limit=10000)
    if tick_response and isinstance(tick_response, dict):
        all_ticks = tick_response.get('ticks', [])

    # Slice ticks into each display timeframe
    tick_data = {}
    for tf in DISPLAY_TIMEFRAMES:
        tick_data[tf] = slice_ticks_by_time(all_ticks, TF_SECONDS[tf])

    # Order flow
    orderflow = api.get_orderflow()
    of_stats = api.get_orderflow_stats()

    # Imbalance - API supports 5m, 15m, 1h, 4h, 24h
    # 🌙 Moon Dev - Fetch 5m and 15m, then we use tick CVD for the rest
    imbalances = {}
    for tf in ['5m', '15m']:
        imb = api.get_imbalance(tf)
        if imb:
            imbalances[tf] = imb

    # Latest price
    latest_data = api.get_tick_latest()
    btc_price = 0
    if latest_data:
        btc_price = latest_data.get('prices', {}).get('BTC', 0)

    # ==================== BTC PRICE OVERVIEW ====================
    # 🌙 Moon Dev - Use 5m ticks for the overview since we're trading 5-min markets
    ticks_5m = tick_data.get('5m', [])
    cvd_1h, chg_1h, deltas_1h, prices_1h = compute_tick_cvd(ticks_5m)

    overview = Text()
    overview.append("  ₿ BITCOIN  ", style="bold bright_yellow")
    overview.append(f"{format_price(btc_price)}  ", style="bold bright_white")

    if chg_1h > 0:
        overview.append(f"+{chg_1h:.3f}%", style=BULL_COLOR)
    elif chg_1h < 0:
        overview.append(f"{chg_1h:.3f}%", style=BEAR_COLOR)
    else:
        overview.append("0.000%", style="dim")

    overview.append("  |  CVD: ", style="dim")
    if cvd_1h > 0:
        overview.append(f"+{cvd_1h}", style=BULL_COLOR)
    elif cvd_1h < 0:
        overview.append(f"{cvd_1h}", style=BEAR_COLOR)
    else:
        overview.append("0", style="dim")

    # BTC order flow stats
    if of_stats:
        overview.append("  |  ", style="dim")
        tps = of_stats.get('trades_per_second', 0)
        overview.append(f"{tps:.1f} trades/sec", style="bold white")

    output.append(Panel(overview, border_style="bright_yellow", box=box.HEAVY, padding=(0, 0)))

    # ==================== MULTI-TIMEFRAME CVD TABLE ====================
    mtf_table = Table(
        title="[bold bright_magenta]⚡ BTC CVD ACROSS TIMEFRAMES ⚡[/]",
        box=box.HEAVY_EDGE,
        border_style="bright_magenta",
        header_style="bold bright_white on dark_magenta",
        show_lines=True,
        padding=(0, 1),
        expand=True,
    )
    mtf_table.add_column("TIMEFRAME", style="bold bright_white", justify="center", width=12)
    mtf_table.add_column("CHG%", justify="right", width=10)
    mtf_table.add_column("CVD", justify="right", width=8)
    mtf_table.add_column("PRICE ACTION", justify="center", width=SPARKLINE_WIDTH + 2)
    mtf_table.add_column("CVD FLOW", justify="center", width=SPARKLINE_WIDTH + 2)
    mtf_table.add_column("SIGNAL", justify="center", width=16)
    mtf_table.add_column("🌙 VERDICT", justify="center", width=14)

    for tf in DISPLAY_TIMEFRAMES:
        ticks = tick_data.get(tf, [])
        cvd_val, price_chg, deltas, prices = compute_tick_cvd(ticks)

        price_spark, price_color = create_sparkline(prices)
        cvd_spark, cvd_color = create_cvd_sparkline(deltas)
        div_type, signal_text, verdict, signal_color = detect_divergence(price_chg, cvd_val)

        if price_chg > 0:
            chg_str = f"[{BULL_COLOR}]+{price_chg:.3f}%[/]"
        elif price_chg < 0:
            chg_str = f"[{BEAR_COLOR}]{price_chg:.3f}%[/]"
        else:
            chg_str = "[dim]0.000%[/]"

        if cvd_val > 0:
            cvd_str = f"[{BULL_COLOR}]+{cvd_val}[/]"
        elif cvd_val < 0:
            cvd_str = f"[{BEAR_COLOR}]{cvd_val}[/]"
        else:
            cvd_str = "[dim]0[/]"

        if div_type and "DIV" in div_type:
            signal_display = f"[{signal_color}]>>> {signal_text} <<<[/]"
            # 🌙 Moon Dev - Make the verdict pop on divergences
            if "UP" in verdict:
                verdict_display = f"[bold bright_green on dark_green] ▲ {verdict} ▲ [/]"
            else:
                verdict_display = f"[bold bright_red on dark_red] ▼ {verdict} ▼ [/]"
        else:
            signal_display = f"[{signal_color}]{signal_text}[/]"
            if "UP" in verdict:
                verdict_display = f"[{BULL_COLOR}]▲ {verdict}[/]"
            elif "DOWN" in verdict:
                verdict_display = f"[{BEAR_COLOR}]▼ {verdict}[/]"
            else:
                verdict_display = f"[dim]{verdict}[/]"

        mtf_table.add_row(
            tf,
            chg_str, cvd_str,
            f"[{price_color}]{price_spark}[/]",
            f"[{cvd_color}]{cvd_spark}[/]",
            signal_display,
            verdict_display,
        )

    output.append(mtf_table)

    # ==================== BTC ORDER FLOW PRESSURE ====================
    # Use imbalance data for real $ volumes, orderflow for pressure/delta
    btc_flow = {}
    if orderflow:
        btc_flow = orderflow.get('by_coin', {}).get('BTC', {})

    # Get BTC dollar volumes from 5m imbalance (the real $ data for intraday)
    btc_imb_1h = imbalances.get('5m', {}).get('by_coin', {}).get('BTC', {})
    buy_vol = btc_imb_1h.get('buy_volume_usd', 0)
    sell_vol = btc_imb_1h.get('sell_volume_usd', 0)
    total_vol = buy_vol + sell_vol

    buy_pressure = btc_flow.get('buy_pressure', (buy_vol / total_vol) if total_vol > 0 else 0.5)
    delta = btc_flow.get('cumulative_delta', 0)

    bar, pct_str, label, color = create_pressure_bar(buy_pressure)

    pressure_text = Text()
    pressure_text.append("\n  ₿ BTC BUY/SELL PRESSURE (5M)\n\n", style="bold bright_cyan")
    pressure_text.append(f"  BUY  ", style=f"bold {BULL_COLOR}")
    bar_width = CVD_BAR_WIDTH
    filled = int(bar_width * buy_pressure)
    empty = bar_width - filled
    pressure_text.append("█" * filled, style=BULL_COLOR)
    pressure_text.append("█" * empty, style=BEAR_COLOR)
    pressure_text.append(f"  SELL\n\n", style=f"bold {BEAR_COLOR}")

    pressure_text.append(f"  Buy Volume:   ", style="dim")
    pressure_text.append(f"{format_volume(buy_vol)}", style=BULL_COLOR)
    pressure_text.append(f"  |  Sell Volume:  ", style="dim")
    pressure_text.append(f"{format_volume(sell_vol)}", style=BEAR_COLOR)
    pressure_text.append(f"  |  Total: ", style="dim")
    pressure_text.append(f"{format_volume(total_vol)}\n", style="bold bright_yellow")

    pressure_text.append(f"  Buy %: ", style="dim")
    pressure_text.append(f"{pct_str}", style=f"bold {color}")
    pressure_text.append(f"  |  Cum Delta: ", style="dim")
    if delta > 0:
        pressure_text.append(f"+{format_volume(delta)}", style=BULL_COLOR)
    elif delta < 0:
        pressure_text.append(f"{format_volume(delta)}", style=BEAR_COLOR)
    else:
        pressure_text.append("$0", style="dim")
    pressure_text.append(f"  |  Verdict: ", style="dim")
    pressure_text.append(f"{label}\n", style=f"bold {color}")

    output.append(Panel(pressure_text, border_style="bright_cyan", box=box.HEAVY_EDGE, padding=(0, 1)))

    # ==================== BTC MULTI-TIMEFRAME DOLLAR IMBALANCE ====================
    # 🌙 Moon Dev - Compute imbalance from ticks for ALL intraday timeframes
    imb_table = Table(
        title="[bold bright_red]🎯 BTC DOLLAR IMBALANCE BY TIMEFRAME 🎯[/]  [dim]Real $ aggression[/]",
        box=box.HEAVY_EDGE,
        border_style="bright_red",
        header_style="bold bright_white on dark_red",
        show_lines=True,
        padding=(0, 1),
        expand=True,
    )
    imb_table.add_column("TIMEFRAME", style="bold bright_white", justify="center", width=10)
    imb_table.add_column("BUY VOL", style=BULL_COLOR, justify="right", width=14)
    imb_table.add_column("SELL VOL", style=BEAR_COLOR, justify="right", width=14)
    imb_table.add_column("NET $", justify="right", width=14)
    imb_table.add_column("BUY ◄══ PRESSURE ══► SELL", justify="center", width=CVD_BAR_WIDTH + 6)
    imb_table.add_column("BIAS", justify="center", width=14)

    for tf in DISPLAY_TIMEFRAMES:
        # Use API imbalance data if available (5m, 15m), otherwise compute from ticks
        api_imb = imbalances.get(tf, {}).get('by_coin', {}).get('BTC', {})
        if api_imb and api_imb.get('buy_volume_usd', 0) > 0:
            btc_imb = api_imb
        else:
            btc_imb = compute_tick_imbalance(tick_data.get(tf, []))

        buy_vol = btc_imb.get('buy_volume_usd', 0)
        sell_vol = btc_imb.get('sell_volume_usd', 0)
        net = btc_imb.get('net_imbalance_usd', buy_vol - sell_vol)
        ratio = btc_imb.get('imbalance_ratio', 0)

        if net > 0:
            net_str = f"[{STRONG_BULL if ratio > 0.5 else BULL_COLOR}]+{format_volume(net)}[/]"
        elif net < 0:
            net_str = f"[{STRONG_BEAR if ratio < -0.5 else BEAR_COLOR}]{format_volume(net)}[/]"
        else:
            net_str = "[dim]$0[/]"

        total = buy_vol + sell_vol
        buy_pct = (buy_vol / total) if total > 0 else 0.5
        bar, pct_str, label, color = create_pressure_bar(buy_pct)

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

        tf_label = {"1m": "⚡ 1 MIN", "3m": "🔥 3 MIN", "5m": "📊 5 MIN", "10m": "🎯 10 MIN", "15m": "🌊 15 MIN"}.get(tf, tf)
        imb_table.add_row(
            tf_label,
            f"[{BULL_COLOR}]{format_volume(buy_vol)}[/]",
            f"[{BEAR_COLOR}]{format_volume(sell_vol)}[/]",
            net_str, bar, bias,
        )

    output.append(imb_table)

    # ==================== DIVERGENCE ALERTS ====================
    # alerts stored as (text, style, direction) tuples for proper Rich rendering
    alerts = []
    for tf in DISPLAY_TIMEFRAMES:
        ticks = tick_data.get(tf, [])
        cvd_val, price_chg, deltas, prices = compute_tick_cvd(ticks)
        div_type, signal_text, verdict, signal_color = detect_divergence(price_chg, cvd_val)

        if div_type and "DIV" in div_type:
            if "BULLISH" in div_type:
                alerts.append(("UP", tf, f"Price DOWN {price_chg:+.3f}% but buyers aggressive (CVD +{cvd_val}) = accumulation"))
            else:
                alerts.append(("DOWN", tf, f"Price UP {price_chg:+.3f}% but sellers aggressive (CVD {cvd_val}) = distribution"))

    # Dollar-level divergence: 5m vs 15m
    if imbalances.get('5m') and imbalances.get('15m'):
        short_btc = imbalances['5m'].get('by_coin', {}).get('BTC', {})
        long_btc = imbalances['15m'].get('by_coin', {}).get('BTC', {})
        short_ratio = short_btc.get('imbalance_ratio', 0)
        long_ratio = long_btc.get('imbalance_ratio', 0)
        short_net = short_btc.get('net_imbalance_usd', 0)
        long_net = long_btc.get('net_imbalance_usd', 0)

        if short_ratio > 0.3 and long_ratio < -0.2:
            alerts.append(("UP", "5m vs 15m", f"5m buying (+{format_volume(short_net)}) against 15m selling ({format_volume(long_net)}) = reversal attempt"))
        elif short_ratio < -0.3 and long_ratio > 0.2:
            alerts.append(("DOWN", "5m vs 15m", f"5m selling ({format_volume(short_net)}) against 15m buying (+{format_volume(long_net)}) = pullback"))

    if alerts:
        alert_content = Text()
        alert_content.append("  🚨 DIVERGENCE DETECTED 🚨\n\n", style="bold bright_magenta")
        for direction, tf, reason in alerts:
            if direction == "UP":
                alert_content.append(f"  ▲▲▲ EXPECT UP ▲▲▲", style="bold bright_green")
                alert_content.append(f"  ({tf}) ", style="bold white")
                alert_content.append(f"{reason}\n", style="bright_green")
            else:
                alert_content.append(f"  ▼▼▼ EXPECT DOWN ▼▼▼", style="bold bright_red")
                alert_content.append(f"  ({tf}) ", style="bold white")
                alert_content.append(f"{reason}\n", style="bright_red")

        output.append(Panel(
            alert_content,
            title="[bold bright_magenta]⚡ BTC ALPHA ⚡[/]",
            border_style="bright_magenta",
            box=box.DOUBLE_EDGE,
            padding=(0, 1)
        ))
    else:
        output.append(Panel(
            "  [dim]No divergences. Price and CVD aligned across all timeframes. Watching...[/]",
            title="[dim]BTC Divergence Monitor[/]",
            border_style="dim",
            box=box.ROUNDED,
            padding=(0, 0)
        ))

    return Group(*output)


def main():
    """🌙 Moon Dev's BTC CVD Scanner"""
    console = Console()
    console.clear()
    console.print(create_header())
    console.print("\n[bold bright_yellow]  🌙 Moon Dev:[/] Initializing BTC CVD Scanner...")

    api = MoonDevAPI()
    if not api.api_key:
        console.print("[bold red]  ❌ No API key found! Set MOONDEV_API_KEY in your .env file[/]")
        return

    console.print(f"[bold bright_green]  ✅ Moon Dev API connected[/]")
    console.print(f"[bold bright_yellow]  ₿  Scanning: BTC across {', '.join(DISPLAY_TIMEFRAMES)}[/]")
    console.print(f"[bold bright_cyan]  🔄 Refresh rate: {REFRESH_SECONDS}s[/]")
    console.print(f"[dim]  📡 Pulling BTC tick data nobody else has access to...[/]\n")

    cycle_count = 0

    with Live(console=console, refresh_per_second=1, vertical_overflow="visible") as live:
        while True:
            cycle_count += 1
            try:
                dashboard = build_dashboard(api, console, cycle_count)
                live.update(dashboard)
            except Exception as e:
                console.print(f"[bold yellow]  🌙 Moon Dev: CVD cycle #{cycle_count} hiccup, retrying - {e}[/]")
            time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    print("🌙 Moon Dev's BTC CVD Scanner - Starting up...")
    print("🌙 Moon Dev says: Bitcoin order flow cheat code. Let's go.\n")
    main()
