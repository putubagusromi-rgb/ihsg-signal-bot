import threading
import sys
import io
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram_bot import start_bot_polling, scheduled_worker
from config import TELEGRAM_BOT_TOKEN

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"IHSG Signal Bot is Alive and Running!")

    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌐 Health Check server aktif di port {port}...")
    server.serve_forever()

def main():
    print("="*60)
    print("🚀 IHSG & WHALE ACCUMULATION SIGNAL BOT")
    print("   Powered by Yahoo Finance API & Bandarmology Quant")
    print("="*60)

    # Jalankan dummy web server agar Render mendeteksi open port (Port Binding)
    web_thread = threading.Thread(target=run_health_server, daemon=True)
    web_thread.start()

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
