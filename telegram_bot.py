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

esc = html.escape
_command_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="cmd")


def make_stock_inline_keyboard(ticker: str) -> dict:
    """
    Membuat tombol interaktif Telegram sekali klik untuk saham tertentu.
    """
    t = ticker.replace(".JK", "").strip().upper()
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Buka Chart", "callback_data": f"chart:{t}"},
                {"text": "🌊 Order Flow", "callback_data": f"flow:{t}"}
            ],
            [
                {"text": "💎 Cek Valuasi", "callback_data": f"val:{t}"},
                {"text": "🕵️ Aksi Korporasi", "callback_data": f"insider:{t}"}
            ],
            [
                {"text": "🧮 Hitung Lot (10jt)", "callback_data": f"calc:{t}"},
                {"text": "🤖 Tanya AI Copilot", "callback_data": f"tanya:{t}"}
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
        resp = requests.post(url, data=data, files=files, timeout=30)
        return resp.status_code == 200
    except Exception as e:
        print(f"[ERROR sendPhoto] {e}")
        return False


def send_long_telegram_message(text: str, chat_id: str = None, parse_mode: str = "HTML", reply_markup: dict = None) -> bool:
    MAX_LEN = 4000
    if len(text) <= MAX_LEN:
        return send_telegram_message(text, chat_id, parse_mode, reply_markup=reply_markup)

    chunks = []
    while text:
        if len(text) <= MAX_LEN:
            chunks.append(text)
            break
        split_idx = text.rfind("\n", 0, MAX_LEN)
        if split_idx == -1:
            split_idx = MAX_LEN
        chunks.append(text[:split_idx])
        text = text[split_idx:].lstrip("\n")

    success = True
    for i, chunk in enumerate(chunks):
        rm = reply_markup if i == len(chunks) - 1 else None
        if not send_telegram_message(chunk, chat_id, parse_mode, reply_markup=rm):
            success = False
    return success


def answer_telegram_callback(callback_query_id: str):
    """
    Menjawab callback query agar ikon loading di tombol Telegram berhenti.
    """
    token = TELEGRAM_BOT_TOKEN
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_query_id}, timeout=10)
    except Exception:
        pass


def format_ihsg_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error:</b> {esc(str(data['error']))}"

    change_sym = "+" if data["pct_change"] >= 0 else ""
    return (
        f"📊 <b>IHSG MARKET SIGNAL UPDATE</b> 🇮🇩\n"
        f"📅 <i>Tanggal: {esc(str(data['date']))}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Level IHSG:</b> <code>{data['close']:,.2f}</code> ({change_sym}{data['pct_change']:.2f}% | {change_sym}{data['change_pts']:.2f} pts)\n"
        f"📈 <b>Tren Pasar:</b> {data['trend_emoji']} <b>{esc(str(data['trend']))}</b>\n"
        f"⚡ <b>Momentum:</b> <b>{esc(str(data['momentum']))}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Indikator Kunci:</b>\n"
        f"• RSI (14): <code>{data['rsi']}</code> — <i>{esc(str(data['rsi_status']))}</i>\n"
        f"• MA20: <code>{data['ma20']:,.2f}</code> | MA50: <code>{data['ma50']:,.2f}</code>\n"
        f"• Support: <code>{data['support']:,.2f}</code> | Resistance: <code>{data['resistance']:,.2f}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <b>Strategi:</b>\n"
        f"👉 <b>{esc(str(data['recommendation']))}</b>"
    )


def format_single_stock_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Gagal Menganalisis Saham:</b> {esc(str(data['error']))}"

    w = data["whale"]
    tp = data["trading_plan"]
    chg_sym = "+" if data["pct_change"] >= 0 else ""
    flow_str = f"+Rp{w['whale_flow_billion']:.1f} M" if w['whale_flow_billion'] >= 0 else f"-Rp{abs(w['whale_flow_billion']):.1f} M"

    reasons_text = ""
    if w.get("entry_reasons"):
        reasons_text = "\n🔍 <b>Fakta Akumulasi:</b>\n" + "\n".join([f" • {r}" for r in w["entry_reasons"]])

    res = (
        f"💎 <b>ANALISIS SAHAM &amp; WHALE FLOW: #{data['ticker']}</b>\n"
        f"📅 <i>Tanggal: {data['date']}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Harga Terakhir:</b> <code>Rp{int(data['close']):,}</code> ({chg_sym}{data['pct_change']:.2f}%)\n"
        f"🏷️ <b>Sinyal:</b> {data['signal_badge']}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🐋 <b>BANDARMOLOGY &amp; WHALE METRICS:</b>\n"
        f" • Status: <b>{w['whale_status']}</b>\n"
        f" • Skor Akumulasi: <b>{w['whale_score']}/100</b>\n"
        f" • RVOL (Lonjakan Vol): <b>{w['rvol']:.2f}x</b> dari rata-rata\n"
        f" • Est. Net Whale Flow: <b>{flow_str}</b>\n"
        f" • Est. Harga Beli Whale (VWAP): <code>Rp{int(w['whale_vwap']):,}</code> ({w['pct_from_vwap']:+.1f}% vs harga)\n"
        f" • Profil Lot: 🐋 <b>Jumbo {w.get('lot_profile', {}).get('jumbo_pct', 50)}%</b> | 🐜 Retail {w.get('lot_profile', {}).get('retail_pct', 30)}%\n"
        f" • <i>{w.get('lot_profile', {}).get('summary', '')}</i>\n"
        f"{reasons_text}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📐 <b>INDIKATOR TEKNIKAL:</b>\n"
        f" • EMA 20: <code>{int(data['ema20']):,}</code> | EMA 50: <code>{int(data['ema50']):,}</code>\n"
        f" • RSI 14: <code>{data['rsi']:.1f}</code>\n"
        f" • Support: <code>Rp{int(data['levels']['support_1']):,}</code>\n"
        f" • Resistance: <code>Rp{int(data['levels']['resistance_1']):,}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>TRADING PLAN REKOMENDASI (SWING):</b>\n"
        f" • Area Beli: <code>Rp{tp['entry_area']}</code>\n"
        f" • Target 1 (TP1): <code>Rp{tp['tp1']:,}</code>\n"
        f" • Target 2 (TP2): <code>Rp{tp['tp2']:,}</code>\n"
        f" • Stop Loss (SL): <code>Rp{tp['stop_loss']:,}</code>\n"
        f" • Risk/Reward Ratio: <b>{tp['rr_ratio']}x</b>\n"
    )

    sent = data.get("sentiment", {})
    if sent:
        news_lines = [
            f"\n📰 <b>BAU SENTIMEN BERITA &amp; KATALIS:</b> {sent.get('badge', '⚪')}",
            f"<i>{sent.get('catalyst_summary', '')}</i>"
        ]
        headlines = sent.get("headlines", [])
        if headlines:
            news_lines.append("<b>Top Berita Terkini:</b>")
            for h in headlines[:3]:
                news_lines.append(f" {h['tag']} {h['title']} <i>({h['source']})</i>")
        res += "\n━━━━━━━━━━━━━━━━━━━\n" + "\n".join(news_lines)

    return res


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
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⚖️ <b>TEKANAN VOLUME &amp; MONEY FLOW:</b>\n"
        f"• Arah Arus Uang: <b>{domination}</b>\n"
        f"• Net Whale Flow: <b>{flow_str}</b>\n"
        f"• Chaikin Money Flow: <code>{w['cmf']:.3f}</code>\n"
        f"• Lonjakan Vol (RVOL): <code>{w['rvol']:.2f}x</code> dari rata-rata\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🐋 <b>PROFIL UKURAN TRANSAKSI (TICKET SIZE):</b>\n"
        f"• 🐋 <b>Order Jumbo (Bandar/Institusi):</b> <code>{jumbo}%</code>\n"
        f"  [{bar_jumbo}]\n"
        f"• 🐜 <b>Order Retail (Semut/FOMO):</b> <code>{retail}%</code>\n"
        f"  [{bar_retail}]\n"
        f"• 📦 <b>Order Menengah:</b> <code>{medium}%</code>\n\n"
        f"💡 <i>{lot.get('summary', '')}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>MODAL BANDAR &amp; TOLOK UKUR:</b>\n"
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
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Total Modal Alokasi:</b> <code>Rp{int(data['capital']):,}</code>\n"
        f"💵 <b>Harga Saham Saat Ini:</b> <code>Rp{data['price']:,}</code> (Rp{data['cost_per_lot']:,}/lot)\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <b>REKOMENDASI PORSI AMAN (RISK 2%):</b>\n"
        f"• Alokasi Aman: <b>{data['recommended_lots']} Lot</b> ({data['recommended_lots'] * 100:,} lembar)\n"
        f"• Total Modal Dipakai: <code>Rp{data['total_spent']:,}</code>\n"
        f"• Sisa Kas Aman (Cash Buffer): <code>Rp{data['cash_remaining']:,}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>SKENARIO PROFIT / LOSS:</b>\n"
        f"• Target TP1: <code>Rp{data['tp1']:,}</code> (+{data['profit_pct']}%)\n"
        f"  👉 Potensi Cuan: <b>+Rp{data['profit_potential']:,}</b>\n"
        f"• Stop Loss (SL): <code>Rp{data['sl']:,}</code> ({data['loss_pct']}%)\n"
        f"  👉 Resiko Toleransi: <b>-Rp{data['loss_potential']:,}</b>\n"
        f"• Reward to Risk Ratio: <b>{data['rr_ratio']}x</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Catatan: Jangan all-in pada 1 saham. Disiplin cut loss bila tembus SL!</i>"
    )


def format_sector_rotation_message(sectors: list) -> str:
    if not sectors:
        return "⚠️ Gagal mengambil data rotasi sektor."

    lines = [
        "🔄 <b>RADAR ROTASI SEKTOR IHSG (FUND FLOW)</b> 📊",
        "<i>Mendeteksi ke sektor mana arus dana Big Money sedang mengalir hari ini:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    for idx, s in enumerate(sectors, 1):
        arrow = "🟢" if s["avg_change"] > 0 else ("🔴" if s["avg_change"] < 0 else "⚪")
        chg_sym = "+" if s["avg_change"] > 0 else ""
        leader_sym = "+" if s["leader_pct"] > 0 else ""
        lines.append(
            f"{arrow} <b>{s['sector']}</b>\n"
            f"   • Rata-rata: <b>{chg_sym}{s['avg_change']:.2f}%</b>\n"
            f"   • Top Stock: <b>#{s['leader']}</b> ({leader_sym}{s['leader_pct']:.2f}%)\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/scan KODE</code> pada saham pemimpin sektor yang sedang naik untuk momentum swing.</i>")
    return "\n".join(lines)


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
    """
    Menangani aksi klik tombol interaktif Telegram inline keyboard.
    """
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

    elif action == "flow":
        send_telegram_message(f"⏳ <i>Membaca Order Flow &amp; Tiket Transaksi #{esc(ticker)}...</i>", chat_id)
        data_flow = analyze_single_stock(ticker)
        send_long_telegram_message(format_flow_message(data_flow), chat_id)

    elif action == "val":
        send_telegram_message(f"⏳ <i>Mengecek valuasi fundamental #{esc(ticker)}...</i>", chat_id)
        data_val = get_single_stock_valuation(ticker)
        if "error" in data_val:
            send_telegram_message(f"❌ {data_val['error']}", chat_id)
            return
        msg_val = (
            f"💎 <b>DIAGNOSIS VALUASI: #{data_val['ticker']}</b>\n"
            f"🏢 <i>Sektor: {data_val['sector']}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>Harga Sekarang:</b> <code>Rp{int(data_val['price']):,}</code>\n"
            f"📊 <b>PBV (Price to Book):</b> <code>{data_val['pbv']}x</code>\n"
            f"📈 <b>PER (Price to Earnings):</b> <code>{data_val['per']}x</code>\n"
            f"💰 <b>Dividend Yield:</b> <code>{data_val['div_yield']}%</code>\n"
            f"🏛️ <b>Profitabilitas (ROE):</b> <code>{data_val['roe']}%</code>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Status Valuasi:</b>\n👉 <b>{data_val['status']}</b>"
        )
        send_telegram_message(msg_val, chat_id)

    elif action == "insider":
        send_telegram_message(f"⏳ <i>Memindai aksi korporasi &amp; keterbukaan info #{esc(ticker)}...</i>", chat_id)
        actions = fetch_insider_corporate_actions(ticker=ticker, limit=4)
        lines = [
            f"🕵️‍♂️ <b>RADAR INSIDER &amp; AKSI KORPORASI (#{esc(ticker)})</b>",
            "━━━━━━━━━━━━━━━━━━━"
        ]
        if not actions:
            lines.append("<i>Tidak ditemukan aksi korporasi khusus baru-baru ini.</i>")
        else:
            for a in actions:
                lines.append(f"{a['badge']} <b>{a['category']}</b>\n👉 {a['title']} <i>({a['source']})</i>\n")
        lines.append("━━━━━━━━━━━━━━━━━━━")
        send_long_telegram_message("\n".join(lines), chat_id)

    elif action == "calc":
        send_telegram_message(f"⏳ <i>Menghitung alokasi aman #{esc(ticker)} untuk modal standar Rp10 Juta...</i>", chat_id)
        res_calc = calculate_position_sizing(ticker, "10jt")
        send_long_telegram_message(format_position_sizing_message(res_calc), chat_id)

    elif action == "tanya":
        send_telegram_message(f"🤖 <i>AI Copilot sedang menyusun diagnosa lengkap #{esc(ticker)}...</i>", chat_id)
        resp_ai = answer_market_query(f"apakah aman beli {ticker} sekarang?")
        send_long_telegram_message(resp_ai, chat_id)


def handle_telegram_command(command_text: str, chat_id: str):
    parts = command_text.strip().split()
    if not parts:
        return

    cmd = parts[0].split("@")[0].lower()

    if cmd in ["/start", "/menu", "/help"]:
        help_msg = (
            "🤖 <b>IHSG &amp; WHALE BANDARMOLOGY SIGNAL BOT</b>\n\n"
            "Bot ini memantau IHSG dan mendeteksi saham yang diakumulasi Whale / Smart Money "
            "dari seluruh <b>958 saham BEI</b> dilengkapi dengan <b>AI Market Copilot</b>.\n\n"
            "📌 <b>Daftar Perintah Screening &amp; Sinyal:</b>\n"
            "• <code>/tanya [PERTANYAAN]</code> — Tanya jawab pasar &amp; saham bebas ke AI Copilot\n"
            "• <code>/scan KODE</code> — Analisis saham + Tombol Interaktif Pintar\n"
            "• <code>/chart KODE</code> — Grafik Candlestick teknikal + MA20/50 + TP/SL\n"
            "• <code>/calc KODE MODAL</code> — Hitung lot aman &amp; risiko (Misal: <code>/calc BBCA 10jt</code>)\n"
            "• <code>/sektor</code> — Radar rotasi arus dana antar sektor bursa\n"
            "• <code>/flow KODE</code> — Analisis Order Flow murni + Profil Order Jumbo Bandar\n"
            "• <code>/ihsg</code> — Sinyal &amp; analisis kondisi pasar IHSG terkini\n"
            "• <code>/whale</code> atau <code>/lq45</code> — Screening 45 saham terlikuid (LQ45)\n"
            "• <code>/insider [KODE]</code> — Radar Aksi Korporasi &amp; Keterbukaan Info\n"
            "• <code>/undervalued [KODE]</code> — Cek Saham Murah / Screener Lintas Sektor\n"
            "• <code>/dividen</code> — Radar Saham dengan Dividend Yield Tertinggi\n"
            "• <code>/daily</code> — Ringkasan harian IHSG &amp; Watchlist pilihan\n\n"
            "💡 <i>Tip: Sekarang Anda bisa klik tombol interaktif di bawah pesan tanpa perlu ketik ulang!</i>"
        )
        send_long_telegram_message(help_msg, chat_id)

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
        send_telegram_message("🤖 <i>AI Copilot sedang menganalisis pasar &amp; menyusun diagnosa...</i>", chat_id)
        ans = answer_market_query(user_query)
        ticker_found = extract_ticker_from_query(user_query)
        kb = make_stock_inline_keyboard(ticker_found) if ticker_found else None
        send_long_telegram_message(ans, chat_id, reply_markup=kb)

    elif cmd in ["/ihsg"]:
        send_telegram_message("⏳ <i>Sedang menganalisis data IHSG...</i>", chat_id)
        data = analyze_ihsg()
        send_long_telegram_message(format_ihsg_message(data), chat_id)

    elif cmd in ["/whale", "/lq45", "/akumulasi"]:
        send_telegram_message("⏳ <i>Memindai saham LQ45 untuk deteksi akumulasi Whale...</i>", chat_id)
        stocks = scan_whale_watchlist(LQ45_WATCHLIST)
        send_long_telegram_message(format_whale_scan_message(stocks, title_tag="LQ45"), chat_id)

    elif cmd in ["/kompas100"]:
        send_telegram_message("⏳ <i>Memindai 100 saham Kompas100 secara paralel...</i>", chat_id)
        stocks = scan_whale_watchlist(KOMPAS100_WATCHLIST)
        send_long_telegram_message(format_whale_scan_message(stocks, title_tag="KOMPAS 100"), chat_id)

    elif cmd in ["/whale_all", "/semua"]:
        total_tickers = len(ALL_IDX_TICKERS)
        send_telegram_message(f"⏳ <i>Memindai seluruh <b>{total_tickers} saham BEI</b>... Mohon tunggu ~20-30 detik.</i>", chat_id)
        min_turnover = INDICATOR_CONFIG.get("min_turnover_billion", 0.5)
        stocks = scan_whale_watchlist(ALL_IDX_TICKERS, min_turnover_billion=min_turnover, max_workers=8)
        send_long_telegram_message(format_whale_scan_message(stocks, title_tag="ALL 958 IDX STOCKS", limit=10), chat_id)

    elif cmd in ["/scan"]:
        if len(parts) < 2:
            send_telegram_message("⚠️ Harap sertakan kode saham. Contoh: <code>/scan BBCA</code>", chat_id)
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
            send_telegram_message(f"❌ Gagal membuat chart untuk #{esc(ticker)}. Pastikan kode benar.", chat_id)
            return
        caption = f"📊 <b>Technical Candlestick Chart: #{esc(ticker)}</b>\n<i>Garis Biru: EMA20 | Kuning: EMA50 | Cyan: TP1 | Merah: Stop Loss</i>"
        if not send_telegram_photo(buf, caption=caption, chat_id=chat_id):
            send_telegram_message(f"❌ Gagal mengirim gambar chart #{esc(ticker)} ke Telegram.", chat_id)

    elif cmd in ["/calc", "/hitung", "/money"]:
        if len(parts) < 3:
            send_telegram_message(
                "⚠️ Format salah! Gunakan: <code>/calc [KODE] [MODAL]</code>\nContoh: <code>/calc BBCA 10jt</code> atau <code>/calc BBRI 25000000</code>",
                chat_id
            )
            return

        ticker = parts[1].upper()
        capital_str = parts[2]
        send_telegram_message(f"⏳ <i>Menghitung alokasi aman lot #{esc(ticker)} untuk modal {esc(capital_str)}...</i>", chat_id)
        res = calculate_position_sizing(ticker, capital_str)
        send_long_telegram_message(format_position_sizing_message(res), chat_id)

    elif cmd in ["/sektor", "/sector"]:
        send_telegram_message("⏳ <i>Memindai performa dan arus rotasi sektor IHSG...</i>", chat_id)
        sectors = scan_sector_rotation()
        send_long_telegram_message(format_sector_rotation_message(sectors), chat_id)

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
        if not actions:
            lines.append("<i>Tidak ditemukan aksi korporasi khusus baru-baru ini.</i>")
        else:
            for a in actions:
                lines.append(f"{a['badge']} <b>{a['category']}</b>\n👉 {a['title']} <i>({a['source']})</i>\n")
        lines.append("━━━━━━━━━━━━━━━━━━━")
        send_long_telegram_message("\n".join(lines), chat_id)

    elif cmd in ["/undervalued", "/berlian", "/murah"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"⏳ <i>Mengecek valuasi fundamental #{ticker}...</i>", chat_id)
            data = get_single_stock_valuation(ticker)
            if "error" in data:
                send_telegram_message(f"❌ {data['error']}", chat_id)
                return
            msg = (
                f"💎 <b>DIAGNOSIS VALUASI: #{data['ticker']}</b>\n"
                f"🏢 <i>Sektor: {data['sector']}</i>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>Harga Sekarang:</b> <code>Rp{int(data['price']):,}</code>\n"
                f"📊 <b>PBV (Price to Book):</b> <code>{data['pbv']}x</code>\n"
                f"📈 <b>PER (Price to Earnings):</b> <code>{data['per']}x</code>\n"
                f"💰 <b>Dividend Yield:</b> <code>{data['div_yield']}%</code>\n"
                f"🏛️ <b>Profitabilitas (ROE):</b> <code>{data['roe']}%</code>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
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
                    f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['price']):,}</code> | Sektor: {s['sector']})\n"
                    f"   • PBV: <b>{s['pbv']}x</b> | PER: <b>{s['per']}x</b>\n"
                    f"   • ROE: <b>{s['roe']}%</b> | Div Yield: <b>{s['div_yield']}%</b>\n"
                    f"   • Diskon Fundamental: <b>{s['discount_score']}/100</b>\n"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━")
            send_long_telegram_message("\n".join(lines), chat_id)

    elif cmd in ["/dividen", "/dividend"]:
        send_telegram_message("⏳ <i>Memindai saham-saham dengan Dividend Yield tertinggi di IDX...</i>", chat_id)
        stocks = scan_high_dividend_stocks(LQ45_WATCHLIST, limit=5)
        lines = [
            "💰 <b>TOP DIVIDEND YIELD RADAR (PASIF INCOME)</b> 💵",
            "<i>Saham pemberi bagi hasil dividen paling royal di bursa:</i>",
            "━━━━━━━━━━━━━━━━━━━"
        ]
        for idx, s in enumerate(stocks, 1):
            lines.append(
                f"<b>{idx}. #{s['ticker']}</b> — <code>Rp{int(s['price']):,}</code>\n"
                f"   • 💰 <b>Dividend Yield: {s['div_yield']}%</b>\n"
                f"   • Sektor: {s['sector']} | PER: {s['per']}x\n"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 <i>Ketik <code>/scan KODE</code> untuk cek kapan waktu terbaik masuk sebelum cum-date.</i>")
        send_long_telegram_message("\n".join(lines), chat_id)

    elif cmd in ["/daily"]:
        send_telegram_message("⏳ <i>Menyiapkan laporan harian pasar...</i>", chat_id)
        ihsg = analyze_ihsg()
        send_long_telegram_message(format_ihsg_message(ihsg), chat_id)
        stocks = scan_whale_watchlist(LQ45_WATCHLIST)
        send_long_telegram_message(format_whale_scan_message(stocks, title_tag="LQ45", limit=5), chat_id)

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
                    stocks = scan_whale_watchlist(LQ45_WATCHLIST)
                    msg = (
                        "🌅 <b>MORNING MARKET RADAR &amp; WHALE PICKS (08:30 WIB)</b>\n"
                        "<i>30 Menit Menuju Pembukaan Sesi 1 IHSG!</i>\n\n"
                        + format_ihsg_message(ihsg) + "\n\n"
                        + format_whale_scan_message(stocks, title_tag="LQ45 MORNING", limit=5)
                    )
                    send_long_telegram_message(msg)
                    already_sent["morning"] = today_str

            # Closing Report (16:15 WIB)
            if now_str == SCHEDULED_ALERTS.get("market_closing", "16:15") and already_sent["closing"] != today_str:
                if TELEGRAM_CHAT_ID:
                    ihsg = analyze_ihsg()
                    stocks = scan_whale_watchlist(LQ45_WATCHLIST)
                    msg = (
                        "🌇 <b>POST-MARKET CLOSING REPORT &amp; WHALE PICKS (16:15 WIB)</b>\n\n"
                        + format_ihsg_message(ihsg) + "\n\n"
                        + format_whale_scan_message(stocks, title_tag="LQ45 CLOSING", limit=5)
                    )
                    send_long_telegram_message(msg)
                    already_sent["closing"] = today_str

            time.sleep(30)
        except Exception as e:
            print(f"[Scheduler Error] {e}")
            time.sleep(30)
