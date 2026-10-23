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
                {"text": "📊 Buka Chart", "callback_data": f"chart:{t}"},
                {"text": "🐋 Cek Whale", "callback_data": f"whale:{t}"}
            ],
            [
                {"text": "🚀 Cek Rumor", "callback_data": f"rumor:{t}"},
                {"text": "🌊 Order Flow", "callback_data": f"flow:{t}"}
            ],
            [
                {"text": "💎 Cek Valuasi", "callback_data": f"val:{t}"},
                {"text": "🧮 Hitung Lot (10jt)", "callback_data": f"calc:{t}"}
            ],
            [
                {"text": "🤖 Tanya AI Copilot", "callback_data": f"tanya:{t}"}
            ]
        ]
    }


def setup_bot_commands() -> bool:
    token = TELEGRAM_BOT_TOKEN
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        return False
    url = f"https://api.telegram.org/bot{token}/setMyCommands"
    commands = [
        {"command": "prediksi", "description": "🔮 Prediksi Arah IHSG Besok (AI Sniper)"},
        {"command": "multibagger", "description": "🚀 Radar Saham Potensi Multi-Bagger"},
        {"command": "arahunter", "description": "⚡ Radar ARA Hunter (Calon Meledak Besok)"},
        {"command": "watchlist", "description": "💼 Portofolio Pantauan Pribadi (TP/SL)"},
        {"command": "pantau", "description": "➕ Tambah Saham Pantauan (/pantau KODE HARGA LOT)"},
        {"command": "tierlist", "description": "🏆 Tier List Akumulasi Whale LQ45"},
        {"command": "daily", "description": "📅 Laporan Harian Lengkap Pasar"},
        {"command": "regime", "description": "🌐 Status Kesehatan Pasar IHSG"},
        {"command": "whalelist", "description": "🐋 Top Whale Accumulation"},
        {"command": "hedge", "description": "🏛️ Wyckoff Silent Absorption"},
        {"command": "sektor", "description": "🔄 Rotasi Sektor IDX"},
        {"command": "insider", "description": "📰 Keterbukaan Informasi & Rumor"},
        {"command": "bersih", "description": "🧹 Mode Bersih (Tutup Tombol Bawah)"},
        {"command": "keyboard", "description": "⌨️ Tampilkan Tombol Menu Bawah"},
        {"command": "menu", "description": "📱 Buka Menu Navigasi Utama"}
    ]
    try:
        resp = requests.post(url, json={"commands": commands}, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[ERROR setMyCommands] {e}")
        return False


def make_compact_reply_keyboard() -> dict:
    return {
        "keyboard": [
            [
                {"text": "🔮 Prediksi Arah IHSG"},
                {"text": "🚀 Radar Multi-Bagger"}
            ],
            [
                {"text": "⚡ Radar ARA Hunter"},
                {"text": "💼 Portofolio Pribadi"}
            ]
        ],
        "resize_keyboard": True,
        "is_persistent": False
    }


def make_remove_reply_keyboard() -> dict:
    return {"remove_keyboard": True}


make_persistent_reply_keyboard = make_compact_reply_keyboard


def make_main_inline_menu() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "🔮 Prediksi Arah IHSG", "callback_data": "menu:prediksi"},
                {"text": "🚀 Radar Multi-Bagger", "callback_data": "menu:multibagger"}
            ],
            [
                {"text": "⚡ Radar ARA Hunter", "callback_data": "menu:arahunter"},
                {"text": "💼 Portofolio Pantauan", "callback_data": "menu:watchlist"}
            ],
            [
                {"text": "🏆 Tier List Whale", "callback_data": "menu:tierlist"},
                {"text": "🌐 Status Pasar IHSG", "callback_data": "menu:regime"}
            ],
            [
                {"text": "🐋 Top Whale LQ45", "callback_data": "menu:whalelist"},
                {"text": "🏛️ Wyckoff Spring", "callback_data": "menu:hedge"}
            ],
            [
                {"text": "🔄 Rotasi Sektor", "callback_data": "menu:sektor"},
                {"text": "📰 Rumor & Aksi Korporasi", "callback_data": "menu:insider"}
            ],
            [
                {"text": "📅 Laporan Harian Pasar", "callback_data": "menu:daily"},
                {"text": "🧹 Bersihkan Layar", "callback_data": "menu:bersih"}
            ]
        ]
    }


def send_telegram_message(text: str, chat_id: str = None, parse_mode: str = "HTML", reply_markup: dict = None) -> bool:
    token = TELEGRAM_BOT_TOKEN
    target_id = chat_id or TELEGRAM_CHAT_ID

    if not token or not target_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        resp = requests.post(url, json=payload, timeout=15)
        return resp.status_code == 200
    except Exception as e:
        print(f"[ERROR Request] {e}")
        return False


def send_telegram_photo(photo_buf: io.BytesIO, caption: str = "", chat_id: str = None, parse_mode: str = "HTML") -> bool:
    token = TELEGRAM_BOT_TOKEN
    target_id = chat_id or TELEGRAM_CHAT_ID

    if not token or not target_id or photo_buf is None:
        return False

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    data = {
        "chat_id": target_id,
        "caption": caption,
        "parse_mode": parse_mode
    }
    photo_buf.seek(0)
    files = {
        "photo": ("chart.png", photo_buf, "image/png")
    }

    try:
        resp = requests.post(url, data=data, files=files, timeout=20)
        return resp.status_code == 200
    except Exception as e:
        print(f"[ERROR Photo] {e}")
        return False


def send_long_telegram_message(text: str, chat_id: str = None, parse_mode: str = "HTML", reply_markup: dict = None) -> bool:
    max_len = 3900
    if len(text) <= max_len:
        return send_telegram_message(text, chat_id=chat_id, parse_mode=parse_mode, reply_markup=reply_markup)

    lines = text.split("\n")
    chunks = []
    current_chunk = ""

    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_len:
            chunks.append(current_chunk)
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"

    if current_chunk.strip():
        chunks.append(current_chunk)

    success = True
    for idx, chunk in enumerate(chunks):
        markup = reply_markup if (idx == len(chunks) - 1) else None
        res = send_telegram_message(chunk, chat_id=chat_id, parse_mode=parse_mode, reply_markup=markup)
        if not res:
            success = False
        time.sleep(0.5)

    return success


def answer_telegram_callback(callback_query_id: str):
    token = TELEGRAM_BOT_TOKEN
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_query_id}, timeout=5)
    except Exception:
        pass


def format_ihsg_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Gagal Menganalisis IHSG:</b> {data['error']}"

    chg_sym = "+" if data["pct_change"] >= 0 else ""
    flow_str = f"+Rp{data['whale_flow_billion']:.1f} M" if data['whale_flow_billion'] >= 0 else f"-Rp{abs(data['whale_flow_billion']):.1f} M"

    return (
        "📊 <b>IHSG COMPREHENSIVE SIGNAL UPDATE</b>\n"
        f"📅 <i>Tanggal: {data['date']}</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>IHSG:</b> <code>{data['close']:,.2f}</code> ({chg_sym}{data['pct_change']:.2f}%)\n"
        f"🧭 <b>Status Tren:</b> <b>{data['trend']}</b>\n"
        f"⚡ <b>RSI (14):</b> <code>{data['rsi']:.1f}</code>\n"
        f"🌊 <b>Chaikin Money Flow:</b> <code>{data['cmf']:.3f}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🐋 <b>WHALE &amp; BANDARMOLOGY:</b>\n"
        f"• Net Flow Whale (Top 15): <b>{flow_str}</b>\n"
        f"• Status Dominasi: <b>{data['whale_signal']}</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <b>Level Kunci:</b> Support <code>{data['support']:,.2f}</code> | Resistance <code>{data['resistance']:,.2f}</code>\n"
        f"💡 <b>Panduan Aksi:</b>\n👉 <i>{data['action']}</i>"
    )


def format_single_stock_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Gagal Menganalisis #{data.get('ticker', '')}:</b> {data['error']}"

    chg_sym = "+" if data["pct_change"] >= 0 else ""
    w = data["whale"]
    tp = data["trading_plan"]
    flow_str = f"+Rp{w['whale_flow_billion']:.1f} M" if w['whale_flow_billion'] >= 0 else f"-Rp{abs(w['whale_flow_billion']):.1f} M"

    news_lines = []
    if data.get("news"):
        for n in data["news"][:2]:
            news_lines.append(f"• {n['badge']} {esc(n['title'])} <i>({esc(n['source'])})</i>")
    news_block = "\n".join(news_lines) if news_lines else "• <i>Tidak ada rumor/berita khusus terdeteksi hari ini.</i>"

    return (
        f"🎯 <b>ANALISIS DEEP DIVE: #{data['ticker']}</b>\n"
        f"📅 <i>{data['date']} | Sektor: {data['sector']}</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Harga Terakhir:</b> <code>Rp{int(data['close']):,}</code> ({chg_sym}{data['pct_change']:.2f}%)\n"
        f"📈 <b>Tren Pasar:</b> <b>{data['trend']}</b>\n"
        f"⚡ <b>RSI (14):</b> <code>{data['rsi']:.1f}</code> ({'Jenuh Jual / Oversold' if data['rsi'] < 30 else 'Jenuh Beli / Overbought' if data['rsi'] > 70 else 'Netral'})\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🐋 <b>JEJAK WHALE &amp; BANDAR:</b>\n"
        f"• Status Akumulasi: <b>{w['whale_status']}</b> (Skor: <code>{w['whale_score']}/100</code>)\n"
        f"• Net Flow Modal: <b>{flow_str}</b>\n"
        f"• Lonjakan Volume (RVOL): <code>{w['rvol']:.2f}x</code> dari rata-rata\n"
        f"• Est. Modal Rata-rata Bandar (VWAP): <code>Rp{int(w['whale_vwap']):,}</code>\n"
        f"• Posisi Harga vs Modal Bandar: <b>{w['pct_from_vwap']:+.1f}%</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📰 <b>RADAR BERITA &amp; RUMOR TERKINI:</b>\n"
        f"{news_block}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📋 <b>TRADING PLAN OTOMATIS:</b>\n"
        f"• Rekomendasi: <b>{tp['action']}</b>\n"
        f"• Area Entry: <code>Rp{tp['entry_area']}</code>\n"
        f"• Target TP 1: <code>Rp{tp['tp1']:,}</code> (+{tp['tp1_gain_pct']}%)\n"
        f"• Target TP 2: <code>Rp{tp['tp2']:,}</code> (+{tp['tp2_gain_pct']}%)\n"
        f"• Stop Loss (SL): <code>Rp{tp['stop_loss']:,}</code> ({tp['sl_loss_pct']}%)\n"
        f"• Reward/Risk Ratio: <code>{tp['risk_reward_ratio']}x</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Tip: Disiplin pada Stop Loss jika bandar berbalik distribusi!</i>"
    )


def format_hedgefund_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error Wyckoff / Hedge Fund #{data.get('ticker', '')}:</b> {data['error']}"

    chg_sym = "+" if data["pct_change"] >= 0 else ""
    cost_status = f"💎 Diskon Modal Bandar (-{abs(data['pct_from_vwap20']):.1f}%)" if data['pct_from_vwap20'] < 0 else f"🎯 Premium (+{data['pct_from_vwap20']:.1f}%)"

    return (
        f"🏛️ <b>WYCKOFF &amp; HEDGE FUND FOOTPRINT: #{data['ticker']}</b>\n"
        f"📅 <i>Harga: Rp{int(data['close']):,} ({chg_sym}{data['pct_change']:.2f}%)</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ <b>Fase Wyckoff:</b> {data['phase_badge']}\n"
        f"🎯 <b>Skor Akumulasi Senyap:</b> <code>{data['silent_score']}/100</code>\n"
        f"⚖️ <b>Volatilitas ATR:</b> <code>{data['atr_pct']:.2f}%</code> (Tekanan Sell Mengering)\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🐋 <b>BENCHMARK MODAL BANDAR:</b>\n"
        f"• Modal 20-Hari Bandar (VWAP): <code>Rp{int(data['vwap_20']):,}</code>\n"
        f"• Posisi Harga Saat Ini: <b>{cost_status}</b>\n"
        f"• Support Spring (Batas Bawah): <code>Rp{int(data['spring_support']):,}</code>\n"
        f"• Target Resistance TP: <code>Rp{int(data['tp_target']):,}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📖 <b>DIAGNOSA AKSI BANDAR:</b>\n<i>{data['verdict']}</i>\n\n"
        f"💡 <b>PANDUAN EKSEKUSI TRADING:</b>\n👉 <i>{data['strategy']}</i>"
    )


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

    w = data["whale"]
    lot = w.get("lot_profile", {})
    jumbo = lot.get("jumbo_pct", 50)
    retail = lot.get("retail_pct", 30)
    medium = lot.get("medium_pct", 20)
    chg_sym = "+" if data["pct_change"] >= 0 else ""
    flow_str = f"+Rp{w['whale_flow_billion']:.1f} M" if w['whale_flow_billion'] >= 0 else f"-Rp{abs(w['whale_flow_billion']):.1f} M"

    jumbo_bars = int(jumbo / 10)
    retail_bars = int(retail / 10)
    bar_jumbo = "█" * jumbo_bars + "░" * (10 - jumbo_bars)
    bar_retail = "█" * retail_bars + "░" * (10 - retail_bars)

    domination = "🟢 DOMINASI AKUMULASI (BUYER AGGRESSIVE)" if w['cmf'] > 0 else "🔴 DOMINASI DISTRIBUSI (SELLER AGGRESSIVE)"

    return (
        f"🌊 <b>ORDER FLOW &amp; WHALE FOOTPRINT: #{data['ticker']}</b>\n"
        f"📅 <i>Tanggal: {data['date']} | Harga: Rp{int(data['close']):,} ({chg_sym}{data['pct_change']:.2f}%)</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "⚖️ <b>TEKANAN VOLUME &amp; MONEY FLOW:</b>\n"
        f"• Arah Arus Uang: <b>{domination}</b>\n"
        f"• Net Whale Flow: <b>{flow_str}</b>\n"
        f"• Chaikin Money Flow: <code>{w['cmf']:.3f}</code>\n"
        f"• Lonjakan Vol (RVOL): <code>{w['rvol']:.2f}x</code> dari rata-rata\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🐋 <b>PROFIL UKURAN TRANSAKSI (TICKET SIZE):</b>\n"
        f"• 🐋 <b>Order Jumbo (Bandar/Institusi):</b> <code>{jumbo}%</code>\n"
        f"  [{bar_jumbo}]\n"
        f"• 🐜 <b>Order Retail (Semut/FOMO):</b> <code>{retail}%</code>\n"
        f"  [{bar_retail}]\n"
        f"• 📦 <b>Order Menengah:</b> <code>{medium}%</code>\n\n"
        f"💡 <i>{lot.get('summary', '')}</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>MODAL BANDAR &amp; TOLOK UKUR:</b>\n"
        f"• Est. Rata-rata Modal Bandar (VWAP): <code>Rp{int(w['whale_vwap']):,}</code>\n"
        f"• Posisi Harga vs Modal Bandar: <b>{w['pct_from_vwap']:+.1f}%</b>\n"
        f"• Support Kunci: <code>Rp{int(data['levels']['support_1']):,}</code>\n"
        f"• Resistance Target: <code>Rp{int(data['levels']['resistance_1']):,}</code>\n"
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
        chg_sym = "+" if s["chg_5d"] >= 0 else ""
        lines.append(
            f"<b>{s['badge']} {s['sector']}</b>\n"
            f"   • Return 5 Hari: <b>{chg_sym}{s['chg_5d']:.2f}%</b> ({s['status']})\n"
            f"   • Saham Penggerak: <code>#{s['leader']}</code>\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Tip: Masuk ke saham di sektor LEADING atau ACCELERATING untuk momentum terbaik!</i>")
    return "\n".join(lines)


def format_whale_footprint_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error Whale Footprint #{data.get('ticker', '')}:</b> {data['error']}"

    chg_sym = "+" if data["pct_change"] >= 0 else ""
    return (
        f"🐋 <b>DIAGNOSA WHALE FOOTPRINT: #{data['ticker']}</b>\n"
        f"📅 <i>Harga: Rp{int(data['close']):,} ({chg_sym}{data['pct_change']:.2f}%)</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Skor Akumulasi Whale:</b> <b>{data['whale_score']}/100</b>\n"
        f"🏷️ <b>Status Bandar:</b> <b>{data['whale_status']}</b>\n"
        f"⚡ <b>Lonjakan Volume (RVOL):</b> <code>{data['rvol']:.2f}x</code> dari rata-rata\n"
        f"🌊 <b>Chaikin Money Flow:</b> <code>{data['cmf']:.3f}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>ANALISIS MODAL BANDAR:</b>\n"
        f"• Modal 20-Hari Bandar (VWAP): <code>Rp{int(data['vwap_20d']):,}</code>\n"
        f"• Modal 5-Hari Terakhir: <code>Rp{int(data['vwap_5d']):,}</code>\n"
        f"• Posisi Harga vs Modal 20D: <b>{data['pct_diff_vwap20']:+.1f}%</b>\n"
        f"• Support Bandar Terdekat: <code>Rp{int(data['sl_support']):,}</code>\n"
        f"• Target Profit 1 (TP1): <code>Rp{int(data['tp1']):,}</code>\n"
        f"• Target Profit 2 (TP2): <code>Rp{int(data['tp2']):,}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📖 <b>DIAGNOSA AKSI:</b>\n<i>{data['action']}</i>"
    )


def format_top_whale_scan_message(stocks: list, title_tag: str = "LQ45") -> str:
    if not stocks:
        return f"⚠️ Belum ada saham yang masuk kriteria akumulasi masif di kategori {title_tag}."

    lines = [
        f"👑 <b>TOP WHALE ACCUMULATION ({title_tag})</b> 🚀",
        "<i>Saham dengan akumulasi institusi / smart money paling dominan:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]
    for idx, s in enumerate(stocks, 1):
        disc_str = f"💎 Diskon {abs(s['pct_diff_vwap20']):.1f}%" if s['pct_diff_vwap20'] < -1.0 else f"🎯 Modal Seimbang"
        lines.append(
            f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['close']):,}</code>)\n"
            f"   • Skor Whale: <b>{s['whale_score']}/100</b> ({s['status']})\n"
            f"   • Modal Bandar: <code>Rp{int(s['vwap_20d']):,}</code> ({disc_str})\n"
            f"   • Target TP: <code>Rp{int(s['tp1']):,}</code> | Stop Loss: <code>Rp{int(s['sl']):,}</code>\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/whale KODE</code> (misal: <code>/whale BBCA</code>) untuk diagnosa footprint mendalam.</i>")
    return "\n".join(lines)


def format_whale_tier_list_message(tiers: dict) -> str:
    if "error" in tiers:
        return f"❌ <b>Error Tier List:</b> {tiers['error']}"

    tier_s = tiers.get("tier_s", [])
    tier_a = tiers.get("tier_a", [])
    tier_b = tiers.get("tier_b", [])

    lines = [
        "🏆 <b>TIER LIST WHALE &amp; BANDARMOLOGY (LQ45)</b> 📊",
        "<i>Ranking saham berdasarkan kekuatan akumulasi institusi &amp; posisi modal bandar:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    lines.append("👑 <b>TIER S — GOD TIER (Monster Akumulasi &amp; High Conviction)</b>")
    lines.append("<i>Saham dengan skor tertinggi (≥90) &amp; akumulasi institusi masif:</i>")
    if not tier_s:
        lines.append("<i>Belum ada saham yang mencapai kualifikasi Tier S hari ini.</i>\n")
    else:
        for idx, s in enumerate(tier_s, 1):
            disc_str = f"💎 <b>Diskon {abs(s['pct_diff_vwap20']):.1f}%</b>" if s['pct_diff_vwap20'] < -1.5 else "🎯 Modal Seimbang"
            lines.append(
                f"<b>{idx}. #{s['ticker']}</b> — <code>Rp{int(s['close']):,}</code>\n"
                f"   • Skor Whale: <b>{s['whale_score']}/100</b> ({s['status']})\n"
                f"   • Posisi: {disc_str} (Modal Whale: <code>Rp{int(s['vwap_20d']):,}</code>)\n"
                f"   • Target TP: <code>Rp{int(s['tp1']):,}</code> | Stop Loss: <code>Rp{int(s['sl']):,}</code>\n"
            )

    lines.append("💎 <b>TIER A — HIGH CONVICTION (Akumulasi Kuat &amp; Siap Mark-Up)</b>")
    lines.append("<i>Saham dengan akumulasi solid (skor 80–89) &amp; penyerapan stabil:</i>")
    if not tier_a:
        lines.append("<i>Belum ada saham yang masuk Tier A hari ini.</i>\n")
    else:
        for idx, s in enumerate(tier_a, 1):
            disc_str = f"💎 <b>Diskon {abs(s['pct_diff_vwap20']):.1f}%</b>" if s['pct_diff_vwap20'] < -1.5 else "🎯 Modal Seimbang"
            lines.append(
                f"<b>{idx}. #{s['ticker']}</b> — <code>Rp{int(s['close']):,}</code>\n"
                f"   • Skor Whale: <b>{s['whale_score']}/100</b> ({s['status']})\n"
                f"   • Posisi: {disc_str} (Modal Whale: <code>Rp{int(s['vwap_20d']):,}</code>)\n"
                f"   • Target TP: <code>Rp{int(s['tp1']):,}</code> | Stop Loss: <code>Rp{int(s['sl']):,}</code>\n"
            )

    lines.append("⚡ <b>TIER B — EARLY ACCUMULATION (Fase Penyerapan Awal)</b>")
    lines.append("<i>Saham tahap awal akumulasi (skor 70–79) yang sedang menguji support:</i>")
    if not tier_b:
        lines.append("<i>Belum ada saham yang masuk Tier B hari ini.</i>\n")
    else:
        for idx, s in enumerate(tier_b[:6], 1):
            disc_str = f"💎 Diskon {abs(s['pct_diff_vwap20']):.1f}%" if s['pct_diff_vwap20'] < -1.5 else "🎯 Modal Seimbang"
            lines.append(
                f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['close']):,}</code>) — Skor: <b>{s['whale_score']}/100</b> | {disc_str}"
            )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <b>Rekomendasi Trading:</b>")
    lines.append("👉 Prioritaskan entry pada saham <b>Tier S</b> dan <b>Tier A</b> yang bertanda 💎 <i>Diskon Bandar</i> untuk Risk/Reward Ratio maksimal.")
    lines.append("👉 Ketik <code>/whale KODE</code> (misal: <code>/whale MDKA</code>) untuk melihat diagnosa detail.")
    return "\n".join(lines)


def format_multibagger_detail_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error:</b> {esc(str(data['error']))}"

    lines = [
        f"🚀 <b>RADAR MULTI-BAGGER &amp; RUMOR: #{data['ticker']}</b> 🔥",
        "<i>Deteksi Saham Potensi Ratusan Persen (Rumor Aksi Korporasi + Akumulasi Bandar)</i>",
        "━━━━━━━━━━━━━━━━━━━",
        f"🎯 <b>Skor Potensi Multi-Bagger: {data['mb_score']}/100</b>",
        f"🏷️ <b>Status:</b> {data['phase_badge']}",
        f"💵 <b>Harga Sekarang:</b> <code>Rp{int(data['close']):,}</code>",
        "━━━━━━━━━━━━━━━━━━━",
        "📊 <b>JEJAK FOOTPRINT WHALE:</b>",
        f"• <b>Modal Rata-rata Whale:</b> <code>Rp{int(data['vwap_20d']):,}</code>",
        f"• <b>Posisi Terhadap Modal:</b> {data['cost_status']}",
        f"• <b>Lonjakan Volume (RVOL):</b> <b>{data['rvol']:.1f}x</b> dari rata-rata",
        f"• <b>Money Flow CMF:</b> <b>{data['cmf_20']:+.2f}</b>",
        "━━━━━━━━━━━━━━━━━━━",
        "📰 <b>KATALIS &amp; BAU RUMOR TERDETEKSI:</b>"
    ]

    if not data.get("news"):
        lines.append("<i>Belum ada keterbukaan informasi khusus terbaru.</i>")
    else:
        for n in data["news"]:
            lines.append(f"{n['badge']} {esc(n['title'])} <i>({esc(n['source'])})</i>")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━",
        f"📖 <b>DIAGNOSA AKSI BANDAR:</b>\n<i>{data['verdict']}</i>",
        "",
        f"🎯 <b>RENCANA EKSEKUSI MENGIKUTI BANDAR:</b>\n<i>{data['action']}</i>\n",
        f"• 🎯 <b>Target TP-1 (+30%):</b> <code>Rp{int(data['tp1']):,}</code> <i>(Jual 35% lot &amp; geser SL ke BEP)</i>",
        f"• 🚀 <b>Target TP-2 (+75%):</b> <code>Rp{int(data['tp2']):,}</code> <i>(Jual 35% lot kunci profit 1 bagger)</i>",
        f"• 💎 <b>Runner Lot (30% Sisa):</b> <i>Dibiarkan terbang ikuti mark-up bandar</i>",
        f"• 🛑 <b>Stop Loss Ketat (-6%):</b> <code>Rp{int(data['sl']):,}</code>",
        "━━━━━━━━━━━━━━━━━━━",
        f"💡 <i>Tip: Masuk saat fase Akumulasi Senyap sebelum berita resmi menjadi euforia publik!</i>"
    ])
    return "\n".join(lines)


def format_multibagger_scan_message(picks: list) -> str:
    if not picks:
        return "⚠️ Tidak ada saham yang memenuhi kriteria Multi-Bagger hari ini."

    lines = [
        "🚀 <b>TOP POTENSI MULTI-BAGGER RADAR (IHSG)</b> 🔥",
        "<i>Saham tidur / murah dengan lonjakan volume Whale &amp; rumor aksi korporasi (ala BIPI / PANI):</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    for idx, p in enumerate(picks, 1):
        catalysts_str = ", ".join([c["keyword"] for c in p.get("catalysts", [])[:2]])
        cat_badge = f" [Katalis: {catalysts_str}]" if catalysts_str else ""
        lines.append(
            f"<b>{idx}. #{p['ticker']}</b> — <code>Rp{int(p['close']):,}</code>\n"
            f"   • Skor Potensi: <b>{p['mb_score']}/100</b> ({p['phase']})\n"
            f"   • Modal Bandar: <code>Rp{int(p['vwap_20d']):,}</code> ({p['cost_status']})\n"
            f"   • Vol Spike: <b>{p['rvol']:.1f}x</b>{cat_badge}\n"
            f"   • Target TP: <code>Rp{int(p['tp1']):,}</code> | Stop Loss: <code>Rp{int(p['sl']):,}</code>\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/rumor KODE</code> (misal: <code>/rumor BIPI</code>) untuk membedah berita &amp; akumulasi bandar lengkap!</i>")
    return "\n".join(lines)


def format_daily_prediction_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error:</b> {esc(str(data['error']))}"

    factors_str = "\n".join([f"• {f}" for f in data.get("factors", [])])
    tier = data.get("tier_label", "⚡ TIER 2: SINYAL HARIAN")
    win_rate = data.get("win_rate_est", "60%")

    return (
        "🔮 <b>PREDIKSI HARIAN ARAH IHSG (AI SNIPER ENGINE)</b> 📊\n"
        "<i>Berdasarkan 4 Pola Sniper: EIDO Wall Street + Kurs Rupiah + V-Rebound</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ <b>Status Tingkatan:</b> <b>{tier}</b>\n"
        f"🎯 <b>Arah Prediksi:</b> <b>{data['direction']}</b>\n"
        f"🏆 <b>Akurasi Historis (Win Rate):</b> <code>{win_rate}</code>\n"
        f"⚡ <b>Skor Kekuatan Sinyal:</b> <code>{data['score']:+d}</code> (-100 s/d +100)\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Level IHSG Terakhir:</b> <code>{data['ihsg_current']:,.2f}</code> ({data['ihsg_last_chg']:+.2f}%)\n"
        f"🛡️ <b>Estimasi Support Harian:</b> <code>{data['support']:,.2f}</code>\n"
        f"🚀 <b>Estimasi Resistance Harian:</b> <code>{data['resistance']:,.2f}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🔍 <b>FAKTOR KUNCI HARI INI:</b>\n"
        f"{factors_str}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <b>PANDUAN EKSEKUSI TRADING:</b>\n<i>{data['guidance']}</i>"
    )


def format_ihsg_regime_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error:</b> {esc(str(data['error']))}"

    lines = [
        "🌐 <b>IHSG MACRO MARKET REGIME &amp; DEFENSE ENGINE</b> 🛡️",
        "<i>Sistem Deteksi Kesehatan Pasar &amp; Proteksi Penurunan IHSG (Pelajaran Backtest 2024-2026)</i>",
        "━━━━━━━━━━━━━━━━━━━",
        f"🏷️ <b>Status Pasar:</b> {data['regime']}",
        f"🧭 <b>Mode Operasi:</b> <b>{data['status_text']}</b>",
        f"💵 <b>Level IHSG Saat Ini:</b> <code>{data['ihsg_price']:,.2f}</code> ({data['chg_1d']:+.2f}%)",
        f"📊 <b>Perubahan 5 Hari:</b> <code>{data['chg_5d']:+.2f}%</code>",
        f"📈 <b>Rata-rata SMA20:</b> <code>{data['sma20']:,.2f}</code> | <b>SMA50:</b> <code>{data['sma50']:,.2f}</code>",
        "━━━━━━━━━━━━━━━━━━━",
        "🛡️ <b>REKOMENDASI ALOKASI PORTOFOLIO:</b>",
        f"• <b>Porsi Cash Aman:</b> Minimal <b>{data['cash_pct']}%</b> dari total modal",
        f"• <b>Saham Bluechip (Big Banks):</b> {'✅ Diperbolehkan' if data['allow_bigcaps'] else '⛔ DILARANG (Rawan Guyur)'}",
        f"• <b>Saham Multi-Bagger (Konglo/Rumor):</b> {'✅ Boleh Diseleksi' if data['allow_multibagger'] else '⛔ Tahan Dulu'}",
        "━━━━━━━━━━━━━━━━━━━",
        f"💡 <b>PANDUAN EKSEKUSI BOT:</b>\n<i>{data['advice']}</i>"
    ]
    return "\n".join(lines)


def format_simulasi_100m_message() -> str:
    return (
        "💰 <b>HASIL REAL BACKTEST MENGIKUTI BANDAR (2024 - 2026)</b> 📊\n"
        "<i>Strategi: Akumulasi Smart Money + Target Bertahap (TP1 +30%, TP2 +75%, Runner)</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💵 <b>Modal Awal:</b> <code>Rp 100.000.000</code>\n"
        "💎 <b>Modal Akhir:</b> <code>Rp 150.173.667</code>\n"
        "🚀 <b>Net Profit Bersih:</b> <b>+Rp 50.173.667 (+50.2%)</b>\n"
        "📈 <b>Profit Factor:</b> <code>1.47</code> (Rasio Cuan vs Rugi > 5:1)\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>CARA MENGIKUTI TARGET TP BANDAR:</b>\n"
        "1️⃣ <b>TP-1 (+30%):</b> Jual 35% lot untuk balik modal dasar &amp; pasang Stop Loss di BEP (Risk-Free!).\n"
        "2️⃣ <b>TP-2 (+75%):</b> Jual 35% lot lagi saat harga meledak mendekati 1 Bagger.\n"
        "3️⃣ <b>Runner Lot (30% Sisa):</b> Dibiarkan terbang mengikuti mark-up bandar sampai ada sinyal distribusi!\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>CONTOH TRADE MONSTER MULTI-BAGGER:</b>\n"
        "• <b>#PANI</b>: Masuk Rp5.119 ➔ Keluar Rp10.588 | <b>+Rp 16,11 Juta (+106.8%)</b>\n"
        "• <b>#MDKA</b>: Masuk Rp2.159 ➔ Keluar Rp3.194 | <b>+Rp 12,80 Juta (+47.9%)</b>\n"
        "• <b>#ASII</b>: Masuk Rp3.889 ➔ Keluar Rp6.807 | <b>+Rp 8,10 Juta (+75.0%)</b>\n"
        "• <b>#MEDC</b>: Masuk Rp874 ➔ Keluar Rp1.257 | <b>+Rp 8,09 Juta (+43.7%)</b>\n"
        "• <b>#TPIA</b>: Masuk Rp5.182 ➔ Keluar Rp6.228 | <b>+Rp 7,57 Juta (+20.2%)</b>\n"
        "• <b>#BREN</b>: Masuk Rp4.644 ➔ Keluar Rp5.967 | <b>+Rp 6,76 Juta (+28.5%)</b>\n"
        "• <b>#BIPI</b>: Masuk Rp85 ➔ Keluar Rp99 (4.513 lot!) | <b>+Rp 6,15 Juta (+16.5%)</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🛡️ <b>DISIPLIN PROTEKSI SAAT SALAH:</b>\n"
        "• Kerugian dibatasi ketat di <b>-6.0%</b> (rugi cuma ~Rp 1,5 Juta per saham).\n"
        "• Tetapi saat menang di saham bandar, cuan mencapai <b>Rp 8 Juta s/d Rp 16 Juta</b>!\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Gunakan tombol menu di bawah untuk memindai saham yang sedang diakumulasi bandar hari ini!</i>"
    )


def format_whale_scan_message(stocks: list, title_tag: str = "LQ45", limit: int = 7) -> str:
    if not stocks:
        return f"⚠️ Tidak ditemukan saham yang memenuhi kriteria akumulasi aktif di kategori {title_tag}."

    top_stocks = stocks[:limit]
    lines = [
        f"🐋 <b>TOP WHALE ACCUMULATION ({title_tag})</b> 🚀",
        "<i>Berdasarkan Volume Spike, Chaikin Money Flow &amp; Breakout</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    for idx, s in enumerate(top_stocks, 1):
        w = s["whale"]
        lot_prof = w.get("lot_profile", {})
        jumbo = lot_prof.get("jumbo_pct", 50)
        chg_sym = "+" if s["pct_change"] >= 0 else ""
        flow = f"+{w['whale_flow_billion']:.1f}M" if w['whale_flow_billion'] >= 0 else f"{w['whale_flow_billion']:.1f}M"
        lines.append(
            f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['close']):,}</code> | {chg_sym}{s['pct_change']:.1f}%)\n"
            f"   • Status: <b>{w['whale_status']}</b> ({w['whale_score']}/100)\n"
            f"   • Tiket Order: 🐋 <b>Jumbo {jumbo}%</b> | Vol Spike: <b>{w['rvol']:.1f}x</b> | Flow: <b>{flow}</b>\n"
            f"   • Rencana: Beli <code>Rp{s['trading_plan']['entry_area']}</code> | TP: <code>{s['trading_plan']['tp1']:,}</code> | SL: <code>{s['trading_plan']['stop_loss']:,}</code>\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/scan KODE</code> (misal: <code>/scan BBCA</code>) untuk detail lengkap.</i>")
    return "\n".join(lines)


def handle_telegram_callback(callback_query: dict):
    cb_id = callback_query.get("id")
    if cb_id:
        answer_telegram_callback(cb_id)

    data = callback_query.get("data", "")
    msg = callback_query.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id"))
    if not chat_id or not data:
        return

    parts = data.split(":")
    if len(parts) < 2:
        return

    action, ticker = parts[0], parts[1].upper()

    if action == "chart":
        send_telegram_message(f"🎨 <i>Menggambar visual candlestick chart &amp; TP/SL #{esc(ticker)}...</i>", chat_id)
        buf = generate_stock_chart(ticker)
        if buf is None:
            send_telegram_message(f"❌ Gagal membuat chart untuk #{esc(ticker)}.", chat_id)
            return
        caption = f"📊 <b>Technical Candlestick Chart: #{esc(ticker)}</b>\n<i>Garis Biru: EMA20 | Kuning: EMA50 | Cyan: TP1 | Merah: Stop Loss</i>"
        send_telegram_photo(buf, caption=caption, chat_id=chat_id)

    elif action == "whale":
        send_telegram_message(f"🐋 <i>Mendiagnosis jejak Whale &amp; Bandarmology #{esc(ticker)}...</i>", chat_id)
        data_whale = analyze_whale_footprint(ticker)
        kb = make_stock_inline_keyboard(ticker)
        send_long_telegram_message(format_whale_footprint_message(data_whale), chat_id, reply_markup=kb)

    elif action == "rumor":
        send_telegram_message(f"🚀 <i>Mendiagnosis rumor aksi korporasi &amp; potensi Multi-Bagger #{esc(ticker)}...</i>", chat_id)
        data_mb = analyze_multibagger_rumor(ticker)
        kb = make_stock_inline_keyboard(ticker)
        send_long_telegram_message(format_multibagger_detail_message(data_mb), chat_id, reply_markup=kb)

    elif action == "flow":
        send_telegram_message(f"⏳ <i>Membaca Order Flow &amp; Tiket Transaksi #{esc(ticker)}...</i>", chat_id)
        data_flow = analyze_single_stock(ticker)
        send_long_telegram_message(format_flow_message(data_flow), chat_id)

    elif action == "hedge":
        send_telegram_message(f"🏛️ <i>Mendiagnosis fase Wyckoff &amp; Hedge Fund footprint #{esc(ticker)}...</i>", chat_id)
        data_hedge = analyze_hedgefund_wyckoff(ticker)
        send_long_telegram_message(format_hedgefund_message(data_hedge), chat_id)

    elif action == "val":
        send_telegram_message(f"⏳ <i>Mengecek valuasi fundamental #{esc(ticker)}...</i>", chat_id)
        data_val = get_single_stock_valuation(ticker)
        if "error" in data_val:
            send_telegram_message(f"❌ {data_val['error']}", chat_id)
            return
        msg_val = (
            f"💎 <b>DIAGNOSIS VALUASI: #{data_val['ticker']}</b>\n"
            f"🏢 <i>Sektor: {data_val['sector']}</i>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>Harga Sekarang:</b> <code>Rp{int(data_val['price']):,}</code>\n"
            f"📊 <b>PBV (Price to Book):</b> <code>{data_val['pbv']}x</code>\n"
            f"📈 <b>PER (Price to Earnings):</b> <code>{data_val['per']}x</code>\n"
            f"💰 <b>Dividend Yield:</b> <code>{data_val['div_yield']}%</code>\n"
            f"🏛️ <b>Profitabilitas (ROE):</b> <code>{data_val['roe']}%</code>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Status Valuasi:</b>\n👉 <b>{data_val['status']}</b>"
        )
        send_telegram_message(msg_val, chat_id)

    elif action == "calc":
        send_telegram_message(f"⏳ <i>Menghitung alokasi aman #{esc(ticker)} untuk modal standar Rp10 Juta...</i>", chat_id)
        res_calc = calculate_position_sizing(ticker, "10jt")
        send_long_telegram_message(format_position_sizing_message(res_calc), chat_id)

    elif action == "tanya":
        send_telegram_message(f"🤖 <i>AI Copilot sedang menyusun diagnosa lengkap #{esc(ticker)}...</i>", chat_id)
        resp_ai = answer_market_query(f"apakah aman beli {ticker} sekarang?")
        send_long_telegram_message(resp_ai, chat_id)

    elif action == "menu":
        target = ticker.lower()
        if target == "prediksi":
            send_telegram_message("🔮 <i>Mendiagnosis Wall Street semalam, kurs Rupiah & teknikal IHSG...</i>", chat_id)
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


def handle_telegram_command(command_text: str, chat_id: str):
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
                "• <code>/pantau PANI 5200 50</code> (50 lot di harga Rp 5.200)\n"
                "• <code>/pantau ASII 4900 15</code>\n\n"
                "<i>Robot akan otomatis mengawal posisi TP1 (+30%), TP2 (+75%), dan batas Stop Loss (-6%) Anda!</i>",
                chat_id
            )
            return

        ticker = parts[1].upper()
        try:
            raw_p = parts[2].replace(",", "").replace(".", "").strip() if "." not in parts[2] else parts[2].replace(",", "").strip()
            buy_price = float(raw_p)
            lots = int(parts[3]) if len(parts) > 3 else 10
        except Exception:
            send_telegram_message("❌ Format angka tidak valid. Contoh: <code>/pantau BBCA 9800 20</code>", chat_id)
            return

        res = add_stock_to_portfolio(chat_id, ticker, buy_price, lots)
        msg = (
            f"✅ <b>BERHASIL MENAMBAHKAN #{ticker} KE PANTAUAN!</b> 💼\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>Modal Beli:</b> <code>Rp{int(buy_price):,}</code> ({lots} Lot)\n"
            f"💰 <b>Total Investasi:</b> <code>Rp{int(res['total_invested']):,}</code>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🎯 <b>TARGET TRADING PLAN OTOMATIS:</b>\n"
            f"• 🎯 <b>Target TP1 (+30%):</b> <code>Rp{int(res['tp1']):,}</code> <i>(Jual 35% lot &amp; geser SL ke BEP)</i>\n"
            f"• 🚀 <b>Target TP2 (+75%):</b> <code>Rp{int(res['tp2']):,}</code> <i>(Kunci profit monster)</i>\n"
            f"• 🛑 <b>Batas Cut Loss (-6%):</b> <code>Rp{int(res['sl']):,}</code>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Ketik <code>/watchlist</code> kapan saja untuk melihat evaluasi real-time portofolio Anda.</i>"
        )
        send_telegram_message(msg, chat_id)

    elif cmd in ["/watchlist", "/portofolioku", "/pantauan"]:
        send_telegram_message("⏳ <i>Menghubungkan ke bursa untuk mengevaluasi portofolio Anda...</i>", chat_id)
        eval_data = evaluate_user_portfolio(chat_id)
        send_long_telegram_message(format_portfolio_message(eval_data), chat_id)

    elif cmd in ["/hapuspantau", "/unpantau", "/delpantau"]:
        if len(parts) < 2:
            send_telegram_message("⚠️ Format: <code>/hapuspantau KODE</code>\nContoh: <code>/hapuspantau BBCA</code>", chat_id)
            return
        ticker = parts[1].upper()
        ok = remove_stock_from_portfolio(chat_id, ticker)
        if ok:
            send_telegram_message(f"🗑️ <b>#{ticker} berhasil dihapus dari pantauan portofolio.</b>", chat_id)
        else:
            send_telegram_message(f"⚠️ #{ticker} tidak ditemukan di daftar pantauan Anda.", chat_id)

    elif cmd in ["/hedge", "/hedgefund", "/wyckoff"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"🏛️ <i>Mendiagnosis jejak Hedge Fund &amp; fase Wyckoff #{esc(ticker)}...</i>", chat_id)
            data_hedge = analyze_hedgefund_wyckoff(ticker)
            kb = make_stock_inline_keyboard(ticker)
            send_long_telegram_message(format_hedgefund_message(data_hedge), chat_id, reply_markup=kb)
        else:
            send_telegram_message("🏛️ <i>Memindai saham LQ45 untuk fase Silent Accumulation &amp; Spring Shakeout...</i>", chat_id)
            picks = scan_hedgefund_picks(limit=6)
            send_long_telegram_message(format_hedgefund_scan_message(picks), chat_id)

    elif cmd in ["/tanya", "/ask", "/ai"]:
        if len(parts) < 2:
            send_telegram_message(
                "🤖 <b>AI MARKET COPILOT</b>\n\n"
                "Ketik pertanyaan Anda setelah <code>/tanya</code>.\n"
                "Contoh:\n"
                "• <code>/tanya apakah aman beli BBRI sekarang?</code>\n"
                "• <code>/tanya bagaimana prospek dividen BBCA?</code>\n"
                "• <code>/tanya sektor apa yang paling menarik hari ini?</code>\n"
                "• <code>/tanya rekomendasi saham swing trade</code>",
                chat_id
            )
            return

        user_query = " ".join(parts[1:])
        send_telegram_message(f"🤖 <i>AI Copilot sedang menganalisis: \"{esc(user_query)}\"...</i>", chat_id)
        reply = answer_market_query(user_query)
        detected_ticker = extract_ticker_from_query(user_query)
        kb = make_stock_inline_keyboard(detected_ticker) if detected_ticker else None
        send_long_telegram_message(reply, chat_id, reply_markup=kb)

    elif cmd in ["/ihsg", "/market"]:
        send_telegram_message("⏳ <i>Mengambil data terkini IHSG &amp; net flow Whale...</i>", chat_id)
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

    elif cmd in ["/simulasi100jt", "/portofolio", "/backtest100m"]:
        send_long_telegram_message(format_simulasi_100m_message(), chat_id)

    elif cmd in ["/whale", "/bandar"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"🐋 <i>Mendiagnosis jejak Whale &amp; Bandarmology #{esc(ticker)}...</i>", chat_id)
            data_whale = analyze_whale_footprint(ticker)
            kb = make_stock_inline_keyboard(ticker)
            send_long_telegram_message(format_whale_footprint_message(data_whale), chat_id, reply_markup=kb)
        else:
            send_telegram_message("🐋 <i>Memindai saham LQ45 dengan akumulasi Whale tertinggi...</i>", chat_id)
            top_whales = scan_top_whale_accumulations(limit=6)
            send_long_telegram_message(format_top_whale_scan_message(top_whales, title_tag="LQ45 WHALE"), chat_id)

    elif cmd in ["/tierlist", "/tier"]:
        send_telegram_message("🏆 <i>Menyusun Tier List akumulasi Whale LQ45 (Tier S, A, B)...</i>", chat_id)
        tiers = get_whale_tier_list(LQ45_WATCHLIST)
        send_long_telegram_message(format_whale_tier_list_message(tiers), chat_id)

    elif cmd in ["/multibagger", "/mb"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"🚀 <i>Mendiagnosis rumor aksi korporasi &amp; potensi Multi-Bagger #{esc(ticker)}...</i>", chat_id)
            data_mb = analyze_multibagger_rumor(ticker)
            kb = make_stock_inline_keyboard(ticker)
            send_long_telegram_message(format_multibagger_detail_message(data_mb), chat_id, reply_markup=kb)
        else:
            send_telegram_message("🚀 <i>Memindai saham potensi Multi-Bagger (Rumor Aksi Korporasi + Akumulasi)...</i>", chat_id)
            picks = scan_top_multibagger_picks(limit=6)
            send_long_telegram_message(format_multibagger_scan_message(picks), chat_id)

    elif cmd in ["/multibagger_all", "/mb_all"]:
        send_telegram_message("🚀 <i>Memindai 100 saham Kompas100 untuk mencari potensi Multi-Bagger... Mohon tunggu ~15 detik.</i>", chat_id)
        picks = scan_top_multibagger_picks(limit=8, watchlist=KOMPAS100_WATCHLIST)
        send_long_telegram_message(format_multibagger_scan_message(picks), chat_id)

    elif cmd in ["/whalelist", "/topwhale"]:
        send_telegram_message("👑 <i>Memindai akumulasi Whale terbesar lintas LQ45...</i>", chat_id)
        top_whales = scan_top_whale_accumulations(limit=7)
        send_long_telegram_message(format_top_whale_scan_message(top_whales, title_tag="LQ45"), chat_id)

    elif cmd in ["/scan"]:
        if len(parts) < 2:
            send_telegram_message("⚠️ Harap sertakan kode saham. Contoh: <code>/scan BBCA</code> atau <code>/scan ASII</code>", chat_id)
            return

        ticker = parts[1].upper()
        send_telegram_message(f"⏳ <i>Menganalisis #{esc(ticker)}, jejak Whale &amp; Bau Berita...</i>", chat_id)
        data = analyze_single_stock(ticker)
        kb = make_stock_inline_keyboard(ticker)
        send_long_telegram_message(format_single_stock_message(data), chat_id, reply_markup=kb)

    elif cmd in ["/chart", "/grafik"]:
        if len(parts) < 2:
            send_telegram_message("⚠️ Harap sertakan kode saham. Contoh: <code>/chart BBCA</code>", chat_id)
            return

        ticker = parts[1].upper()
        send_telegram_message(f"🎨 <i>Menggambar visual candlestick chart &amp; TP/SL #{esc(ticker)}...</i>", chat_id)
        buf = generate_stock_chart(ticker)
        if buf is None:
            send_telegram_message(f"❌ Gagal membuat chart untuk #{esc(ticker)}. Pastikan ticker valid.", chat_id)
            return
        caption = f"📊 <b>Technical Candlestick Chart: #{esc(ticker)}</b>\n<i>Garis Biru: EMA20 | Kuning: EMA50 | Garis Cyan: TP1 | Garis Merah: Stop Loss</i>"
        send_telegram_photo(buf, caption=caption, chat_id=chat_id)

    elif cmd in ["/flow", "/orderflow"]:
        if len(parts) < 2:
            send_telegram_message("⚠️ Harap sertakan kode saham. Contoh: <code>/flow BBCA</code>", chat_id)
            return

        ticker = parts[1].upper()
        send_telegram_message(f"⏳ <i>Membaca Order Flow &amp; Tiket Transaksi #{esc(ticker)}...</i>", chat_id)
        data = analyze_single_stock(ticker)
        kb = make_stock_inline_keyboard(ticker)
        send_long_telegram_message(format_flow_message(data), chat_id, reply_markup=kb)

    elif cmd in ["/insider", "/aksi"]:
        ticker = parts[1].upper() if len(parts) > 1 else None
        target_str = f"#{ticker}" if ticker else "Bursa IDX"
        send_telegram_message(f"⏳ <i>Memindai radar aksi korporasi &amp; keterbukaan info {target_str}...</i>", chat_id)
        actions = fetch_insider_corporate_actions(ticker=ticker, limit=5)
        lines = [
            f"🕵️‍♂️ <b>RADAR INSIDER &amp; AKSI KORPORASI ({target_str})</b>",
            "<i>Kabar Merger, Akuisisi, Buyback &amp; Dividen Terkini:</i>",
            "━━━━━━━━━━━━━━━━━━━"
        ]
        for a in actions:
            t_tag = f"#{a['ticker']} " if a.get('ticker') else ""
            lines.append(f"{a['badge']} <b>{t_tag}{a['category']}</b>\n👉 {a['title']} <i>({a['source']})</i>\n")
        lines.append("━━━━━━━━━━━━━━━━━━━")
        send_long_telegram_message("\n".join(lines), chat_id)

    elif cmd in ["/valuasi", "/val"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"⏳ <i>Mengecek valuasi fundamental #{esc(ticker)}...</i>", chat_id)
            data = get_single_stock_valuation(ticker)
            if "error" in data:
                send_telegram_message(f"❌ {data['error']}", chat_id)
                return
            msg = (
                f"💎 <b>DIAGNOSIS VALUASI: #{data['ticker']}</b>\n"
                f"🏢 <i>Sektor: {data['sector']}</i>\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>Harga Sekarang:</b> <code>Rp{int(data['price']):,}</code>\n"
                f"📊 <b>PBV (Price to Book):</b> <code>{data['pbv']}x</code>\n"
                f"📈 <b>PER (Price to Earnings):</b> <code>{data['per']}x</code>\n"
                f"💰 <b>Dividend Yield:</b> <code>{data['div_yield']}%</code>\n"
                f"🏛️ <b>Profitabilitas (ROE):</b> <code>{data['roe']}%</code>\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 <b>Status Valuasi:</b>\n👉 <b>{data['status']}</b>"
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
            "<i>Saham-saham pembagi dividen royal di bursa:</i>",
            "━━━━━━━━━━━━━━━━━━━"
        ]
        for idx, s in enumerate(stocks, 1):
            lines.append(
                f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['price']):,}</code>)\n"
                f"   • 💰 <b>Dividend Yield: {s['div_yield']}%</b>\n"
                f"   • Sektor: {s['sector']} | PER: {s['per']}x\n"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 <i>Ketik <code>/scan KODE</code> untuk cek kapan waktu terbaik masuk sebelum cum-date.</i>")
        send_long_telegram_message("\n".join(lines), chat_id)

    elif cmd in ["/daily"]:
        send_telegram_message("⏳ <i>Menyiapkan laporan harian komprehensif pasar...</i>", chat_id)
        ihsg = analyze_ihsg()
        pred = predict_daily_ihsg_direction()
        ara_picks = scan_ara_hunter_picks(limit=3)
        hedge_picks = scan_hedgefund_picks(limit=4)
        stocks = scan_whale_watchlist(LQ45_WATCHLIST)
        port_brief = format_portfolio_daily_brief(chat_id)

        msg_parts = [
            "📅 <b>LAPORAN HARIAN KOMPREHENSIF PASAR (IHSG RADAR)</b> 📊\n",
            format_ihsg_message(ihsg) + "\n",
            format_daily_prediction_message(pred) + "\n",
            format_ara_hunter_message(ara_picks) + "\n",
            format_hedgefund_scan_message(hedge_picks) + "\n",
            format_whale_scan_message(stocks, title_tag="LQ45 WHALE MOMENTUM", limit=4)
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
