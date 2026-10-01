import threading
import sys
import time
from telegram_bot import start_bot_polling, scheduled_worker
from config import TELEGRAM_BOT_TOKEN

def main():
    print("="*60)
    print("🚀 IHSG & WHALE ACCUMULATION SIGNAL BOT")
    print("   Powered by Yahoo Finance API & Bandarmology Quant")
    print("="*60)

    # Jalankan background scheduler untuk pesan otomatis (08:30 WIB & 16:15 WIB)
    scheduler_thread = threading.Thread(target=scheduled_worker, daemon=True)
    scheduler_thread.start()

    # Mulai polling Telegram Bot
    try:
        start_bot_polling()
    except KeyboardInterrupt:
        print("\n[INFO] Bot dihentikan oleh pengguna.")
        sys.exit(0)

if __name__ == "__main__":
    main()
