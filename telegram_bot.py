import os
import sys
import time
import requests
import html
import io
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

try:
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
except Exception:
    WIB = None

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    SCHEDULED_ALERTS,
    LQ45_WATCHLIST,
    KOMPAS100_WATCHLIST,
    ALL_IDX_TICKERS,
    INDICATOR_CONFIG
)
from signal_engine import analyze_ihsg, analyze_single_stock, scan_whale_watchlist
from insider_radar import (
    fetch_insider_corporate_actions,
    scan_undervalued_stocks,
    scan_high_dividend_stocks,
    get_single_stock_valuation
)
from advanced_tools import (
    generate_stock_chart,
    calculate_position_sizing,
    scan_sector_rotation
)
from ai_copilot import answer_market_query, extract_ticker_from_query
from hedgefund_radar import analyze_hedgefund_wyckoff, scan_hedgefund_picks
from whale_radar import analyze_whale_footprint, scan_top_whale_accumulations, get_whale_tier_list
from multibagger_radar import analyze_multibagger_rumor, scan_top_multibagger_picks
from macro_regime import get_ihsg_market_regime
from daily_prediction import predict_daily_ihsg_direction
from ara_hunter import scan_ara_hunter_picks, format_ara_hunter_message
from portfolio_tracker import (
    add_stock_to_portfolio,
    remove_stock_from_portfolio,
    evaluate_user_portfolio,
    format_portfolio_message,
    format_portfolio_daily_brief
)

esc = html.escape
_command_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="cmd")


def make_stock_inline_keyboard(ticker: str) -> dict:
    t = ticker.replace(".JK", "").strip().upper()
    return {
        "inline_keyboard": [
            [
                {"text": f"📈 Chart #{t}", "callback_data": f"chart:{t}"},
                {"text": f"🐋 Whale Track", "callback_data": f"whale:{t}"}
            ],
            [
                {"text": f"🏛️ Wyckoff Setup", "callback_data": f"hedge:{t}"},
                {"text": f"💎 Valuasi & PBV", "callback_data": f"val:{t}"}
            ],
            [
                {"text": f"🧮 Money Mgmt (10Jt)", "callback_data": f"calc:{t}:10jt"},
                {"text": f"➕ Pantau Saham Ini", "callback_data": f"portadd:{t}"}
            ]
        ]
    }


def make_main_inline_menu() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "🔮 Prediksi IHSG Besok", "callback_data": "menu:prediksi"},
                {"text": "⚡ Radar ARA Hunter", "callback_data": "menu:arahunter"}
            ],
            [
                {"text": "💼 Pantau Portofolio", "callback_data": "menu:watchlist"},
                {"text": "🚀 Radar Multi-Bagger", "callback_data": "menu:multibagger"}
            ],
            [
                {"text": "🏆 Tier List Akumulasi", "callback_data": "menu:tierlist"},
                {"text": "🏛️ Wyckoff Hedge Fund", "callback_data": "menu:hedge"}
            ],
            [
                {"text": "🐋 Top 5 Whale LQ45", "callback_data": "menu:whalelist"},
                {"text": "🌐 Status Pasar IHSG", "callback_data": "menu:regime"}
            ],
            [
                {"text": "🔄 Rotasi Sektor IDX", "callback_data": "menu:sektor"},
                {"text": "📰 Radar Aksi Korporasi", "callback_data": "menu:insider"}
            ],
            [
                {"text": "📊 Laporan Harian Lengkap", "callback_data": "menu:daily"},
                {"text": "🧹 Mode Layar Bersih", "callback_data": "menu:bersih"}
            ]
        ]
    }


def make_compact_reply_keyboard() -> dict:
    return {
        "keyboard": [
            [
                {"text": "🔮 Prediksi Arah IHSG"},
                {"text": "⚡ Radar ARA Hunter"}
            ],
            [
                {"text": "💼 Portofolio Pribadi"},
                {"text": "🚀 Radar Multi-Bagger"}
            ]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }


def make_remove_reply_keyboard() -> dict:
    return {
        "remove_keyboard": True
    }


def setup_bot_commands():
    token = TELEGRAM_BOT_TOKEN
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        return

    commands = [
        {"command": "menu", "description": "⚡ Panel Menu Lengkap Bot"},
        {"command": "daily", "description": "📊 Laporan Harian Lengkap Pasar"},
        {"command": "prediksi", "description": "🔮 Prediksi Arah IHSG Besok (Win Rate 67%)"},
        {"command": "arahunter", "description": "⚡ Radar Saham Potensi ARA Besok"},
        {"command": "watchlist", "description": "💼 Cek Portofolio Saham Pribadi"},
        {"command": "pantau", "description": "➕ Tambah Saham (cth: /pantau BBCA 9800 20)"},
        {"command": "hapuspantau", "description": "➖ Hapus Saham Pantauan (cth: /hapuspantau BBCA)"},
        {"command": "bersih", "description": "🧹 Sembunyikan Tombol Bawah (Layar Bersih)"},
        {"command": "keyboard", "description": "⌨️ Tampilkan Kembali Tombol Bawah"},
        {"command": "multibagger", "description": "🚀 Radar Saham Calon Multi-Bagger"},
        {"command": "tierlist", "description": "🏆 Tier List Akumulasi Whale (S/A/B)"},
        {"command": "hedge", "description": "🏛️ Wyckoff Spring & Hedge Fund Picks"},
        {"command": "whalelist", "description": "🐋 Top 5 Saham Diakumulasi Whale"},
        {"command": "scan", "description": "🎯 Deep Dive 1 Saham (cth: /scan BBCA)"},
        {"command": "chart", "description": "📈 Grafik Candlestick & MA (cth: /chart BBRI)"},
        {"command": "regime", "description": "🌐 Status Kesehatan Pasar & Proteksi Crash"},
        {"command": "val", "description": "💎 Deep Value Screener (PBV & PER Rendah)"},
        {"command": "dividen", "description": "💰 Dividend Hunter (Saham Yield Tertinggi)"},
        {"command": "calc", "description": "🧮 Hitung Money Management (cth: /calc BBCA 20jt)"},
        {"command": "sektor", "description": "🔄 Peta Rotasi Sektor IDX"},
        {"command": "insider", "description": "📰 Berita Akuisisi, Buyback & Dividen"},
        {"command": "ihsg", "description": "📊 Cek Kondisi & Level IHSG Terkini"}
    ]

    url = f"https://api.telegram.org/bot{token}/setMyCommands"
    try:
        resp = requests.post(url, json={"commands": commands}, timeout=10)
        if resp.status_code == 200:
            print("✅ Telegram bot command menu registered successfully!")
    except Exception as e:
        print(f"⚠️ Gagal mendaftarkan menu perintah bot: {e}")


def send_telegram_message(message: str, chat_id: str = None, reply_markup: dict = None) -> bool:
    token = TELEGRAM_BOT_TOKEN
    target_chat = chat_id or TELEGRAM_CHAT_ID

    if not token or not target_chat or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print(f"[Telegram Mock] Kirim ke {target_chat}:\n{message[:150]}...")
        return True

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        resp = requests.post(url, json=payload, timeout=12)
        if resp.status_code == 200:
            return True
        else:
            payload.pop("parse_mode", None)
            resp2 = requests.post(url, json=payload, timeout=12)
            return resp2.status_code == 200
    except Exception as e:
        print(f"[Telegram Send Error] {e}")
        return False


def send_telegram_photo(photo_bytes: bytes, caption: str = "", chat_id: str = None, reply_markup: dict = None) -> bool:
    token = TELEGRAM_BOT_TOKEN
    target_chat = chat_id or TELEGRAM_CHAT_ID

    if not token or not target_chat or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print(f"[Telegram Mock Photo] Kirim foto ke {target_chat} dengan caption: {caption}")
        return True

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    files = {"photo": ("chart.png", photo_bytes, "image/png")}
    data = {
        "chat_id": target_chat,
        "caption": caption[:1024],
        "parse_mode": "HTML"
    }
    if reply_markup:
        import json
        data["reply_markup"] = json.dumps(reply_markup)

    try:
        resp = requests.post(url, data=data, files=files, timeout=25)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram Photo Error] {e}")
        return False


def send_long_telegram_message(message: str, chat_id: str = None, reply_markup: dict = None):
    max_len = 3900
    if len(message) <= max_len:
        return send_telegram_message(message, chat_id, reply_markup=reply_markup)

    parts = []
    current = ""
    for line in message.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            parts.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        parts.append(current)

    for i, part in enumerate(parts):
        kb = reply_markup if i == len(parts) - 1 else None
        send_telegram_message(part, chat_id, reply_markup=kb)
        time.sleep(0.5)


def answer_callback_query(callback_query_id: str):
    token = TELEGRAM_BOT_TOKEN
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        return
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_query_id}, timeout=5)
    except Exception:
        pass


def format_ihsg_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Gagal Menganalisis IHSG:</b> {data['error']}"

    pct = data.get("pct_change", 0.0)
    chg_sym = "+" if pct >= 0 else ""
    close = data.get("close", 0.0)
    date_str = data.get("date", "Hari ini")
    trend = data.get("trend", "NETRAL")
    trend_emoji = data.get("trend_emoji", "📊")
    rsi = data.get("rsi", 50.0)
    rsi_status = data.get("rsi_status", "NEUTRAL")
    momentum = data.get("momentum", "NETRAL")
    macd = data.get("macd")
    macd_signal = data.get("macd_signal")
    support = data.get("support", 0.0)
    resistance = data.get("resistance", 0.0)
    action = data.get("action") or data.get("recommendation", "Ikuti money management ketat.")

    lines = [
        "📊 <b>IHSG COMPREHENSIVE SIGNAL UPDATE</b>",
        f"📅 <i>Tanggal: {date_str}</i>",
        "━━━━━━━━━━━━━━━━━━━",
        f"💵 <b>IHSG:</b> <code>{close:,.2f}</code> ({chg_sym}{pct:.2f}%)",
        f"🧭 <b>Status Tren:</b> {trend_emoji} <b>{trend}</b>",
        f"⚡ <b>RSI (14):</b> <code>{rsi:.1f}</code> ({rsi_status})",
        f"🎯 <b>Momentum:</b> <b>{momentum}</b>" + (f" (MACD: {macd:.2f} / Sig: {macd_signal:.2f})" if macd is not None and macd_signal is not None else "")
    ]

    flow_val = data.get("whale_flow_billion")
    cmf_val = data.get("cmf")
    whale_sig = data.get("whale_signal")

    if flow_val is not None or cmf_val is not None or whale_sig:
        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.append("🐋 <b>WHALE &amp; BANDARMOLOGY:</b>")
        if flow_val is not None:
            flow_str = f"+Rp{flow_val:.1f} M" if flow_val >= 0 else f"-Rp{abs(flow_val):.1f} M"
            lines.append(f"• Net Flow Whale: <b>{flow_str}</b>")
        if cmf_val is not None:
            lines.append(f"• Chaikin Money Flow: <code>{cmf_val:.3f}</code>")
        if whale_sig:
            lines.append(f"• Dominasi: <b>{whale_sig}</b>")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━",
        f"🛡️ <b>Level Kunci:</b> Support <code>{support:,.2f}</code> | Resistance <code>{resistance:,.2f}</code>",
        f"💡 <b>Panduan Aksi:</b>\n👉 <i>{action}</i>"
    ])
    return "\n".join(lines)


def format_single_stock_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Gagal Menganalisis #{data.get('ticker', '')}:</b> {data['error']}"

    close_val = data.get("close", 0)
    pct = data.get("pct_change", 0.0)
    chg_sym = "+" if pct >= 0 else ""
    w = data.get("whale", {})
    tp = data.get("trading_plan", {})
    flow_val = w.get("whale_flow_billion", 0)
    flow_str = f"+Rp{flow_val:.1f} M" if flow_val >= 0 else f"-Rp{abs(flow_val):.1f} M"

    sentiment = data.get("sentiment", {})
    news_items = data.get("news") or sentiment.get("news") or []
    news_lines = []
    for n in news_items[:2]:
        news_lines.append(f"• {n.get('badge', '📰')} {esc(n.get('title', ''))} <i>({esc(n.get('source', ''))})</i>")
    news_block = "\n".join(news_lines) if news_lines else "• <i>Tidak ada rumor/berita khusus terdeteksi hari ini.</i>"

    sector_str = f" | Sektor: {data['sector']}" if data.get("sector") else ""
    trend_str = data.get("trend") or data.get("signal") or "BULLISH"
    rsi_val = data.get("rsi", 50.0)
    rsi_desc = "Jenuh Jual / Oversold" if rsi_val < 30 else ("Jenuh Beli / Overbought" if rsi_val > 70 else "Netral")

    tp_action = tp.get("action") or data.get("signal") or "BUY / AKUMULASI"
    tp_entry = tp.get("entry_area", f"{int(close_val):,}")
    tp1_val = tp.get("tp1", 0)
    tp2_val = tp.get("tp2", 0)
    sl_val = tp.get("stop_loss", 0)

    tp1_gain = tp.get("tp1_gain_pct")
    if tp1_gain is None and tp1_val and close_val:
        tp1_gain = round(((tp1_val - close_val) / close_val) * 100, 1)
    elif tp1_gain is None:
        tp1_gain = 0.0

    tp2_gain = tp.get("tp2_gain_pct")
    if tp2_gain is None and tp2_val and close_val:
        tp2_gain = round(((tp2_val - close_val) / close_val) * 100, 1)
    elif tp2_gain is None:
        tp2_gain = 0.0

    sl_loss = tp.get("sl_loss_pct")
    if sl_loss is None and sl_val and close_val:
        sl_loss = round(((sl_val - close_val) / close_val) * 100, 1)
    elif sl_loss is None:
        sl_loss = 0.0

    rr_ratio = tp.get("rr_ratio") or tp.get("risk_reward_ratio") or 2.0

    return (
        f"🎯 <b>ANALISIS DEEP DIVE: #{data.get('ticker', '')}</b>\n"
        f"📅 <i>{data.get('date', 'Hari Ini')}{sector_str}</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Harga Terakhir:</b> <code>Rp{int(close_val):,}</code> ({chg_sym}{pct:.2f}%)\n"
        f"📈 <b>Tren Pasar:</b> <b>{trend_str}</b>\n"
        f"⚡ <b>RSI (14):</b> <code>{rsi_val:.1f}</code> ({rsi_desc})\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🐋 <b>JEJAK WHALE &amp; BANDAR:</b>\n"
        f"• Status Akumulasi: <b>{w.get('whale_status', 'Netral')}</b> (Skor: <code>{w.get('whale_score', 50)}/100</code>)\n"
        f"• Net Flow Modal: <b>{flow_str}</b>\n"
        f"• Lonjakan Volume (RVOL): <code>{w.get('rvol', 1.0):.2f}x</code> dari rata-rata\n"
        f"• Est. Modal Bandar (VWAP): <code>Rp{int(w.get('whale_vwap', close_val)):,}</code>\n"
        f"• Posisi vs Modal Bandar: <b>{w.get('pct_from_vwap', 0):+.1f}%</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📰 <b>RADAR BERITA &amp; RUMOR TERKINI:</b>\n"
        f"{news_block}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📋 <b>TRADING PLAN OTOMATIS:</b>\n"
        f"• Rekomendasi: <b>{tp_action}</b>\n"
        f"• Area Entry: <code>Rp{tp_entry}</code>\n"
        f"• Target TP 1: <code>Rp{int(tp1_val):,}</code> (+{tp1_gain}%)\n"
        f"• Target TP 2: <code>Rp{int(tp2_val):,}</code> (+{tp2_gain}%)\n"
        f"• Stop Loss (SL): <code>Rp{int(sl_val):,}</code> ({sl_loss}%)\n"
        f"• Reward/Risk Ratio: <code>{rr_ratio}x</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Tip: Disiplin pada Stop Loss jika bandar berbalik distribusi!</i>"
    )


def format_hedgefund_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error Wyckoff / Hedge Fund #{data.get('ticker', '')}:</b> {data['error']}"

    price = data.get("price") or data.get("close", 0)
    pct = data.get("pct_change")
    pct_str = f" ({'+' if pct >= 0 else ''}{pct:.2f}%)" if pct is not None else ""
    vwap_pct = data.get("pct_from_vwap") or data.get("pct_from_vwap20", 0.0)
    cost_status = f"💎 Diskon Modal Bandar (-{abs(vwap_pct):.1f}%)" if vwap_pct < 0 else f"🎯 Premium (+{vwap_pct:.1f}%)"
    score = data.get("hedge_score") or data.get("silent_score", 50)
    badge = data.get("phase_badge", "🏛️ ACCUMULATION")
    verdict = data.get("verdict") or data.get("phase_desc", "Fase penyerapan supply oleh institutional buyer.")
    strategy = data.get("strategy") or data.get("recommendation", "Akumulasi bertahap dekat area support.")

    vwap = data.get("vwap_20", price)
    spring_sup = data.get("spring_low") or data.get("spring_support") or data.get("support_20", int(price * 0.95))
    tp = data.get("tp_target") or data.get("resistance_20", int(price * 1.10))

    lines = [
        f"🏛️ <b>WYCKOFF &amp; HEDGE FUND FOOTPRINT: #{data.get('ticker', '')}</b>",
        f"📅 <i>Harga: Rp{int(price):,}{pct_str}</i>",
        "━━━━━━━━━━━━━━━━━━━",
        f"🏷️ <b>Fase Wyckoff:</b> {badge}",
        f"🎯 <b>Skor Akumulasi Senyap:</b> <code>{score}/100</code>"
    ]
    if "atr_pct" in data:
        lines.append(f"⚖️ <b>Volatilitas ATR:</b> <code>{data['atr_pct']:.2f}%</code>")
    if "cmf_10" in data:
        lines.append(f"🌊 <b>Chaikin Money Flow (10D):</b> <code>{data['cmf_10']:.3f}</code>")
    if "rvol" in data:
        lines.append(f"⚡ <b>RVOL:</b> <code>{data['rvol']:.2f}x</code>")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━",
        "🐋 <b>BENCHMARK MODAL BANDAR:</b>",
        f"• Modal 20-Hari Bandar (VWAP): <code>Rp{int(vwap):,}</code>",
        f"• Posisi Harga Saat Ini: <b>{cost_status}</b>",
        f"• Support Spring (Batas Bawah): <code>Rp{int(spring_sup):,}</code>",
        f"• Target Resistance TP: <code>Rp{int(tp):,}</code>",
        "━━━━━━━━━━━━━━━━━━━",
        f"📖 <b>DIAGNOSA AKSI BANDAR:</b>\n<i>{verdict}</i>\n",
        f"💡 <b>PANDUAN EKSEKUSI TRADING:</b>\n👉 <i>{strategy}</i>"
    ])
    return "\n".join(lines)


def format_hedgefund_scan_message(picks: list) -> str:
    if not picks:
        return "⚠️ Belum ada saham yang masuk kriteria Spring Shakeout atau Silent Absorption hari ini."

    lines = [
        "🏛️ <b>TOP HEDGE FUND &amp; WYCKOFF PICKS (LQ45)</b> 🚀",
        "<i>Mendeteksi saham yang sedang diakumulasi diam-diam atau baru saja membuang penumpang:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]
    for idx, p in enumerate(picks, 1):
        lines.append(
            f"<b>{idx}. #{p['ticker']}</b> (<code>Rp{p['price']:,}</code> | Modal Bandar: <code>Rp{p['vwap_20']:,}</code>)\n"
            f"   • Fase: {p['phase_badge']}\n"
            f"   • Target TP: <code>Rp{p['tp_target']:,}</code> | Stop Loss: <code>Rp{p['spring_low']:,}</code>\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/hedge KODE</code> (misal: <code>/hedge ASII</code>) untuk analisis mendalam.</i>")
    return "\n".join(lines)


def format_flow_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Gagal Menganalisis Order Flow:</b> {data['error']}"

    ticker = data.get("ticker", "SAHAM")
    price = data.get("price", 0)
    chg = data.get("pct_change", 0.0)
    chg_sym = "+" if chg >= 0 else ""
    vwap = data.get("vwap", price)
    diff = data.get("pct_diff_vwap", 0.0)
    cmf = data.get("cmf", 0.0)
    rvol = data.get("rvol", 1.0)
    flow_val = data.get("whale_flow_billion", 0.0)
    flow_str = f"+Rp{flow_val:.1f} M" if flow_val >= 0 else f"-Rp{abs(flow_val):.1f} M"
    score = data.get("whale_score", 50)
    status = data.get("whale_status", "NETRAL")

    return (
        f"🌊 <b>BANDARMOLOGY &amp; ORDER FLOW: #{ticker}</b>\n"
        f"📅 <i>Harga: Rp{int(price):,} ({chg_sym}{chg:.2f}%)</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🐋 <b>Skor Akumulasi:</b> <code>{score}/100</code> (<b>{status}</b>)\n"
        f"💵 <b>Net Whale Flow:</b> <b>{flow_str}</b>\n"
        f"⚡ <b>RVOL (Lonjakan Vol):</b> <code>{rvol:.2f}x</code>\n"
        f"🌊 <b>Chaikin Money Flow:</b> <code>{cmf:.3f}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>ESTIMASI MODAL BANDAR:</b>\n"
        f"• VWAP Bandar: <code>Rp{int(vwap):,}</code>\n"
        f"• Deviasi Harga: <b>{diff:+.2f}%</b> dari modal bandar\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Gunakan <code>/scan {ticker}</code> untuk melihat Trading Plan lengkap.</i>"
    )


def format_position_sizing_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Gagal Menghitung Money Management:</b> {data['error']}"

    return (
        f"🧮 <b>SMART MONEY MANAGEMENT: #{data['ticker']}</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Total Modal Alokasi:</b> <code>Rp{int(data['capital']):,}</code>\n"
        f"💵 <b>Harga Saham Saat Ini:</b> <code>Rp{data['price']:,}</code> (Rp{data['cost_per_lot']:,}/lot)\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🛡️ <b>REKOMENDASI PORSI AMAN (RISK 2%):</b>\n"
        f"• Alokasi Aman: <b>{data['recommended_lots']} Lot</b> ({data['recommended_lots'] * 100:,} lembar)\n"
        f"• Total Modal Dipakai: <code>Rp{data['total_spent']:,}</code>\n"
        f"• Sisa Kas Aman (Cash Buffer): <code>Rp{data['cash_remaining']:,}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>SKENARIO PROFIT / LOSS:</b>\n"
        f"• Target TP1: <code>Rp{data['tp1']:,}</code> (+{data['profit_pct']}%)\n"
        f"  👉 Potensi Cuan: <b>+Rp{data['profit_potential']:,}</b>\n"
        f"• Stop Loss (SL): <code>Rp{data['sl']:,}</code> ({data['loss_pct']}%)\n"
        f"  👉 Resiko Toleransi: <b>-Rp{data['loss_potential']:,}</b>\n"
        f"• Reward to Risk Ratio: <b>{data['rr_ratio']}x</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Catatan: Jangan all-in pada 1 saham. Disiplin cut loss bila tembus SL!</i>"
    )


def format_sector_rotation_message(sectors: list) -> str:
    if not sectors:
        return "⚠️ Gagal membaca data rotasi sektor hari ini."

    lines = [
        "🔄 <b>PETA ROTASI SEKTOR BURSA (IDX SECTORS)</b>",
        "<i>Mendeteksi sektor yang sedang menjadi primadona aliran dana:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]
    for s in sectors:
        chg = s.get("avg_change") if s.get("avg_change") is not None else s.get("chg_5d", 0.0)
        chg_sym = "+" if chg >= 0 else ""
        badge = s.get("badge") or ("🟢" if chg > 1.0 else ("🔴" if chg < -1.0 else "🟡"))
        status = s.get("status") or ("LEADING 🚀" if chg > 1.5 else ("IMPROVING 📈" if chg > 0 else ("WEAKENING 📉" if chg > -1.5 else "LAGGING 🛑")))
        leader = s.get("leader", "-")
        leader_pct = s.get("leader_pct")
        leader_str = f"#{leader}" + (f" ({'+' if leader_pct >= 0 else ''}{leader_pct:.1f}%)" if leader_pct is not None else "")

        lines.append(
            f"<b>{badge} {s.get('sector', '')}</b>\n"
            f"   • Rata-rata Performa: <b>{chg_sym}{chg:.2f}%</b> ({status})\n"
            f"   • Saham Penggerak: <code>{leader_str}</code>\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Tip: Masuk ke saham di sektor LEADING atau IMPROVING untuk momentum terbaik!</i>")
    return "\n".join(lines)


def format_whale_footprint_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error Whale Footprint #{data.get('ticker', '')}:</b> {data['error']}"

    close = data.get("close", 0)
    pct = data.get("pct_change")
    pct_str = f" ({'+' if pct >= 0 else ''}{pct:.2f}%)" if pct is not None else ""
    whale_status = data.get("status") or data.get("whale_status", "Netral")
    badge = data.get("badge", "🐋")
    score = data.get("whale_score", 50)
    rvol = data.get("rvol", 1.0)
    cmf = data.get("cmf_20") or data.get("cmf", 0.0)
    vwap20 = data.get("vwap_20d") or data.get("vwap_20", close)
    vwap5 = data.get("vwap_5d") or data.get("vwap_5", close)
    pct_diff = data.get("pct_diff_vwap20") or data.get("pct_from_vwap", 0.0)
    sl = data.get("sl") or data.get("sl_support") or data.get("sup_20", int(close * 0.95))
    tp1 = data.get("tp1", int(close * 1.05))
    tp2 = data.get("tp2", int(close * 1.10))
    action = data.get("action_plan") or data.get("explanation") or data.get("action", "Disiplin money management.")

    return (
        f"🐋 <b>DIAGNOSA WHALE FOOTPRINT: #{data.get('ticker', '')}</b>\n"
        f"📅 <i>Harga: Rp{int(close):,}{pct_str}</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Skor Akumulasi Whale:</b> <b>{score}/100</b>\n"
        f"🏷️ <b>Status Bandar:</b> {badge} <b>{whale_status}</b>\n"
        f"⚡ <b>Lonjakan Volume (RVOL):</b> <code>{rvol:.2f}x</code> dari rata-rata\n"
        f"🌊 <b>Chaikin Money Flow:</b> <code>{cmf:.3f}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>ANALISIS MODAL BANDAR:</b>\n"
        f"• Modal 20-Hari Bandar (VWAP): <code>Rp{int(vwap20):,}</code>\n"
        f"• Modal 5-Hari Terakhir: <code>Rp{int(vwap5):,}</code>\n"
        f"• Posisi Harga vs Modal 20D: <b>{pct_diff:+.1f}%</b>\n"
        f"• Support Bandar Terdekat: <code>Rp{int(sl):,}</code>\n"
        f"• Target Profit 1 (TP1): <code>Rp{int(tp1):,}</code>\n"
        f"• Target Profit 2 (TP2): <code>Rp{int(tp2):,}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📖 <b>DIAGNOSA AKSI:</b>\n<i>{action}</i>"
    )


def format_top_whale_scan_message(stocks: list, title_tag: str = "LQ45") -> str:
    if not stocks:
        return f"⚠️ Belum ada saham yang masuk kriteria akumulasi masif di kategori {title_tag}."

    lines = [
        f"🐋 <b>RADAR TOP AKUMULASI WHALE ({title_tag})</b> 🚀",
        "<i>Saham-saham dengan net inflow dan lonjakan volume terbesar:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]
    for idx, s in enumerate(stocks, 1):
        lines.append(
            f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['close']):,}</code>)\n"
            f"   • {s['badge']} Status: <b>{s['status']}</b> (Skor: <code>{s['whale_score']}/100</code>)\n"
            f"   • Modal Bandar (VWAP 20): <code>Rp{int(s['vwap_20d']):,}</code> ({s['cost_status']})\n"
            f"   • Lonjakan Volume: <code>{s['rvol']:.2f}x</code> | Target TP: <code>Rp{int(s['tp1']):,}</code>\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/scan KODE</code> (misal: <code>/scan BBCA</code>) untuk sinyal teknikal &amp; chart.</i>")
    return "\n".join(lines)


def format_whale_tier_list_message(tiers: dict) -> str:
    lines = [
        "🏆 <b>WHALE ACCUMULATION TIER LIST (LQ45)</b> 📊",
        "<i>Peringkat saham berdasarkan kekuatan & konsistensi akumulasi Bandar:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    tier_configs = [
        ("tier_s", "👑 <b>TIER S (STRONG ACCUMULATION - HIGH CONVICTION)</b>", "Akumulasi masif, harga dekat modal bandar, resiko minimal:"),
        ("tier_a", "⭐ <b>TIER A (MODERATE ACCUMULATION)</b>", "Bandar mulai masuk aktif, potensi breakout terbuka:"),
        ("tier_b", "👀 <b>TIER B (EARLY WATCHLIST / SPECULATIVE)</b>", "Ada jejak beli awal, tunggu konfirmasi volume lebih lanjut:")
    ]

    for key, title, desc in tier_configs:
        items = tiers.get(key, [])
        lines.append(title)
        lines.append(f"<i>{desc}</i>")
        if not items:
            lines.append("• <i>Belum ada saham yang memenuhi kriteria di tier ini saat ini.</i>\n")
            continue

        for it in items:
            lines.append(
                f"• <b>#{it['ticker']}</b> (<code>Rp{int(it['close']):,}</code> | Skor: <code>{it['whale_score']}</code>)\n"
                f"  👉 Modal Bandar: <code>Rp{int(it['vwap_20d']):,}</code> | TP: <code>Rp{int(it['tp1']):,}</code>"
            )
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Prioritaskan alokasi modal pada Tier S untuk keamanan maksimal!</i>")
    return "\n".join(lines)


def format_multibagger_detail_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error Radar Multi-Bagger #{data.get('ticker', '')}:</b> {data['error']}"

    ticker = data.get("ticker", "SAHAM")
    price = data.get("price", 0)
    score = data.get("bagger_score", 0)
    badge = data.get("badge", "🚀")
    signals = data.get("signals", [])
    rumor_items = data.get("rumors", [])

    sig_lines = []
    for s in signals:
        sig_lines.append(f"• {s}")
    sig_block = "\n".join(sig_lines) if sig_lines else "• Sinyal awal akumulasi terdeteksi."

    rumor_lines = []
    for r in rumor_items[:2]:
        rumor_lines.append(f"• 📰 <b>{esc(r.get('title', ''))}</b> <i>({esc(r.get('source', ''))})</i>")
    rumor_block = "\n".join(rumor_lines) if rumor_lines else "• <i>Belum ada rumor publik terbuka (akumulasi senyap).</i>"

    return (
        f"🚀 <b>RADAR MULTI-BAGGER DETECTOR: #{ticker}</b>\n"
        f"📅 <i>Harga Saat Ini: Rp{int(price):,}</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Skor Potensi Multi-Bagger:</b> <code>{score}/100</code>\n"
        f"🏷️ <b>Status Diagnosa:</b> {badge}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🔍 <b>INDIKATOR RAHASIA BANDAR:</b>\n"
        f"{sig_block}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📰 <b>CATATAN AKSI KORPORASI &amp; RUMOR:</b>\n"
        f"{rumor_block}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📋 <b>TRADING STRATEGY:</b>\n"
        "• Gunakan dana santai (tidak untuk uang belanja bulanan).\n"
        "• Masuk bertahap saat terjadi konsolidasi / retest support.\n"
        "• Pasang trailing stop jika telah terapresiasi &gt; 30%.\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Ketik <code>/chart {ticker}</code> untuk melihat posisi support teknikal.</i>"
    )


def format_multibagger_scan_message(picks: list) -> str:
    if not picks:
        return "⚠️ Belum ada saham yang masuk kriteria Multi-Bagger hari ini (Skor di bawah batas ambang)."

    lines = [
        "🚀 <b>TOP MULTI-BAGGER RADAR PICKS</b> 💎",
        "<i>Saham-saham dengan kombinasi Akumulasi Masif + Rumor Ekspansi/Akuisisi:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]
    for idx, p in enumerate(picks, 1):
        lines.append(
            f"<b>{idx}. #{p['ticker']}</b> (<code>Rp{int(p['price']):,}</code> | Skor: <code>{p['bagger_score']}/100</code>)\n"
            f"   • Status: {p['badge']}\n"
            f"   • Katalis: <i>{p['catalyst']}</i>\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/bagger KODE</code> (misal: <code>/bagger CUAN</code>) untuk bedah katalis lengkap.</i>")
    return "\n".join(lines)


def format_daily_prediction_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Gagal Menyusun Prediksi IHSG:</b> {data['error']}"

    dir_symbol = "🟢 REBOUND / NAIK" if data["direction"] == "NAIK" else ("🔴 MELEMAH / TURUN" if data["direction"] == "TURUN" else "🟡 SIDEWAYS / KONSOLIDASI")
    chg_sym = "+" if data["eido_ret"] >= 0 else ""
    sp_sym = "+" if data["sp500_ret"] >= 0 else ""

    lines = [
        "🔮 <b>PREDIKSI ARAH IHSG HARI INI (AI SNIPER)</b> 🎯",
        f"<i>Estimasi Win Rate Historis: <b>{data['win_rate_est']}%</b> ({data['tier_label']})</i>",
        "━━━━━━━━━━━━━━━━━━━",
        f"🧭 <b>Arah IHSG:</b> <b>{dir_symbol}</b>",
        f"🎯 <b>Tingkat Keyakinan:</b> <code>{data['confidence']}%</code> (Skor: <code>{data['score']}</code>)",
        "━━━━━━━━━━━━━━━━━━━",
        "🌐 <b>RADAR GLOBAL &amp; MAKRO (OVERNIGHT):</b>",
        f"• Wall Street (S&amp;P 500): <b>{sp_sym}{data['sp500_ret']:.2f}%</b>",
        f"• ETF Saham Indo (EIDO NY): <b>{chg_sym}{data['eido_ret']:.2f}%</b>",
        f"• Kurs USD/IDR: <code>Rp{data['usd_idr']:,.0f}</code> ({'+' if data['idr_chg'] >= 0 else ''}{data['idr_chg']:.2f}%)",
        f"• Posisi RSI IHSG: <code>{data['rsi14']:.1f}</code>",
        "━━━━━━━━━━━━━━━━━━━",
        "🛡️ <b>ESTIMASI RANGE IHSG:</b>",
        f"• Support: <code>{data['support']:,.0f}</code> | Resistance: <code>{data['resistance']:,.0f}</code>",
        "━━━━━━━━━━━━━━━━━━━",
        f"💡 <b>PANDUAN STRATEGI:</b>\n👉 <i>{data['guidance']}</i>"
    ]
    return "\n".join(lines)


def format_ihsg_regime_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Gagal Mendiagnosis Rezim IHSG:</b> {data['error']}"

    chg_sym = "+" if data["pct_change"] >= 0 else ""
    lines = [
        "🌐 <b>DIAGNOSIS KESEHATAN PASAR &amp; REZIM IHSG</b> 🛡️",
        f"📅 <i>Indeks IHSG: {data['close']:,.2f} ({chg_sym}{data['pct_change']:.2f}%)</i>",
        "━━━━━━━━━━━━━━━━━━━",
        f"🏷️ <b>Status Pasar:</b> {data['regime_badge']}",
        f"🎯 <b>Skor Kesehatan Makro:</b> <code>{data['macro_score']}/100</code>",
        f"⚡ <b>Indikator Volatilitas:</b> <b>{data['volatility_status']}</b>",
        "━━━━━━━━━━━━━━━━━━━",
        "📊 <b>LEVEL SUPPORT &amp; CRASH DEFENSE:</b>",
        f"• Support EMA 50: <code>{data['ema50']:,.2f}</code>",
        f"• Fortress Level (EMA 200): <code>{data['ema200']:,.2f}</code>",
        f"• Posisi vs EMA 200: <b>{data['pct_above_ema200']:+.2f}%</b>",
        "━━━━━━━━━━━━━━━━━━━",
        f"📖 <b>DIAGNOSA KONDISI:</b>\n<i>{data['verdict']}</i>\n",
        f"💡 <b>PANDUAN ALOKASI ASET:</b>\n👉 <i>{data['asset_allocation_guide']}</i>"
    ]
    return "\n".join(lines)


def format_simulasi_100m_message() -> str:
    return (
        "💼 <b>PANDUAN PORTOFOLIO &amp; MONEY MANAGEMENT</b> 📊\n"
        "<i>Sistem manajemen modal otomatis untuk menjaga kestabilan modal:</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💡 <b>FITUR BARU: PORTOFOLIO PRIBADI REAL-TIME</b>\n"
        "Sekarang Anda dapat melacak langsung saham riil yang Anda miliki!\n\n"
        "<b>Cara Menggunakan:</b>\n"
        "• Ketik: <code>/pantau KODE HARGA LOT</code>\n"
        "  Contoh: <code>/pantau BBCA 9800 20</code>\n"
        "  <i>(Mencatat 20 lot BBCA di harga beli Rp 9.800)</i>\n\n"
        "• Ketik <code>/watchlist</code> kapan saja untuk melihat evaluasi cuan/rugi, status bandar, dan rekomendasi aksi real-time!\n"
        "• Ketik <code>/hapuspantau KODE</code> untuk menghapus saham dari daftar.\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🧮 <b>FITUR HITUNG UKURAN LOT AMAN:</b>\n"
        "Gunakan perintah kalkulator pintar sebelum membeli saham:\n"
        "👉 Ketik: <code>/calc BBCA 25jt</code> (atau nominal modal Anda)\n"
        "Bot akan menghitungkan maksimal lot aman dan level Stop Loss-nya!"
    )


def format_whale_scan_message(stocks: list, title_tag: str = "LQ45", limit: int = 7) -> str:
    if not stocks:
        return f"⚠️ Belum ada saham di {title_tag} yang memenuhi kriteria Whale Flow saat ini."

    lines = [
        f"🐋 <b>WHALE RADAR SCANNER ({title_tag})</b>",
        f"<i>Ditemukan {len(stocks)} saham dengan akumulasi aktif. Top {min(limit, len(stocks))} teratas:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]
    for idx, s in enumerate(stocks[:limit], 1):
        w = s["whale"]
        tp = s["trading_plan"]
        flow_str = f"+Rp{w['whale_flow_billion']:.1f} M" if w['whale_flow_billion'] >= 0 else f"-Rp{abs(w['whale_flow_billion']):.1f} M"
        lines.append(
            f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['close']):,}</code>)\n"
            f"   • Status: <b>{w['whale_status']}</b> (Skor: <code>{w['whale_score']}/100</code>)\n"
            f"   • Net Inflow: <b>{flow_str}</b> | RVOL: <code>{w['rvol']:.2f}x</code>\n"
            f"   • Area Beli: <code>Rp{tp['entry_area']}</code> | TP: <code>Rp{tp['tp1']:,}</code>"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/scan KODE</code> (misal: <code>/scan BBCA</code>) untuk sinyal teknikal &amp; chart.</i>")
    return "\n".join(lines)


def handle_telegram_callback(callback_query: dict):
    cb_id = callback_query.get("id")
    data = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat_id = str(message.get("chat", {}).get("id"))

    answer_callback_query(cb_id)

    if not data:
        return

    parts = data.split(":")
    action = parts[0]

    if action == "chart" and len(parts) > 1:
        ticker = parts[1].upper()
        send_telegram_message(f"⏳ <i>Membuat grafik candlestick #{esc(ticker)}...</i>", chat_id)
        chart_png = generate_stock_chart(ticker)
        if chart_png:
            kb = make_stock_inline_keyboard(ticker)
            send_telegram_photo(chart_png, caption=f"📊 <b>Chart #{ticker}</b> (Candlestick + EMA + Volume)", chat_id=chat_id, reply_markup=kb)
        else:
            send_telegram_message(f"❌ Gagal memuat grafik #{esc(ticker)}.", chat_id)

    elif action == "whale" and len(parts) > 1:
        ticker = parts[1].upper()
        send_telegram_message(f"⏳ <i>Mendiagnosa jejak modal bandar #{esc(ticker)}...</i>", chat_id)
        data_whale = analyze_whale_footprint(ticker)
        kb = make_stock_inline_keyboard(ticker)
        send_long_telegram_message(format_whale_footprint_message(data_whale), chat_id, reply_markup=kb)

    elif action == "hedge" and len(parts) > 1:
        ticker = parts[1].upper()
        send_telegram_message(f"⏳ <i>Memeriksa fase Wyckoff &amp; Hedge Fund footprint #{esc(ticker)}...</i>", chat_id)
        data_wyckoff = analyze_hedgefund_wyckoff(ticker)
        kb = make_stock_inline_keyboard(ticker)
        send_long_telegram_message(format_hedgefund_message(data_wyckoff), chat_id, reply_markup=kb)

    elif action == "val" and len(parts) > 1:
        ticker = parts[1].upper()
        send_telegram_message(f"⏳ <i>Menghitung valuasi fundamental #{esc(ticker)}...</i>", chat_id)
        data_val = get_single_stock_valuation(ticker)
        if "error" in data_val:
            send_telegram_message(f"❌ {data_val['error']}", chat_id)
        else:
            chg_sym = "+" if data_val["pct_change"] >= 0 else ""
            msg = (
                f"💎 <b>VALUASI FUNDAMENTAL: #{data_val['ticker']}</b>\n"
                f"📅 <i>Harga: Rp{int(data_val['price']):,} ({chg_sym}{data_val['pct_change']:.2f}%)</i>\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>Rasio Utama:</b>\n"
                f"• PBV: <code>{data_val['pbv']}x</code>\n"
                f"• PER: <code>{data_val['per']}x</code>\n"
                f"• Dividend Yield: <code>{data_val['dividend_yield']}%</code>\n"
                f"• Market Cap: <code>Rp{data_val['market_cap_t']:.2f} Triliun</code>\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                f"🏷️ <b>Status Valuasi:</b> <b>{data_val['status']}</b>\n"
                f"💡 <i>{data_val['verdict']}</i>"
            )
            kb = make_stock_inline_keyboard(ticker)
            send_telegram_message(msg, chat_id, reply_markup=kb)

    elif action == "calc" and len(parts) > 1:
        ticker = parts[1].upper()
        capital_str = parts[2] if len(parts) > 2 else "10jt"
        send_telegram_message(f"⏳ <i>Menghitung porsi aman #{esc(ticker)} untuk modal {capital_str}...</i>", chat_id)
        res_calc = calculate_position_sizing(ticker, capital_str)
        kb = make_stock_inline_keyboard(ticker)
        send_long_telegram_message(format_position_sizing_message(res_calc), chat_id, reply_markup=kb)

    elif action == "portadd" and len(parts) > 1:
        ticker = parts[1].upper()
        send_telegram_message(
            f"💼 <b>TAMBAH #{ticker} KE PORTOFOLIO PRIBADI</b>\n\n"
            f"Silakan ketik perintah dengan harga beli dan jumlah lot Anda:\n"
            f"👉 <code>/pantau {ticker} HARGA_BELI JUMLAH_LOT</code>\n\n"
            f"<b>Contoh:</b> <code>/pantau {ticker} 9500 20</code>",
            chat_id
        )

    elif action == "portdel" and len(parts) > 1:
        ticker = parts[1].upper()
        res = remove_stock_from_portfolio(chat_id, ticker)
        send_telegram_message(f"🗑️ #{ticker} berhasil dihapus dari daftar pantauan portofolio Anda.", chat_id)
        eval_data = evaluate_user_portfolio(chat_id)
        send_long_telegram_message(format_portfolio_message(eval_data), chat_id)

    elif action == "menu" and len(parts) > 1:
        target = parts[1]
        if target == "prediksi":
            send_telegram_message("🔮 <i>Menganalisis Wall Street, kurs Rupiah & teknikal IHSG...</i>", chat_id)
            pred = predict_daily_ihsg_direction()
            send_long_telegram_message(format_daily_prediction_message(pred), chat_id)
        elif target == "arahunter":
            send_telegram_message("⚡ <i>Memindai radar ARA Hunter & ledakan volume penutupan...</i>", chat_id)
            picks = scan_ara_hunter_picks(limit=5)
            send_long_telegram_message(format_ara_hunter_message(picks), chat_id)
        elif target == "watchlist":
            send_telegram_message("⏳ <i>Menghubungkan ke bursa untuk mengevaluasi portofolio Anda...</i>", chat_id)
            eval_data = evaluate_user_portfolio(chat_id)
            send_long_telegram_message(format_portfolio_message(eval_data), chat_id)
        elif target == "daily":
            handle_telegram_command("/daily", chat_id)
        elif target == "bersih":
            send_telegram_message(
                "🧹 <b>Mode Layar Bersih Aktif!</b>\n\n"
                "Tombol bawah telah disembunyikan agar seluruh sinyal, grafik, dan teks analisa terbaca penuh tanpa tertutup tombol.\n\n"
                "💡 <i>Anda bisa akses fitur lewat:\n"
                "• Tombol <b>[Menu]</b> di pojok kiri bawah kolom ketik\n"
                "• Ketik <code>/keyboard</code> untuk memunculkan tombol kembali\n"
                "• Ketik <code>/menu</code> untuk membuka panel menu</i>",
                chat_id,
                reply_markup=make_remove_reply_keyboard()
            )
        elif target == "multibagger":
            send_telegram_message("🚀 <i>Memindai saham potensi Multi-Bagger (Rumor Aksi Korporasi + Akumulasi)...</i>", chat_id)
            picks = scan_top_multibagger_picks(limit=6)
            send_long_telegram_message(format_multibagger_scan_message(picks), chat_id)
        elif target == "tierlist":
            send_telegram_message("🏆 <i>Menyusun Tier List akumulasi Whale LQ45 (Tier S, A, B)...</i>", chat_id)
            tiers = get_whale_tier_list(LQ45_WATCHLIST)
            send_long_telegram_message(format_whale_tier_list_message(tiers), chat_id)
        elif target == "regime":
            data_reg = get_ihsg_market_regime()
            send_long_telegram_message(format_ihsg_regime_message(data_reg), chat_id)
        elif target == "simulasi100jt":
            send_long_telegram_message(format_simulasi_100m_message(), chat_id)
        elif target == "whalelist":
            top_whales = scan_top_whale_accumulations(limit=6)
            send_long_telegram_message(format_top_whale_scan_message(top_whales, title_tag="LQ45 WHALE"), chat_id)
        elif target == "hedge":
            picks = scan_hedgefund_picks(limit=6)
            send_long_telegram_message(format_hedgefund_scan_message(picks), chat_id)
        elif target == "sektor":
            sectors = scan_sector_rotation()
            send_long_telegram_message(format_sector_rotation_message(sectors), chat_id)
        elif target == "insider":
            actions = fetch_insider_corporate_actions(limit=5)
            lines = [
                "🕵️‍♂️ <b>RADAR INSIDER &amp; AKSI KORPORASI</b>",
                "<i>Kabar Merger, Akuisisi, Buyback &amp; Dividen Terkini:</i>",
                "━━━━━━━━━━━━━━━━━━━"
            ]
            for a in actions:
                lines.append(f"{a['badge']} <b>{a['category']}</b>\n👉 {a['title']} <i>({a['source']})</i>\n")
            lines.append("━━━━━━━━━━━━━━━━━━━")
            send_long_telegram_message("\n".join(lines), chat_id)


def _handle_telegram_command_impl(command_text: str, chat_id: str):
    raw_text = command_text.strip()

    BTN_MAP = {
        "🔮 Prediksi Arah IHSG": "/prediksi",
        "🚀 Radar Multi-Bagger": "/multibagger",
        "⚡ Radar ARA Hunter": "/arahunter",
        "💼 Portofolio Pribadi": "/watchlist",
        "🏆 Tier List Whale": "/tierlist",
        "🌐 Status Pasar IHSG": "/regime",
        "🐋 Top Whale LQ45": "/whalelist",
        "🏛️ Wyckoff Hedge Fund": "/hedge",
        "🔄 Rotasi Sektor": "/sektor",
        "📰 Radar Aksi Korporasi": "/insider",
        "💰 Portofolio 100 Juta": "/simulasi100jt"
    }

    raw_lower = raw_text.lower()
    if raw_text in BTN_MAP:
        command_text = BTN_MAP[raw_text]
    elif "bersih" in raw_lower or "keyboard_off" in raw_lower or "tutup tombol" in raw_lower or "sembunyi" in raw_lower:
        command_text = "/bersih"
    elif "keyboard_on" in raw_lower or "buka tombol" in raw_lower or raw_lower == "keyboard":
        command_text = "/keyboard"
    elif "ara hunter" in raw_lower or "calon ara" in raw_lower or raw_lower == "ara":
        command_text = "/arahunter"
    elif "watchlist" in raw_lower or "portofolioku" in raw_lower or "portofolio pribadi" in raw_lower:
        command_text = "/watchlist"
    elif "pantau " in raw_lower or raw_lower.startswith("/pantau"):
        pass
    elif "prediksi" in raw_lower or "arah ihsg" in raw_lower or "besok" in raw_lower or "arah" in raw_lower:
        command_text = "/prediksi"
    elif "tier list" in raw_lower:
        command_text = "/tierlist"
    elif "multi-bagger" in raw_lower or "multibagger" in raw_lower:
        command_text = "/multibagger"
    elif "status pasar" in raw_lower or "kesehatan ihsg" in raw_lower or "regime" in raw_lower:
        command_text = "/regime"
    elif "portofolio" in raw_lower or "100 juta" in raw_lower or "simulasi" in raw_lower:
        command_text = "/simulasi100jt"
    elif "top whale" in raw_lower:
        command_text = "/whalelist"
    elif "wyckoff" in raw_lower or "hedge fund" in raw_lower:
        command_text = "/hedge"
    elif "rotasi sektor" in raw_lower or "sektor" in raw_lower:
        command_text = "/sektor"
    elif "aksi korporasi" in raw_lower or "radar aksi" in raw_lower:
        command_text = "/insider"

    parts = command_text.strip().split()
    if not parts:
        return

    cmd = parts[0].split("@")[0].lower()

    if cmd in ["/start", "/help"]:
        help_msg = (
            "🤖 <b>IHSG &amp; WHALE BANDARMOLOGY SIGNAL BOT</b>\n\n"
            "Bot ini memantau IHSG dan mendeteksi saham yang diakumulasi Whale / Smart Money.\n\n"
            "✨ <b>Tampilan Baru yang Lebih Bersih &amp; Rapi:</b>\n"
            "• Tombol bawah dibuat ramping 2 baris agar <b>tidak menutupi sinyal</b>.\n"
            "• Gunakan tombol <b>[Menu]</b> di pojok kiri bawah kolom ketik untuk akses cepat.\n"
            "• Ketik <code>/bersih</code> kapan saja untuk menghilangkan tombol bawah sepenuhnya!"
        )
        send_telegram_message(help_msg, chat_id, reply_markup=make_compact_reply_keyboard())
        send_telegram_message("⚡ <b>PILIHAN MENU CEPAT (KLIK LANGSUNG):</b>", chat_id, reply_markup=make_main_inline_menu())
        return

    elif cmd in ["/menu"]:
        send_telegram_message("⚡ <b>PILIHAN MENU CEPAT (KLIK LANGSUNG):</b>", chat_id, reply_markup=make_main_inline_menu())
        return

    elif cmd in ["/bersih", "/keyboard_off", "/hidekeyboard", "/clearkeyboard"]:
        send_telegram_message(
            "🧹 <b>Mode Layar Bersih Aktif!</b>\n\n"
            "Tombol bawah telah disembunyikan agar seluruh sinyal, grafik, dan teks analisa terbaca penuh tanpa tertutup tombol.\n\n"
            "💡 <i>Anda tetap bisa akses fitur dengan:\n"
            "1️⃣ Tombol <b>[Menu]</b> di pojok kiri bawah kolom ketik\n"
            "2️⃣ Ketik <code>/keyboard</code> untuk memunculkan tombol kembali\n"
            "3️⃣ Ketik <code>/menu</code> untuk membuka panel menu</i>",
            chat_id,
            reply_markup=make_remove_reply_keyboard()
        )
        return

    elif cmd in ["/keyboard", "/keyboard_on", "/tombol"]:
        send_telegram_message(
            "⌨️ <b>Tombol Menu Ramping Aktif!</b>\n\n"
            "Tombol 2 baris telah dipasang di bawah layar (ringkas &amp; tidak menutupi sinyal).\n"
            "Ketik <code>/bersih</code> kapan saja jika ingin menyembunyikannya.",
            chat_id,
            reply_markup=make_compact_reply_keyboard()
        )
        return

    elif cmd in ["/arahunter", "/ara"]:
        send_telegram_message("⚡ <i>Memindai radar ARA Hunter &amp; ledakan volume penutupan bursa...</i>", chat_id)
        picks = scan_ara_hunter_picks(limit=5)
        send_long_telegram_message(format_ara_hunter_message(picks), chat_id)

    elif cmd in ["/pantau", "/tambahpantau"]:
        if len(parts) < 3:
            send_telegram_message(
                "💼 <b>CARA MENAMBAH SAHAM KE PANTAUAN PRIBADI</b>\n\n"
                "Format: <code>/pantau KODE HARGA_BELI LOT</code>\n\n"
                "<b>Contoh:</b>\n"
                "• <code>/pantau BBCA 9800 20</code> (20 lot di harga Rp 9.800)\n"
                "• <code>/pantau CUAN 7200 50</code> (50 lot di harga Rp 7.200)\n\n"
                "<i>Saham ini akan dipantau otomatis setiap hari dengan sinyal Whale &amp; kalkulasi profit/loss!</i>",
                chat_id
            )
            return

        ticker = parts[1].upper()
        try:
            buy_price = float(parts[2].replace(",", "").replace(".", ""))
            lots = int(parts[3]) if len(parts) > 3 else 1
        except ValueError:
            send_telegram_message("❌ Format harga atau lot tidak valid. Contoh: <code>/pantau BBCA 9800 20</code>", chat_id)
            return

        res = add_stock_to_portfolio(chat_id, ticker, buy_price, lots)
        if "error" in res:
            send_telegram_message(f"❌ {res['error']}", chat_id)
        else:
            send_telegram_message(
                f"✅ <b>Berhasil Menambahkan #{ticker} ke Portofolio!</b>\n"
                f"• Modal Beli: <code>Rp{int(buy_price):,}</code> ({lots} lot)\n"
                f"• Total Modal: <code>Rp{int(buy_price * lots * 100):,}</code>\n\n"
                f"💡 <i>Ketik <code>/watchlist</code> untuk mengevaluasi performa &amp; status bandar saat ini.</i>",
                chat_id
            )

    elif cmd in ["/hapuspantau", "/hapus", "/delpantau"]:
        if len(parts) < 2:
            send_telegram_message("⚠️ Format: <code>/hapuspantau KODE</code> (misal: <code>/hapuspantau BBCA</code>)", chat_id)
            return
        ticker = parts[1].upper()
        res = remove_stock_from_portfolio(chat_id, ticker)
        send_telegram_message(f"🗑️ #{ticker} telah dihapus dari daftar pantauan portofolio Anda.", chat_id)

    elif cmd in ["/watchlist", "/portofolioku", "/portofolio"]:
        send_telegram_message("⏳ <i>Menghubungkan ke bursa untuk mengevaluasi portofolio Anda...</i>", chat_id)
        eval_data = evaluate_user_portfolio(chat_id)
        send_long_telegram_message(format_portfolio_message(eval_data), chat_id)

    elif cmd in ["/bagger", "/multibagger", "/calonbagger"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"🚀 <i>Membedah potensi Multi-Bagger #{esc(ticker)}...</i>", chat_id)
            data_bg = analyze_multibagger_rumor(ticker)
            kb = make_stock_inline_keyboard(ticker)
            send_long_telegram_message(format_multibagger_detail_message(data_bg), chat_id, reply_markup=kb)
        else:
            send_telegram_message("🚀 <i>Memindai saham potensi Multi-Bagger (Kombinasi Rumor + Akumulasi)...</i>", chat_id)
            picks = scan_top_multibagger_picks(limit=6)
            send_long_telegram_message(format_multibagger_scan_message(picks), chat_id)

    elif cmd in ["/tierlist", "/tier", "/rank"]:
        send_telegram_message("🏆 <i>Menyusun Tier List akumulasi Whale LQ45 (Tier S, A, B)...</i>", chat_id)
        tiers = get_whale_tier_list(LQ45_WATCHLIST)
        send_long_telegram_message(format_whale_tier_list_message(tiers), chat_id)

    elif cmd in ["/simulasi100jt", "/portofolio100m"]:
        send_long_telegram_message(format_simulasi_100m_message(), chat_id)

    elif cmd in ["/whale", "/bandar"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"🐋 <i>Mendiagnosa jejak modal bandar #{esc(ticker)}...</i>", chat_id)
            data_whale = analyze_whale_footprint(ticker)
            kb = make_stock_inline_keyboard(ticker)
            send_long_telegram_message(format_whale_footprint_message(data_whale), chat_id, reply_markup=kb)
        else:
            send_telegram_message("⏳ <i>Memindai seluruh saham LQ45 untuk mencari Top Akumulasi Whale...</i>", chat_id)
            top_whales = scan_top_whale_accumulations(limit=6)
            send_long_telegram_message(format_top_whale_scan_message(top_whales, title_tag="LQ45 WHALE"), chat_id)

    elif cmd in ["/whalelist"]:
        send_telegram_message("⏳ <i>Mengambil Top Akumulasi Whale LQ45...</i>", chat_id)
        top_whales = scan_top_whale_accumulations(limit=6)
        send_long_telegram_message(format_top_whale_scan_message(top_whales, title_tag="LQ45 WHALE"), chat_id)

    elif cmd in ["/hedge", "/wyckoff"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"⏳ <i>Memeriksa fase Wyckoff &amp; Hedge Fund footprint #{esc(ticker)}...</i>", chat_id)
            data_wyckoff = analyze_hedgefund_wyckoff(ticker)
            kb = make_stock_inline_keyboard(ticker)
            send_long_telegram_message(format_hedgefund_message(data_wyckoff), chat_id, reply_markup=kb)
        else:
            send_telegram_message("⏳ <i>Memindai saham Spring Shakeout &amp; Silent Accumulation...</i>", chat_id)
            picks = scan_hedgefund_picks(limit=6)
            send_long_telegram_message(format_hedgefund_scan_message(picks), chat_id)

    elif cmd in ["/ask", "/tanya", "/ai"]:
        if len(parts) < 2:
            send_telegram_message("⚠️ Format: <code>/ask PERTANYAAN</code>\nContoh: <code>/ask Apakah BBCA masih bagus untuk swing trade?</code>", chat_id)
            return
        user_query = " ".join(parts[1:])
        send_telegram_message(f"🤖 <i>AI Copilot sedang menganalisis: \"{esc(user_query)}\"...</i>", chat_id)
        reply = answer_market_query(user_query)
        detected_ticker = extract_ticker_from_query(user_query)
        kb = make_stock_inline_keyboard(detected_ticker) if detected_ticker else None
        send_long_telegram_message(reply, chat_id, reply_markup=kb)

    elif cmd in ["/ihsg", "/market"]:
        send_telegram_message("⏳ <i>Mengambil data terkini IHSG &amp; level teknikal...</i>", chat_id)
        data = analyze_ihsg()
        send_long_telegram_message(format_ihsg_message(data), chat_id)

    elif cmd in ["/prediksi", "/arah", "/forecast", "/besok"]:
        send_telegram_message("🔮 <i>Menganalisis Wall Street semalam, kurs Rupiah & teknikal IHSG...</i>", chat_id)
        pred = predict_daily_ihsg_direction()
        send_long_telegram_message(format_daily_prediction_message(pred), chat_id)

    elif cmd in ["/regime", "/ihsg_defense", "/macro"]:
        send_telegram_message("🌐 <i>Mendiagnosis kondisi kesehatan IHSG &amp; sinyal proteksi crash...</i>", chat_id)
        data_reg = get_ihsg_market_regime()
        send_long_telegram_message(format_ihsg_regime_message(data_reg), chat_id)

    elif cmd in ["/chart", "/grafik"]:
        if len(parts) < 2:
            send_telegram_message("⚠️ Format: <code>/chart KODE</code> (misal: <code>/chart BBCA</code>)", chat_id)
            return
        ticker = parts[1].upper()
        send_telegram_message(f"⏳ <i>Membuat grafik candlestick #{esc(ticker)}...</i>", chat_id)
        chart_png = generate_stock_chart(ticker)
        if chart_png:
            kb = make_stock_inline_keyboard(ticker)
            send_telegram_photo(chart_png, caption=f"📊 <b>Chart #{ticker}</b> (Candlestick + EMA + Volume)", chat_id=chat_id, reply_markup=kb)
        else:
            send_telegram_message(f"❌ Gagal memuat grafik #{esc(ticker)}.", chat_id)

    elif cmd in ["/scan"]:
        if len(parts) < 2:
            send_telegram_message("⏳ <i>Memindai 45 saham LQ45 untuk mencari momentum Whale...</i>", chat_id)
            stocks = scan_whale_watchlist(LQ45_WATCHLIST)
            send_long_telegram_message(format_whale_scan_message(stocks, title_tag="LQ45"), chat_id)
        else:
            ticker = parts[1].upper()
            send_telegram_message(f"⏳ <i>Menganalisis mendalam #{esc(ticker)}...</i>", chat_id)
            data = analyze_single_stock(ticker)
            kb = make_stock_inline_keyboard(ticker)
            send_long_telegram_message(format_single_stock_message(data), chat_id, reply_markup=kb)

    elif cmd in ["/val", "/value", "/undervalued"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"⏳ <i>Menghitung rasio PBV &amp; PER #{esc(ticker)}...</i>", chat_id)
            data_val = get_single_stock_valuation(ticker)
            if "error" in data_val:
                send_telegram_message(f"❌ {data_val['error']}", chat_id)
                return
            chg_sym = "+" if data_val["pct_change"] >= 0 else ""
            msg = (
                f"💎 <b>VALUASI FUNDAMENTAL: #{data_val['ticker']}</b>\n"
                f"📅 <i>Harga: Rp{int(data_val['price']):,} ({chg_sym}{data_val['pct_change']:.2f}%)</i>\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>Rasio Utama:</b>\n"
                f"• PBV: <code>{data_val['pbv']}x</code>\n"
                f"• PER: <code>{data_val['per']}x</code>\n"
                f"• Dividend Yield: <code>{data_val['dividend_yield']}%</code>\n"
                f"• Market Cap: <code>Rp{data_val['market_cap_t']:.2f} Triliun</code>\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                f"🏷️ <b>Status Valuasi:</b> <b>{data_val['status']}</b>\n"
                f"💡 <i>{data_val['verdict']}</i>"
            )
            kb = make_stock_inline_keyboard(ticker)
            send_telegram_message(msg, chat_id, reply_markup=kb)
        else:
            send_telegram_message("⏳ <i>Menyaring saham 'Mercy Harga Avanza' lintas sektor...</i>", chat_id)
            stocks = scan_undervalued_stocks(LQ45_WATCHLIST, limit=5)
            lines = [
                "💎 <b>DEEP VALUE SCREENER (MERCY HARGA AVANZA)</b> 🚀",
                "<i>Saham-saham fundamental mewah dengan valuasi diskon:</i>",
                "━━━━━━━━━━━━━━━━━━━"
            ]
            for idx, s in enumerate(stocks, 1):
                lines.append(
                    f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['price']):,}</code>)\n"
                    f"   • PBV: <code>{s['pbv']}x</code> | PER: <code>{s['per']}x</code>\n"
                    f"   • 🏷️ {s['status']}\n"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━")
            lines.append("💡 <i>Ketik <code>/val KODE</code> untuk melihat rasio fundamental lengkap.</i>")
            send_long_telegram_message("\n".join(lines), chat_id)

    elif cmd in ["/calc", "/lot"]:
        if len(parts) < 2:
            send_telegram_message("⚠️ Format: <code>/calc KODE MODAL</code>\nContoh: <code>/calc BBCA 10jt</code> atau <code>/calc ASII 50jt</code>", chat_id)
            return

        ticker = parts[1].upper()
        capital_str = parts[2] if len(parts) > 2 else "10jt"
        send_telegram_message(f"⏳ <i>Menghitung money management #{esc(ticker)} untuk modal {capital_str}...</i>", chat_id)
        res_calc = calculate_position_sizing(ticker, capital_str)
        send_long_telegram_message(format_position_sizing_message(res_calc), chat_id)

    elif cmd in ["/sektor", "/sector"]:
        send_telegram_message("⏳ <i>Membaca aliran dana rotasi sektor IDX...</i>", chat_id)
        sectors = scan_sector_rotation()
        send_long_telegram_message(format_sector_rotation_message(sectors), chat_id)

    elif cmd in ["/dividen"]:
        send_telegram_message("⏳ <i>Memindai saham 'Cash Cow' dengan Dividend Yield tertinggi...</i>", chat_id)
        stocks = scan_high_dividend_stocks(LQ45_WATCHLIST, limit=5)
        lines = [
            "💰 <b>DIVIDEND HUNTER (CASH COW SCREENER)</b>",
            "<i>Saham dengan yield pembagian dividen tunai paling royal:</i>",
            "━━━━━━━━━━━━━━━━━━━"
        ]
        for idx, s in enumerate(stocks, 1):
            lines.append(
                f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['price']):,}</code>)\n"
                f"   • Estimasi Yield: <b>{s['yield']}%</b> | Nilai: <code>Rp{s['dividend_value']:,}</code>\n"
                f"   • Kategori: 🏷️ <b>{s['category']}</b>\n"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 <i>Ketik <code>/scan KODE</code> untuk cek kapan waktu terbaik masuk sebelum cum-date.</i>")
        send_long_telegram_message("\n".join(lines), chat_id)

    elif cmd in ["/daily"]:
        send_telegram_message("⏳ <i>Menyiapkan laporan harian komprehensif pasar...</i>", chat_id)

        try:
            ihsg = analyze_ihsg()
            ihsg_part = format_ihsg_message(ihsg)
        except Exception as e:
            ihsg_part = f"⚠️ <i>IHSG Signal: {esc(str(e))}</i>"

        try:
            pred = predict_daily_ihsg_direction()
            pred_part = format_daily_prediction_message(pred)
        except Exception as e:
            pred_part = f"⚠️ <i>Prediksi Harian: {esc(str(e))}</i>"

        try:
            ara_picks = scan_ara_hunter_picks(limit=3)
            ara_part = format_ara_hunter_message(ara_picks)
        except Exception as e:
            ara_part = f"⚠️ <i>ARA Hunter: {esc(str(e))}</i>"

        try:
            hedge_picks = scan_hedgefund_picks(limit=4)
            hedge_part = format_hedgefund_scan_message(hedge_picks)
        except Exception as e:
            hedge_part = f"⚠️ <i>Hedge Fund: {esc(str(e))}</i>"

        try:
            stocks = scan_whale_watchlist(LQ45_WATCHLIST)
            whale_part = format_whale_scan_message(stocks, title_tag="LQ45 WHALE MOMENTUM", limit=4)
        except Exception as e:
            whale_part = f"⚠️ <i>Whale Momentum: {esc(str(e))}</i>"

        try:
            port_brief = format_portfolio_daily_brief(chat_id)
        except Exception:
            port_brief = ""

        msg_parts = [
            "📅 <b>LAPORAN HARIAN KOMPREHENSIF PASAR (IHSG RADAR)</b> 📊\n",
            ihsg_part + "\n",
            pred_part + "\n",
            ara_part + "\n",
            hedge_part + "\n",
            whale_part
        ]
        if port_brief:
            msg_parts.append("\n━━━━━━━━━━━━━━━━━━━\n" + port_brief)

        send_long_telegram_message("\n".join(msg_parts), chat_id)

    else:
        raw = cmd.replace("/", "").upper()
        if len(raw) in [4, 5] and raw.isalpha():
            send_telegram_message(f"⏳ <i>Menganalisis #{esc(raw)}...</i>", chat_id)
            data = analyze_single_stock(raw)
            kb = make_stock_inline_keyboard(raw)
            send_long_telegram_message(format_single_stock_message(data), chat_id, reply_markup=kb)


def handle_telegram_command(command_text: str, chat_id: str):
    try:
        _handle_telegram_command_impl(command_text, chat_id)
    except Exception as e:
        print(f"[Command Execution Error] {e}")
        try:
            send_telegram_message(f"⚠️ <i>Gagal memproses perintah: {esc(str(e))}</i>", chat_id)
        except Exception:
            pass


def start_bot_polling():
    token = TELEGRAM_BOT_TOKEN
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        return

    setup_bot_commands()
    print("🤖 Bot Telegram IHSG Signal & Whale Monitor aktif...")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=20"
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1

                    # 1. Tangani Klik Tombol Interaktif (Callback Query)
                    if "callback_query" in update:
                        cb = update["callback_query"]
                        _command_executor.submit(handle_telegram_callback, cb)
                        continue

                    # 2. Tangani Pesan Teks Perintah Biasa
                    msg = update.get("message")
                    if not msg or "text" not in msg:
                        continue

                    chat_id = str(msg["chat"]["id"])
                    text = msg["text"]
                    _command_executor.submit(handle_telegram_command, text, chat_id)
            else:
                time.sleep(2)
        except Exception as e:
            print(f"[Polling Error] {e}")
            time.sleep(3)


def scheduled_worker():
    print("⏰ Background scheduler aktif untuk notifikasi pasar...")
    already_sent = {"morning": "", "closing": ""}

    while True:
        try:
            now = datetime.now(WIB) if WIB else datetime.now()
            now_str = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")

            # Morning Brief (08:30 WIB - 30 Menit Sebelum Buka)
            if now_str == SCHEDULED_ALERTS.get("morning_brief", "08:30") and already_sent["morning"] != today_str:
                if TELEGRAM_CHAT_ID:
                    ihsg = analyze_ihsg()
                    hedge_picks = scan_hedgefund_picks(limit=4)
                    top_whales = scan_top_whale_accumulations(limit=3)
                    stocks = scan_whale_watchlist(LQ45_WATCHLIST)
                    msg = (
                        "🌅 <b>MORNING MARKET RADAR &amp; WHALE REPORT (08:30 WIB)</b>\n"
                        "<i>30 Menit Menuju Pembukaan Sesi 1 IHSG!</i>\n\n"
                        + format_ihsg_message(ihsg) + "\n\n"
                        + format_top_whale_scan_message(top_whales, title_tag="TOP WHALE ACCUMULATION") + "\n\n"
                        + format_hedgefund_scan_message(hedge_picks) + "\n\n"
                        + format_whale_scan_message(stocks, title_tag="LQ45 WHALE MOMENTUM", limit=4)
                    )
                    send_long_telegram_message(msg)
                    already_sent["morning"] = today_str

            # Closing Report (16:15 WIB)
            if now_str == SCHEDULED_ALERTS.get("market_closing", "16:15") and already_sent["closing"] != today_str:
                if TELEGRAM_CHAT_ID:
                    ihsg = analyze_ihsg()
                    ara_picks = scan_ara_hunter_picks(limit=3)
                    hedge_picks = scan_hedgefund_picks(limit=4)
                    top_whales = scan_top_whale_accumulations(limit=3)
                    stocks = scan_whale_watchlist(LQ45_WATCHLIST)
                    port_brief = format_portfolio_daily_brief(TELEGRAM_CHAT_ID)

                    msg_parts = [
                        "🌇 <b>POST-MARKET CLOSING &amp; WHALE REPORT (16:15 WIB)</b>\n",
                        format_ihsg_message(ihsg) + "\n",
                        format_ara_hunter_message(ara_picks) + "\n",
                        format_top_whale_scan_message(top_whales, title_tag="CLOSING WHALE ACCUMULATION") + "\n",
                        format_hedgefund_scan_message(hedge_picks) + "\n",
                        format_whale_scan_message(stocks, title_tag="LQ45 CLOSING WHALE", limit=4)
                    ]
                    if port_brief:
                        msg_parts.append("\n━━━━━━━━━━━━━━━━━━━\n" + port_brief)

                    send_long_telegram_message("\n".join(msg_parts))
                    already_sent["closing"] = today_str

            time.sleep(30)
        except Exception as e:
            print(f"[Scheduler Error] {e}")
            time.sleep(30)


if __name__ == "__main__":
    t_poll = threading.Thread(target=start_bot_polling, daemon=True, name="polling")
    t_sched = threading.Thread(target=scheduled_worker, daemon=True, name="scheduler")

    t_poll.start()
    t_sched.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Bot dimatikan oleh pengguna.")
        sys.exit(0)
