import os
import sys
import time
import requests
from datetime import datetime
import threading

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


def send_telegram_message(text: str, chat_id: str = None, parse_mode: str = "HTML") -> bool:
    """Mengirim pesan ke Telegram menggunakan Telegram Bot API."""
    token = TELEGRAM_BOT_TOKEN
    target_id = chat_id or TELEGRAM_CHAT_ID

    if not token or not target_id:
        print("[WARNING] Token atau Chat ID Telegram belum diisi di .env")
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
        if resp.status_code == 200:
            return True
        else:
            print(f"[ERROR Telegram API] {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"[ERROR Request] {e}")
        return False


def format_ihsg_message(data: dict) -> str:
    """Memformat hasil analisis IHSG ke pesan Telegram yang rapi & estetik."""
    if "error" in data:
        return f"❌ <b>Error:</b> {data['error']}"

    change_sym = "+" if data["pct_change"] >= 0 else ""
    return (
        f"📊 <b>IHSG MARKET SIGNAL UPDATE</b> 🇮🇩\n"
        f"📅 <i>Tanggal: {data['date']}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Level IHSG:</b> <code>{data['close']:,.2f}</code> ({change_sym}{data['pct_change']:.2f}% | {change_sym}{data['change_pts']:.2f} pts)\n"
        f"📈 <b>Tren Pasar:</b> {data['trend_emoji']} <b>{data['trend']}</b>\n"
        f"⚡ <b>RSI (14):</b> <code>{data['rsi']:.1f}</code> — {data['rsi_desc']}\n"
        f"🌊 <b>MACD:</b> {data['macd_desc']}\n"
        f"🐋 <b>Whale Score Pasar:</b> <code>{data['whale_score']}/100</code> (CMF: {data['cmf']:.2f})\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <b>Support 1:</b> <code>{data['levels']['support_1']:,.0f}</code> | <b>Support 2:</b> <code>{data['levels']['support_2']:,.0f}</code>\n"
        f"🧱 <b>Resist 1:</b> <code>{data['levels']['resistance_1']:,.0f}</code> | <b>Resist 2:</b> <code>{data['levels']['resistance_2']:,.0f}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <b>REKOMENDASI PASAR:</b>\n"
        f"👉 <b>{data['action']}</b>\n"
        f"📝 <i>{data['action_note']}</i>\n"
    )


def format_single_stock_message(data: dict) -> str:
    """Memformat analisis saham tunggal + Bandarmology Whale ke Telegram."""
    if "error" in data:
        return f"❌ <b>Error:</b> {data['error']}"

    w = data["whale"]
    tp = data["trading_plan"]
    chg_sym = "+" if data["pct_change"] >= 0 else ""

    flow_str = f"+Rp{w['whale_flow_billion']:.1f} M" if w['whale_flow_billion'] >= 0 else f"-Rp{abs(w['whale_flow_billion']):.1f} M"

    reasons_text = ""
    if w["entry_reasons"]:
        reasons_text = "\n🔍 <b>Fakta Akumulasi:</b>\n" + "\n".join([f" • {r}" for r in w["entry_reasons"]])

    return (
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


def format_whale_scan_message(stocks: list, title_tag: str = "LQ45", limit: int = 7) -> str:
    """Memformat daftar saham teratas yang sedang diakumulasi Whale."""
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
        chg_sym = "+" if s["pct_change"] >= 0 else ""
        flow = f"+{w['whale_flow_billion']:.1f}M" if w['whale_flow_billion'] >= 0 else f"{w['whale_flow_billion']:.1f}M"
        lines.append(
            f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['close']):,}</code> | {chg_sym}{s['pct_change']:.1f}%)\n"
            f"   • Status: <b>{w['whale_status']}</b> ({w['whale_score']}/100)\n"
            f"   • Vol Spike: <b>{w['rvol']:.1f}x</b> | Flow: <b>{flow}</b>\n"
            f"   • TP: <code>Rp{s['trading_plan']['tp1']:,}</code> | SL: <code>Rp{s['trading_plan']['stop_loss']:,}</code>\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/scan KODE</code> (misal: <code>/scan BBCA</code>) untuk detail lengkap.</i>")
    return "\n".join(lines)


def handle_telegram_command(command_text: str, chat_id: str):
    """Memproses perintah yang diterima bot Telegram."""
    parts = command_text.strip().split()
    cmd = parts[0].lower() if parts else ""

    if cmd in ["/start", "/menu", "/help"]:
        help_msg = (
            "🤖 <b>IHSG & WHALE BANDARMOLOGY SIGNAL BOT</b>\n\n"
            "Bot ini memantau IHSG dan mendeteksi saham yang diakumulasi Whale / Smart Money "
            "dari seluruh <b>958 saham BEI</b> via Yahoo Finance API.\n\n"
            "📌 <b>Daftar Perintah Screening:</b>\n"
            "• <code>/ihsg</code> — Sinyal & analisis kondisi pasar IHSG terkini\n"
            "• <code>/whale</code> atau <code>/lq45</code> — Screening 45 saham terlikuid (LQ45)\n"
            "• <code>/kompas100</code> — Screening 100 saham Kompas100\n"
            "• <code>/whale_all</code> — Screening <b>seluruh 958 saham BEI</b> (dengan filter likuiditas)\n"
            "• <code>/scan KODE</code> — Analisis saham apapun (Contoh: <code>/scan BBCA</code> atau <code>/scan BREN</code>)\n"
            "• <code>/daily</code> — Ringkasan harian IHSG & Watchlist pilihan\n\n"
            "💡 <i>Selamat bertrading & utamakan Money Management!</i>"
        )
        send_telegram_message(help_msg, chat_id)

    elif cmd in ["/ihsg"]:
        send_telegram_message("⏳ <i>Sedang menganalisis data IHSG...</i>", chat_id)
        data = analyze_ihsg()
        send_telegram_message(format_ihsg_message(data), chat_id)

    elif cmd in ["/whale", "/lq45", "/akumulasi"]:
        send_telegram_message("⏳ <i>Memindai saham LQ45 untuk deteksi akumulasi Whale...</i>", chat_id)
        stocks = scan_whale_watchlist(LQ45_WATCHLIST)
        send_telegram_message(format_whale_scan_message(stocks, title_tag="LQ45"), chat_id)

    elif cmd in ["/kompas100"]:
        send_telegram_message("⏳ <i>Memindai 100 saham Kompas100 secara paralel...</i>", chat_id)
        stocks = scan_whale_watchlist(KOMPAS100_WATCHLIST)
        send_telegram_message(format_whale_scan_message(stocks, title_tag="KOMPAS 100"), chat_id)

    elif cmd in ["/whale_all", "/semua"]:
        total_tickers = len(ALL_IDX_TICKERS)
        send_telegram_message(f"⏳ <i>Memindai seluruh <b>{total_tickers} saham BEI</b> (Filter Likuiditas $\ge$ Rp500 Juta)... Mohon tunggu ~20-30 detik.</i>", chat_id)
        min_turnover = INDICATOR_CONFIG.get("min_turnover_billion", 0.5)
        stocks = scan_whale_watchlist(ALL_IDX_TICKERS, min_turnover_billion=min_turnover, max_workers=25)
        send_telegram_message(format_whale_scan_message(stocks, title_tag="ALL 958 IDX STOCKS", limit=10), chat_id)

    elif cmd in ["/scan"]:
        if len(parts) < 2:
            send_telegram_message("⚠️ Harap sertakan kode saham. Contoh: <code>/scan BBCA</code>", chat_id)
            return

        ticker = parts[1].upper()
        send_telegram_message(f"⏳ <i>Menganalisis #{ticker} dan jejak Whale...</i>", chat_id)
        data = analyze_single_stock(ticker)
        send_telegram_message(format_single_stock_message(data), chat_id)

    elif cmd in ["/daily"]:
        send_telegram_message("⏳ <i>Menyiapkan laporan harian pasar...</i>", chat_id)
        ihsg = analyze_ihsg()
        send_telegram_message(format_ihsg_message(ihsg), chat_id)
        stocks = scan_whale_watchlist(LQ45_WATCHLIST)
        send_telegram_message(format_whale_scan_message(stocks, title_tag="LQ45", limit=5), chat_id)

    else:
        # Jika user hanya ketik kode saham langsung (misal: BBCA atau CUAN)
        raw = cmd.replace("/", "").upper()
        if len(raw) in [4, 5] and raw.isalpha():
            send_telegram_message(f"⏳ <i>Menganalisis #{raw}...</i>", chat_id)
            data = analyze_single_stock(raw)
            send_telegram_message(format_single_stock_message(data), chat_id)


def start_bot_polling():
    """Menjalankan loop polling getUpdates Telegram Bot."""
    token = TELEGRAM_BOT_TOKEN
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("\n" + "="*60)
        print("⚠️  TELEGRAM_BOT_TOKEN BELUM DIISI!")
        print("1. Buka Telegram dan chat @BotFather untuk membuat bot baru.")
        print("2. Dapatkan API Token bot.")
        print("3. Buka file .env dan masukkan TELEGRAM_BOT_TOKEN=token_kamu")
        print("4. Kamu juga bisa menguji sinyal langsung di terminal dengan: py cli.py")
        print("="*60 + "\n")
        return

    print("🤖 Bot Telegram IHSG Signal & Whale Monitor aktif...")
    print(f"Total Saham Universe Terdaftar: {len(ALL_IDX_TICKERS)} saham")
    print("Menunggu perintah dari Telegram (Tekan Ctrl+C untuk berhenti)...")

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
                    user = msg.get("from", {}).get("username", "User")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Pesan dari @{user} ({chat_id}): {text}")

                    handle_telegram_command(text, chat_id)
            else:
                time.sleep(2)
        except Exception as e:
            print(f"[Polling Error] {e}")
            time.sleep(3)


def scheduled_worker():
    """Worker background untuk mengirim alert terjadwal (pagi & sore)."""
    print("⏰ Background scheduler aktif untuk notifikasi pasar...")
    already_sent = {"morning": "", "closing": ""}

    while True:
        try:
            now_str = datetime.now().strftime("%H:%M")
            today_str = datetime.now().strftime("%Y-%m-%d")

            # Morning Brief (08:30 WIB)
            if now_str == SCHEDULED_ALERTS.get("morning_brief", "08:30") and already_sent["morning"] != today_str:
                if TELEGRAM_CHAT_ID:
                    print("📢 Mengirim Morning Briefing ke Telegram...")
                    ihsg = analyze_ihsg()
                    send_telegram_message("🌅 <b>MORNING MARKET BRIEFING IHSG</b>\n" + format_ihsg_message(ihsg))
                    already_sent["morning"] = today_str

            # Closing Report (16:15 WIB)
            if now_str == SCHEDULED_ALERTS.get("market_closing", "16:15") and already_sent["closing"] != today_str:
                if TELEGRAM_CHAT_ID:
                    print("📢 Mengirim Closing Report ke Telegram...")
                    ihsg = analyze_ihsg()
                    stocks = scan_whale_watchlist(LQ45_WATCHLIST)
                    send_telegram_message("🌇 <b>POST-MARKET CLOSING REPORT</b>\n" + format_ihsg_message(ihsg))
                    send_telegram_message(format_whale_scan_message(stocks, title_tag="LQ45", limit=5))
                    already_sent["closing"] = today_str

            time.sleep(30)
        except Exception as e:
            print(f"[Scheduler Error] {e}")
            time.sleep(30)
