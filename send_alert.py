import sys
import argparse
from datetime import datetime

from telegram_bot import send_telegram_message, format_ihsg_message, format_whale_scan_message
from signal_engine import analyze_ihsg, scan_whale_watchlist
from config import LQ45_WATCHLIST, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def run_morning_alert():
    """Mengirim Morning Briefing IHSG sebelum pembukaan bursa."""
    print(f"[{datetime.now()}] Mengirim Morning Alert ke Telegram...")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[ERROR] Token atau Chat ID Telegram belum diatur di .env")
        return

    ihsg = analyze_ihsg()
    header = "🌅 <b>MORNING MARKET BRIEFING IHSG</b> 🇮🇩\n\n"
    msg = header + format_ihsg_message(ihsg)
    success = send_telegram_message(msg)
    if success:
        print("[SUCCESS] Morning briefing berhasil terkirim ke Telegram!")
    else:
        print("[FAILED] Gagal mengirim pesan ke Telegram.")


def run_closing_alert():
    """Mengirim Post-Market Closing Report & Top Whale Picks setelah penutupan bursa."""
    print(f"[{datetime.now()}] Mengirim Closing Alert ke Telegram...")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[ERROR] Token atau Chat ID Telegram belum diatur di .env")
        return

    ihsg = analyze_ihsg()
    header = "🌇 <b>POST-MARKET CLOSING REPORT & WHALE PICKS</b> 🇮🇩\n\n"
    msg = header + format_ihsg_message(ihsg)
    send_telegram_message(msg)

    # Scan Top Whale Accumulation LQ45
    stocks = scan_whale_watchlist(LQ45_WATCHLIST)
    whale_msg = format_whale_scan_message(stocks, title_tag="LQ45 TOP PICKS", limit=5)
    success = send_telegram_message(whale_msg)
    if success:
        print("[SUCCESS] Closing report & Whale picks berhasil terkirim ke Telegram!")
    else:
        print("[FAILED] Gagal mengirim pesan ke Telegram.")


def run_test_alert():
    """Mengirim pesan uji coba untuk memastikan konfigurasi bot sudah benar."""
    print(f"[{datetime.now()}] Mengirim Pesan Tes ke Telegram...")
    test_msg = (
        "✅ <b>KONEKSI BOT BERHASIL!</b> 🚀\n\n"
        "Halo! IHSG Signal & Whale Bandarmology Bot kamu sudah terhubung dengan sukses.\n"
        "Notifikasi harian bursa akan dikirimkan otomatis ke chat ini."
    )
    success = send_telegram_message(test_msg)
    if success:
        print("[SUCCESS] Pesan uji coba berhasil sampai di Telegram!")
    else:
        print("[FAILED] Gagal terkirim. Cek kembali TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID di .env.")


def main():
    parser = argparse.ArgumentParser(description="Kirim Notifikasi Terjadwal ke Telegram")
    parser.add_argument("--morning", action="store_true", help="Kirim Morning Briefing (08:30 WIB)")
    parser.add_argument("--closing", action="store_true", help="Kirim Closing Report & Whale (16:15 WIB)")
    parser.add_argument("--test", action="store_true", help="Uji coba pengiriman pesan")

    args = parser.parse_args()

    if args.morning:
        run_morning_alert()
    elif args.closing:
        run_closing_alert()
    elif args.test:
        run_test_alert()
    else:
        print("Gunakan flag: --morning, --closing, atau --test")


if __name__ == "__main__":
    main()
