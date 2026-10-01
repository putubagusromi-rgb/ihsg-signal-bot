import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load file .env dari folder project
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Telegram Bot Credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Simbol Indeks & Market
IHSG_TICKER = "^JKSE"

# Load seluruh saham IDX (958 saham) dari tickers_universe.json
UNIVERSE_FILE = BASE_DIR / "tickers_universe.json"
if UNIVERSE_FILE.exists():
    try:
        with open(UNIVERSE_FILE, "r") as f:
            ALL_IDX_TICKERS = json.load(f)
    except Exception:
        ALL_IDX_TICKERS = []
else:
    ALL_IDX_TICKERS = []

# Watchlist LQ45 (Saham terlikuid & Big Caps)
LQ45_WATCHLIST = [
    "ACES", "ADRO", "AKRA", "AMMN", "ANTM", "ARTO", "ASII", "BBCA", "BBNI", "BBRI",
    "BBTN", "BFIN", "BMRI", "BRIS", "BRPT", "BUKA", "CPIN", "EMTK", "ESSA", "EXCL",
    "GGRM", "GOTO", "HRUM", "ICBP", "INCO", "INDF", "INKP", "INTP", "ITMG", "JSMR",
    "KLBF", "MAPI", "MBMA", "MDKA", "MEDC", "MIKA", "PGAS", "PGEO", "PTBA", "SCMA",
    "SMGR", "SRTG", "TLKM", "TOWR", "UNTR", "UNVR"
]

# Kompas 100 / Active Movers Selection
KOMPAS100_WATCHLIST = list(set(LQ45_WATCHLIST + [
    "ACES", "ADMR", "AGRO", "AUTO", "AVIA", "BIRD", "BKSL", "BSDE", "BTPS", "CLEO",
    "CMRY", "CPIN", "CTRA", "DOID", "ELSA", "ERAA", "HEAL", "IMAS", "INDY", "ISAT",
    "MAPA", "MAPR", "MARK", "MORA", "MYOR", "NISP", "PANI", "PSSI", "PWON", "RAJA",
    "RALS", "ROT", "SIDO", "SIMP", "SMRA", "SSMS", "TAPG", "TKIM", "TPIA", "BREN",
    "CUAN", "WIFI", "WOOD", "MAPA"
]))

# Default watchlist untuk scanning cepat
DEFAULT_WATCHLIST = LQ45_WATCHLIST

# Parameter Indikator Teknikal
INDICATOR_CONFIG = {
    "ema_short": 20,
    "ema_medium": 50,
    "ema_long": 200,
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "cmf_period": 20,           # Chaikin Money Flow period (Whale flow)
    "rvol_period": 20,          # Relative Volume average period
    "whale_rvol_threshold": 1.5, # Volume > 1.5x rata-rata 20 hari dianggap lonjakan Whale
    "min_turnover_billion": 0.5 # Filter likuiditas minimum (Rp 500 Juta / hari) saat scan all stocks
}

# Jam jadwal notifikasi otomatis (Format: HH:MM WIB)
SCHEDULED_ALERTS = {
    "morning_brief": "08:30",  # Sebelum bursa buka sesi 1
    "market_closing": "16:15"  # Setelah bursa tutup sore
}
