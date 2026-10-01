import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    IHSG_TICKER,
    DEFAULT_WATCHLIST,
    LQ45_WATCHLIST,
    KOMPAS100_WATCHLIST,
    ALL_IDX_TICKERS,
    INDICATOR_CONFIG
)
from indicators import add_all_indicators
from broker_summary import WhaleAccumulationAnalyzer


def clean_ticker(symbol: str) -> str:
    """Format ticker menjadi standar Yahoo Finance IDX."""
    symbol = symbol.strip().upper()
    if symbol.startswith("^"):
        return symbol
    if not symbol.endswith(".JK"):
        return f"{symbol}.JK"
    return symbol


def fetch_stock_data(ticker: str, period: str = "6mo", interval: str = "1d") -> Optional[pd.DataFrame]:
    """Mengambil data OHLCV dari Yahoo Finance dan menghitung indikator."""
    formatted_ticker = clean_ticker(ticker)
    try:
        t = yf.Ticker(formatted_ticker)
        df = t.history(period=period, interval=interval)
        if df.empty or len(df) < 20:
            return None
        
        # Tambahkan seluruh indikator teknikal & bandarmology
        df = add_all_indicators(df, INDICATOR_CONFIG)
        return df
    except Exception as e:
        return None


def calculate_support_resistance(df: pd.DataFrame) -> Dict[str, float]:
    """Menghitung level support & resistance utama berdasarkan swing low/high dan Moving Average."""
    recent = df.tail(30)
    current_close = float(df["Close"].iloc[-1])

    swing_low = float(recent["Low"].min())
    swing_high = float(recent["High"].max())

    ema20 = float(df["EMA_20"].iloc[-1])
    ema50 = float(df["EMA_50"].iloc[-1])
    ema200 = float(df["EMA_200"].iloc[-1])
    bb_lower = float(df["BB_Lower"].iloc[-1])
    bb_upper = float(df["BB_Upper"].iloc[-1])

    # Kumpulkan kandidat support (level di bawah harga sekarang)
    supports = [lvl for lvl in [swing_low, ema20, ema50, ema200, bb_lower] if lvl < current_close]
    support_1 = max(supports) if supports else swing_low
    supports_2 = [lvl for lvl in supports if lvl < support_1 * 0.99]
    support_2 = max(supports_2) if supports_2 else support_1 * 0.97

    # Kumpulkan kandidat resistance (level di atas harga sekarang)
    resistances = [lvl for lvl in [swing_high, ema20, ema50, ema200, bb_upper] if lvl > current_close]
    resistance_1 = min(resistances) if resistances else swing_high
    resistances_2 = [lvl for lvl in resistances if lvl > resistance_1 * 1.01]
    resistance_2 = min(resistances_2) if resistances_2 else resistance_1 * 1.03

    return {
        "support_1": round(support_1, 2),
        "support_2": round(support_2, 2),
        "resistance_1": round(resistance_1, 2),
        "resistance_2": round(resistance_2, 2)
    }


def analyze_ihsg() -> Dict[str, Any]:
    """Menganalisis kondisi indeks IHSG (^JKSE) secara komprehensif."""
    df = fetch_stock_data(IHSG_TICKER, period="6mo")
    if df is None:
        return {"error": "Gagal mengambil data IHSG dari Yahoo Finance."}

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    close = float(latest["Close"])
    prev_close = float(prev["Close"])
    change_pts = close - prev_close
    pct_change = (change_pts / prev_close) * 100

    ema20 = float(latest["EMA_20"])
    ema50 = float(latest["EMA_50"])
    ema200 = float(latest["EMA_200"])
    rsi = float(latest["RSI"])
    macd = float(latest["MACD"])
    macd_signal = float(latest["MACD_Signal"])
    macd_hist = float(latest["MACD_Hist"])
    rvol = float(latest["RVOL"])
    cmf = float(latest["CMF"])
    whale_score = int(latest["Whale_Score"])

    levels = calculate_support_resistance(df)

    # Menentukan Tren
    if close > ema20 and ema20 > ema50 and ema50 > ema200:
        trend = "STRONG BULLISH"
        trend_emoji = "🟢🚀"
    elif close > ema20 and close > ema50:
        trend = "BULLISH"
        trend_emoji = "🟢"
    elif close < ema20 and close < ema50 and close < ema200:
        trend = "STRONG BEARISH"
        trend_emoji = "🔴⚠️"
    elif close < ema20 and close < ema50:
        trend = "BEARISH"
        trend_emoji = "🔴"
    else:
        trend = "SIDEWAYS / KONSOLIDASI"
        trend_emoji = "🟡"

    # Momentum RSI
    if rsi >= 70:
        rsi_desc = "OVERBOUGHT (Rentan profit taking)"
    elif rsi >= 55:
        rsi_desc = "BULLISH MOMENTUM (Tren naik sehat)"
    elif rsi >= 45:
        rsi_desc = "NETRAL (Konsolidasi)"
    elif rsi <= 30:
        rsi_desc = "OVERSOLD (Peluang Rebound)"
    else:
        rsi_desc = "BEARISH MOMENTUM (Tekanan jual mendominasi)"

    # MACD Status
    if macd > macd_signal and macd_hist > 0:
        macd_desc = "GOLDEN CROSS / BULLISH"
    elif macd < macd_signal and macd_hist < 0:
        macd_desc = "DEATH CROSS / BEARISH"
    else:
        macd_desc = "CONSOLIDATION"

    # Rekomendasi Aksi Pasar
    if trend in ["STRONG BULLISH", "BULLISH"] and rsi < 70 and cmf > 0:
        action = "AGRESIF BUY / SWING"
        action_note = "Pasar berada dalam tren bullish dengan aliran dana positif. Fokus pada saham-saham breakout & akumulasi whale."
    elif rsi <= 32:
        action = "BUY ON WEAKNESS (BOW)"
        action_note = "IHSG mendekati area oversold ekstrim. Potensi technical rebound segera terjadi."
    elif trend in ["BEARISH", "STRONG BEARISH"]:
        action = "DEFENSIF / CASH IS KING"
        action_note = "IHSG di bawah rata-rata EMA utama. Perketat Stop Loss dan kurangi porsi posisi swing."
    else:
        action = "SELEKTIF SWING & WAIT AND SEE"
        action_note = "IHSG bergerak sideways. Pilih saham yang memiliki sinyal akumulasi tersendiri (divergensi terhadap IHSG)."

    return {
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "close": close,
        "change_pts": change_pts,
        "pct_change": pct_change,
        "trend": trend,
        "trend_emoji": trend_emoji,
        "rsi": rsi,
        "rsi_desc": rsi_desc,
        "macd_desc": macd_desc,
        "cmf": cmf,
        "rvol": rvol,
        "whale_score": whale_score,
        "levels": levels,
        "action": action,
        "action_note": action_note
    }


def analyze_single_stock(symbol: str) -> Dict[str, Any]:
    """Menganalisis saham tertentu secara mendalam (Teknikal + Akumulasi Whale + Entry/Exit Plan)."""
    df = fetch_stock_data(symbol, period="6mo")
    if df is None:
        return {"error": f"Data saham {symbol} tidak ditemukan di Yahoo Finance."}

    clean_sym = symbol.replace(".JK", "").upper()
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    close = float(latest["Close"])
    prev_close = float(prev["Close"])
    pct_change = ((close - prev_close) / prev_close) * 100 if prev_close > 0 else 0.0

    # Analisis Whale
    whale_info = WhaleAccumulationAnalyzer.analyze_stock_whale_flow(clean_sym, df)

    # Indikator Teknikal
    ema20 = float(latest["EMA_20"])
    ema50 = float(latest["EMA_50"])
    ema200 = float(latest["EMA_200"])
    rsi = float(latest["RSI"])
    macd_hist = float(latest["MACD_Hist"])
    macd = float(latest["MACD"])
    macd_signal = float(latest["MACD_Signal"])

    levels = calculate_support_resistance(df)

    # Setup Trading Plan (Swing)
    support = levels["support_1"]
    resistance = levels["resistance_1"]
    resistance_2 = levels["resistance_2"]

    entry_area = f"{int(support * 1.005):,} - {int(close):,}".replace(",", ".")
    stop_loss = int(support * 0.97)
    tp1 = int(resistance)
    tp2 = int(resistance_2)

    risk = close - stop_loss
    reward = tp1 - close
    rr_ratio = round(reward / risk, 2) if risk > 0 else 0.0

    # Sinyal Kesimpulan
    whale_score = whale_info["whale_score"]
    if whale_score >= 70 and close >= ema20 and rsi < 68:
        signal = "STRONG BUY (WHALE ACCUMULATION)"
        signal_badge = "🟢🟢 BUY"
    elif whale_score >= 55 and (close >= ema20 or rsi <= 35):
        signal = "BUY / ACCUMULATE"
        signal_badge = "🟢 BUY"
    elif whale_score < 40 and close < ema20:
        signal = "SELL / AVOID (DISTRIBUTION)"
        signal_badge = "🔴 SELL"
    else:
        signal = "NEUTRAL / WAIT & SEE"
        signal_badge = "🟡 HOLD"

    return {
        "ticker": clean_sym,
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "close": close,
        "pct_change": pct_change,
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
        "rsi": rsi,
        "macd": macd,
        "macd_signal": macd_signal,
        "signal": signal,
        "signal_badge": signal_badge,
        "whale": whale_info,
        "levels": levels,
        "trading_plan": {
            "entry_area": entry_area,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "rr_ratio": rr_ratio
        }
    }


def scan_whale_watchlist(
    watchlist: Optional[List[str]] = None,
    min_turnover_billion: float = 0.0,
    max_workers: int = 15
) -> List[Dict[str, Any]]:
    """
    Memindai saham menggunakan multi-threading paralel:
    Bisa memindai LQ45 (45 saham), Kompas100 (100 saham), atau Seluruh Saham IDX (958 saham).
    Dilengkapi filter turnover minimum agar saham tidur (tanpa transaksi) tidak mengotori hasil.
    """
    if watchlist is None:
        watchlist = DEFAULT_WATCHLIST

    results = []
    total = len(watchlist)
    print(f"🚀 Memindai {total} saham secara paralel ({max_workers} threads)...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_stock = {executor.submit(analyze_single_stock, sym): sym for sym in watchlist}
        for future in as_completed(future_to_stock):
            sym = future_to_stock[future]
            try:
                data = future.result()
                if "error" not in data:
                    turnover = data["whale"].get("turnover_billion", 0.0)
                    # Filter likuiditas jika diset
                    if turnover >= min_turnover_billion:
                        results.append(data)
            except Exception as e:
                pass

    # Urutkan berdasarkan Skor Whale tertinggi dan lonjakan volume (RVOL)
    results.sort(
        key=lambda x: (x["whale"]["whale_score"], x["whale"]["rvol"]),
        reverse=True
    )
    return results
