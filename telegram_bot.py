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
    """Mengirim pesan ke Telegram menggunakan Telegram Bot API."""
    token = TELEGRAM_BOT_TOKEN
    target_id = chat_id or TELEGRAM_CHAT_ID

    if not token or not target_id:
        print("[WARNING] Token atau Chat ID Telegram belum diisi!")
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


def send_long_telegram_message(text: str, chat_id: str = None, parse_mode: str = "HTML") -> bool:
    """Memecah pesan jika melebihi 4000 karakter agar tidak ditolak Telegram."""
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
    """Memformat hasil analisis IHSG ke pesan Telegram yang rapi & estetik."""
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
        f"• MACD: <code>{data['macd']}</code> ({esc(str(data['macd_signal']))})\n"
        f"• MA20: <code>{data['ma20']:,.2f}</code> | MA50: <code>{data['ma50']:,.2f}</code>\n"
        f"• Support: <code>{data['support']:,.2f}</code> | Resistance: <code>{data['resistance']:,.2f}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <b>Strategi:</b>\n"
        f"👉 <b>{esc(str(data['recommendation']))}</b>"
    )


def format_single_stock_message(data: dict) -> str:
    """Memformat hasil analisis teknikal & bandarmology saham tunggal."""
    if "error" in data:
        return f"❌ <b>Gagal Menganalisis Saham:</b> {esc(str(data['error']))}"

    sym = "+" if data["pct_change"] >= 0 else ""
    return (
        f"🔍 <b>ANALISIS SAHAM #{esc(str(data['ticker']))}</b>\n"
        f"🏢 <i>Bursa Efek Indonesia (IDX)</i>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Harga:</b> <code>Rp{data['close']:,}</code> ({sym}{data['pct_change']:.2f}%)\n"
        f"🐋 <b>Whale Score:</b> <code>{data['whale_score']}/100</code> ({esc(str(data['whale_status']))})\n"
        f"🌊 <b>Net Flow Whale:</b> <code>{data['net_flow_whale']}</code>\n"
        f"📊 <b>Relative Vol (RVOL):</b> <code>{data['rvol']}x</code>\n"
        f"🌊 <b>Chaikin Money Flow:</b> <code>{data['cmf']}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>TRADING PLAN REKOMENDASI:</b>\n"
        f"• Signal: <b>{esc(str(data['signal_badge']))} {esc(str(data['signal']))}</b>\n"
        f"• Area Beli: <code>Rp{data['entry_area']}</code>\n"
        f"• Target 1: <code>Rp{data['tp1']:,}</code> (+{data['tp1_pct']:.1f}%)\n"
        f"• Target 2: <code>Rp{data['tp2']:,}</code> (+{data['tp2_pct']:.1f}%)\n"
        f"• Stop Loss: <code>Rp{data['stop_loss']:,}</code> (-{data['sl_pct']:.1f}%)\n"
        f"• R:R Ratio: <b>1 : {data['rr_ratio']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>DYOR — Keputusan investasi ada di tangan Anda.</i>"
    )


def format_whale_scan_message(stocks: list, title_tag: str = "LQ45", limit: int = 7) -> str:
    """Memformat daftar saham hasil screening akumulasi Whale."""
    if not stocks:
        return f"🔍 <b>WHALE RADAR [{esc(title_tag)}]</b>\n\nTidak ada saham yang memenuhi kriteria akumulasi kuat hari ini."

    top = stocks[:limit]
    lines = [
        f"🐋 <b>TOP WHALE ACCUMULATION PICKS [{esc(title_tag)}]</b>",
        f"⚡ <i>Menemukan {len(stocks)} saham dengan jejak akumulasi Smart Money</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    for i, s in enumerate(top, 1):
        sym = "+" if s["pct_change"] >= 0 else ""
        lines.append(
            f"<b>{i}. #{esc(str(s['ticker']))}</b> — <code>Rp{s['close']:,}</code> ({sym}{s['pct_change']:.2f}%)\n"
            f"   Whale Score: <b>{s['whale_score']}/100</b> ({esc(str(s['whale_status']))})\n"
            f"   RVOL: <code>{s['rvol']}x</code> | CMF: <code>{s['cmf']}</code>\n"
            f"   Rencana: Beli <code>{s['entry_area']}</code> | SL: <code>{s['stop_loss']:,}</code>"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/scan KODE</code> (misal: <code>/scan BBCA</code>) untuk detail lengkap.</i>")
    return "\n".join(lines)


def handle_telegram_command(command_text: str, chat_id: str):
    """Memproses perintah yang diterima bot Telegram."""
    parts = command_text.strip().split()
    if not parts:
        return

    cmd = parts[0].split("@")[0].lower()

    if cmd in ["/start", "/menu", "/help"]:
        help_msg = (
            "🤖 <b>IHSG &amp; WHALE BANDARMOLOGY SIGNAL BOT</b>\n\n"
            "Bot ini memantau IHSG dan mendeteksi saham yang diakumulasi Whale / Smart Money "
            "dari seluruh <b>958 saham BEI</b> via Yahoo Finance API.\n\n"
            "📌 <b>Daftar Perintah Screening:</b>\n"
            "• <code>/ihsg</code> — Sinyal &amp; analisis kondisi pasar IHSG terkini\n"
            "• <code>/whale</code> atau <code>/lq45</code> — Screening 45 saham terlikuid (LQ45)\n"
            "• <code>/kompas100</code> — Screening 100 saham Kompas100\n"
            "• <code>/whale_all</code> — Screening <b>seluruh 958 saham BEI</b>\n"
            "• <code>/scan KODE</code> — Analisis saham (Contoh: <code>/scan BBCA</code>)\n"
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
        send_telegram_message(f"⏳ <i>Menganalisis #{esc(ticker)} dan jejak Whale...</i>", chat_id)
        data = analyze_single_stock(ticker)
        send_long_telegram_message(format_single_stock_message(data), chat_id)

    elif cmd in ["/daily"]:
        send_telegram_message("⏳ <i>Menyiapkan laporan harian pasar...</i>", chat_id)
        ihsg = analyze_ihsg()
        send_long_telegram_message(format_ihsg_message(ihsg), chat_id)
        stocks = scan_whale_watchlist(LQ45_WATCHLIST)
        send_long_telegram_message(format_whale_scan_message(stocks, title_tag="LQ45", limit=5), chat_id)

    else:
        # Jika user hanya ketik kode saham langsung (misal: /BBCA atau BBCA)
        raw = cmd.replace("/", "").upper()
        if len(raw) in [4, 5] and raw.isalpha():
            send_telegram_message(f"⏳ <i>Menganalisis #{esc(raw)}...</i>", chat_id)
            data = analyze_single_stock(raw)
            send_long_telegram_message(format_single_stock_message(data), chat_id)


def start_bot_polling():
    """Menjalankan loop polling getUpdates Telegram Bot."""
    token = TELEGRAM_BOT_TOKEN
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("[WARNING] TELEGRAM_BOT_TOKEN belum diisi!")
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
                    user = msg.get("from", {}).get("username", "User")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Pesan dari @{user} ({chat_id}): {text}")

                    _command_executor.submit(handle_telegram_command, text, chat_id)
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
            now = datetime.now(WIB) if WIB else datetime.now()
            now_str = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")

            # Morning Brief (08:30 WIB)
            if now_str == SCHEDULED_ALERTS.get("morning_brief", "08:30") and already_sent["morning"] != today_str:
                if TELEGRAM_CHAT_ID:
                    print("📢 Mengirim Morning Briefing ke Telegram...")
                    ihsg = analyze_ihsg()
                    send_long_telegram_message("🌅 <b>MORNING MARKET BRIEFING IHSG</b>\n" + format_ihsg_message(ihsg))
                    already_sent["morning"] = today_str

            # Closing Report (16:15 WIB)
            if now_str == SCHEDULED_ALERTS.get("market_closing", "16:15") and already_sent["closing"] != today_str:
                if TELEGRAM_CHAT_ID:
                    print("📢 Mengirim Closing Report ke Telegram...")
                    ihsg = analyze_ihsg()
                    stocks = scan_whale_watchlist(LQ45_WATCHLIST)
                    msg = (
                        "🌇 <b>POST-MARKET CLOSING REPORT & WHALE PICKS</b>\n\n"
                        + format_ihsg_message(ihsg) + "\n\n"
                        + format_whale_scan_message(stocks, title_tag="LQ45 CLOSING", limit=5)
                    )
                    send_long_telegram_message(msg)
                    already_sent["closing"] = today_str

            time.sleep(30)
        except Exception as e:
            print(f"[Scheduler Error] {e}")
            time.sleep(30)
