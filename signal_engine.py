import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from config import (
    IHSG_TICKER,
    DEFAULT_WATCHLIST,
    INDICATOR_CONFIG
)
from indicators import add_all_indicators
from broker_summary import WhaleAccumulationAnalyzer


def clean_ticker(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if symbol.startswith("^"):
        return symbol
    if not symbol.endswith(".JK"):
        return f"{symbol}.JK"
    return symbol


def fetch_stock_data(ticker: str, period: str = "6mo", interval: str = "1d") -> Optional[pd.DataFrame]:
    formatted_ticker = clean_ticker(ticker)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            t = yf.Ticker(formatted_ticker)
            df = t.history(period=period, interval=interval)
            if df.empty or len(df) < 20:
                return None
            df = add_all_indicators(df, INDICATOR_CONFIG)
            return df
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"[WARNING] Gagal fetch data {ticker}: {e}")
                return None
    return None


def calculate_support_resistance(df: pd.DataFrame) -> Dict[str, float]:
    recent = df.tail(30)
    current_close = float(df["Close"].iloc[-1])
    swing_low = float(recent["Low"].min())
    swing_high = float(recent["High"].max())

    ema20 = float(df["EMA_20"].iloc[-1])
    ema50 = float(df["EMA_50"].iloc[-1])
    bb_lower = float(df["BB_Lower"].iloc[-1])
    bb_upper = float(df["BB_Upper"].iloc[-1])

    supports = [lvl for lvl in [swing_low, bb_lower, ema20, ema50] if lvl < current_close]
    support_1 = max(supports) if supports else swing_low

    resistances = [lvl for lvl in [swing_high, bb_upper, ema20, ema50] if lvl > current_close]
    resistance_1 = min(resistances) if resistances else swing_high

    return {
        "support_1": round(support_1, 2),
        "resistance_1": round(resistance_1, 2),
        "resistance_2": round(resistance_1 * 1.05, 2)
    }


def analyze_ihsg() -> Dict[str, Any]:
    df = fetch_stock_data(IHSG_TICKER, period="6mo", interval="1d")
    if df is None:
        return {"error": "Gagal mengambil data IHSG"}

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(latest["Close"])
    prev_close = float(prev["Close"])
    pct_change = ((close - prev_close) / prev_close) * 100
    change_pts = close - prev_close

    ema20 = float(latest["EMA_20"])
    ema50 = float(latest["EMA_50"])
    ema200 = float(latest["EMA_200"])
    rsi = float(latest["RSI"])
    macd = float(latest["MACD"])
    macd_signal = float(latest["MACD_Signal"])

    if close > ema20 > ema50 > ema200:
        trend = "SUPER BULLISH"
        trend_emoji = "🚀"
    elif close > ema20 and ema20 > ema50:
        trend = "BULLISH"
        trend_emoji = "🟢"
    elif close < ema20 and ema20 < ema50:
        trend = "BEARISH"
        trend_emoji = "🔴"
    else:
        trend = "SIDEWAYS / CONSOLIDATION"
        trend_emoji = "🟡"

    momentum = "BULLISH" if macd > macd_signal else "BEARISH"
    levels = calculate_support_resistance(df)

    if trend in ["SUPER BULLISH", "BULLISH"] and rsi < 65:
        recommendation = "AKUMULASI / BUY ON WEAKNESS pada saham-saham pilihan yang sedang diakumulasi Whale."
    elif rsi > 70:
        recommendation = "WASPADA PROFIT TAKING. Kurangi posisi agresif, pasang Trailing Stop ketat."
    elif trend == "BEARISH":
        recommendation = "DEFENSIVE MODE. Perbanyak porsi CASH, tunggu konfirmasi rebound."
    else:
        recommendation = "SELEKTIF SWING TRADE. Fokus pada saham-saham berfundamental solid dengan lonjakan volume."

    return {
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "close": close,
        "pct_change": pct_change,
        "change_pts": change_pts,
        "trend": trend,
        "trend_emoji": trend_emoji,
        "momentum": momentum,
        "rsi": round(rsi, 1),
        "rsi_status": "OVERSOLD" if rsi < 30 else ("OVERBOUGHT" if rsi > 70 else "NEUTRAL"),
        "macd": round(macd, 2),
        "macd_signal": round(macd_signal, 2),
        "ma20": ema20,
        "ma50": ema50,
        "support": levels["support_1"],
        "resistance": levels["resistance_1"],
        "recommendation": recommendation
    }


def analyze_single_stock(ticker: str) -> Dict[str, Any]:
    clean_sym = ticker.replace(".JK", "").strip().upper()
    df = fetch_stock_data(clean_sym, period="6mo", interval="1d")
    if df is None:
        return {"error": f"Data saham #{clean_sym} tidak ditemukan atau kurang likuid"}

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(latest["Close"])
    prev_close = float(prev["Close"])
    pct_change = ((close - prev_close) / prev_close) * 100

    whale_info = WhaleAccumulationAnalyzer.analyze_stock_whale_flow(clean_sym, df)
    levels = calculate_support_resistance(df)

    support = levels["support_1"]
    resistance = levels["resistance_1"]
    resistance_2 = levels["resistance_2"]

    entry_low = min(int(support * 1.005), int(close))
    entry_high = max(int(support * 1.005), int(close))
    entry_area = f"{entry_low:,} - {entry_high:,}".replace(",", ".")

    stop_loss = int(support * 0.97)
    tp1 = int(resistance)
    tp2 = int(resistance_2)

    risk = close - stop_loss
    reward = tp1 - close
    rr_ratio = round(reward / risk, 2) if risk > 0 else 0.0

    from news_sentiment import analyze_news_sentiment
    sentiment_data = analyze_news_sentiment(clean_sym)

    whale_score = whale_info["whale_score"]
    sent_score = sentiment_data["sentiment_score"]

    if whale_score >= 65 and sent_score >= 60 and close >= latest["EMA_20"]:
        signal = "STRONG BUY (BANDAR MASUK + KATALIS POSITIF)"
        signal_badge = "🚀 STRONG BUY"
    elif whale_score >= 65 and sent_score < 40:
        signal = "ACCUMULATE WITH CAUTION (BANDAR MASUK TAPI BERITA HATI-HATI)"
        signal_badge = "🟡 ACCUMULATE"
    elif whale_score >= 55 and (close >= latest["EMA_20"] or latest["RSI"] <= 35):
        signal = "BUY / ACCUMULATE (BANDAR INFLOW)"
        signal_badge = "🟢 BUY"
    elif whale_score < 40 and close < latest["EMA_20"]:
        signal = "SELL / AVOID (DISTRIBUSI BANDAR)"
        signal_badge = "🔴 SELL"
    else:
        signal = "NEUTRAL / WAIT & SEE"
        signal_badge = "⚪ WAIT & SEE"

    return {
        "ticker": clean_sym,
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "close": close,
        "pct_change": pct_change,
        "ema20": float(latest["EMA_20"]),
        "ema50": float(latest["EMA_50"]),
        "rsi": float(latest["RSI"]),
        "signal": signal,
        "signal_badge": signal_badge,
        "whale": whale_info,
        "sentiment": sentiment_data,
        "levels": levels,
        "trading_plan": {
            "entry_area": entry_area,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "rr_ratio": rr_ratio
        }
    }


def scan_whale_watchlist(watchlist: Optional[List[str]] = None, min_turnover_billion: float = 0.5, max_workers: int = 8) -> List[Dict[str, Any]]:
    tickers = watchlist or DEFAULT_WATCHLIST
    results = []

    def _process_ticker(sym: str):
        df = fetch_stock_data(sym, period="3mo", interval="1d")
        if df is None:
            return None
        info = WhaleAccumulationAnalyzer.analyze_stock_whale_flow(sym, df)
        if info.get("turnover_billion", 0) < min_turnover_billion:
            return None
        if info.get("whale_score", 0) >= 55:
            levels = calculate_support_resistance(df)
            close = info["close"]
            support = levels["support_1"]
            entry_low = min(int(support * 1.005), int(close))
            entry_high = max(int(support * 1.005), int(close))
            return {
                "ticker": info["ticker"],
                "close": close,
                "pct_change": info["pct_change"],
                "whale": info,
                "trading_plan": {
                    "entry_area": f"{entry_low:,} - {entry_high:,}".replace(",", "."),
                    "tp1": int(levels["resistance_1"]),
                    "stop_loss": int(support * 0.97)
                }
            }
        return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_process_ticker, sym): sym for sym in tickers}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)

    results.sort(key=lambda x: x["whale"]["whale_score"], reverse=True)
    return results
