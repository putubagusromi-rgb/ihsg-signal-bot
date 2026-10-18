import os
import sys
import time
import requests
import html
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

esc = html.escape
_command_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="cmd")


def send_telegram_message(text: str, chat_id: str = None, parse_mode: str = "HTML") -> bool:
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

    try:
        resp = requests.post(url, json=payload, timeout=15)
        return resp.status_code == 200
    except Exception as e:
        print(f"[ERROR Request] {e}")
        return False


def send_long_telegram_message(text: str, chat_id: str = None, parse_mode: str = "HTML") -> bool:
    MAX_LEN = 4000
    if len(text) <= MAX_LEN:
        return send_telegram_message(text, chat_id, parse_mode)

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
    for chunk in chunks:
        if not send_telegram_message(chunk, chat_id, parse_mode):
            success = False
    return success


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
        f"💎 <b>ANALISIS SAHAM & WHALE FLOW: #{data['ticker']}</b>\n"
        f"📅 <i>Tanggal: {data['date']}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Harga Terakhir:</b> <code>Rp{int(data['close']):,}</code> ({chg_sym}{data['pct_change']:.2f}%)\n"
        f"🏷️ <b>Sinyal:</b> {data['signal_badge']}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🐋 <b>BANDARMOLOGY & WHALE METRICS:</b>\n"
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
            f"\n📰 <b>BAU SENTIMEN BERITA & KATALIS:</b> {sent.get('badge', '⚪')}",
            f"<i>{sent.get('catalyst_summary', '')}</i>"
        ]
        headlines = sent.get("headlines", [])
        if headlines:
            news_lines.append("<b>Top Berita Terkini:</b>")
            for h in headlines[:3]:
                news_lines.append(f" {h['tag']} {h['title']} <i>({h['source']})</i>")
        res += "\n━━━━━━━━━━━━━━━━━━━\n" + "\n".join(news_lines)

    return res


def format_whale_scan_message(stocks: list, title_tag: str = "LQ45", limit: int = 7) -> str:
    if not stocks:
        return f"⚠️ Tidak ditemukan saham yang memenuhi kriteria akumulasi aktif di kategori {title_tag}."

    top_stocks = stocks[:limit]
    lines = [
        f"🐋 <b>TOP WHALE ACCUMULATION ({title_tag})</b> 🚀",
        "<i>Berdasarkan Volume Spike, Chaikin Money Flow & Breakout</i>",
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


def handle_telegram_command(command_text: str, chat_id: str):
    parts = command_text.strip().split()
    if not parts:
        return

    cmd = parts[0].split("@")[0].lower()

    if cmd in ["/start", "/menu", "/help"]:
        help_msg = (
            "🤖 <b>IHSG &amp; WHALE BANDARMOLOGY SIGNAL BOT</b>\n\n"
            "Bot ini memantau IHSG dan mendeteksi saham yang diakumulasi Whale / Smart Money "
            "dari seluruh <b>958 saham BEI</b> via Yahoo Finance API &amp; Radar Berita.\n\n"
            "📌 <b>Daftar Perintah Screening:</b>\n"
            "• <code>/ihsg</code> — Sinyal &amp; analisis kondisi pasar IHSG terkini\n"
            "• <code>/whale</code> atau <code>/lq45</code> — Screening 45 saham terlikuid (LQ45)\n"
            "• <code>/kompas100</code> — Screening 100 saham Kompas100\n"
            "• <code>/whale_all</code> — Screening <b>seluruh 958 saham BEI</b>\n"
            "• <code>/scan KODE</code> — Analisis saham + Sentimen Berita + Profil Lot Jumbo\n"
            "• <code>/daily</code> — Ringkasan harian IHSG &amp; Watchlist pilihan\n\n"
            "💡 <i>Selamat bertrading &amp; utamakan Money Management!</i>"
        )
        send_long_telegram_message(help_msg, chat_id)

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
        send_long_telegram_message(format_single_stock_message(data), chat_id)

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
            send_long_telegram_message(format_single_stock_message(data), chat_id)


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
