"""
IHSG Daily Direction Predictor & Multi-Factor Scoring Engine:
Memprediksi arah pergerakan harian IHSG (Naik, Turun, Sideways) setiap pagi sebelum pasar buka,
berdasarkan kombinasi Wall Street overnight sentiment, kurs USD/IDR, teknikal indeks, dan momentum RSI.
"""

from typing import Dict, Any
import yfinance as yf
import pandas as pd
import numpy as np


def predict_daily_ihsg_direction() -> Dict[str, Any]:
    """
    Memprediksi arah IHSG untuk sesi hari ini / esok bursa:
    Kombinasi data real-time:
    - S&P 500 (^GSPC) return semalam
    - Nasdaq (^IXIC) return semalam
    - Kurs USD/IDR (USDIDR=X)
    - Indikator Teknikal IHSG (^JKSE): EMA20, EMA50, RSI 14
    """
    try:
        tickers = ["^JKSE", "^GSPC", "^IXIC", "USDIDR=X"]
        raw = yf.download(tickers, period="2mo", interval="1d", progress=False)
        if raw.empty:
            return {"error": "Gagal mengambil data pasar global dan IHSG."}

        closes = raw["Close"]
        ihsg_c = closes["^JKSE"].dropna()
        sp_c = closes["^GSPC"].dropna()
        nasdaq_c = closes["^IXIC"].dropna()
        idr_c = closes["USDIDR=X"].dropna()

        if len(ihsg_c) < 25:
            return {"error": "Data historis IHSG tidak mencukupi."}

        curr_ihsg = float(ihsg_c.iloc[-1])
        prev_ihsg = float(ihsg_c.iloc[-2])
        ihsg_last_chg = ((curr_ihsg - prev_ihsg) / prev_ihsg) * 100

        # 1. Wall Street Sentiment
        sp_ret = float((sp_c.iloc[-1] - sp_c.iloc[-2]) / sp_c.iloc[-2]) * 100 if len(sp_c) >= 2 else 0.0
        nasdaq_ret = float((nasdaq_c.iloc[-1] - nasdaq_c.iloc[-2]) / nasdaq_c.iloc[-2]) * 100 if len(nasdaq_c) >= 2 else 0.0

        # 2. Kurs USD/IDR
        curr_idr = float(idr_c.iloc[-1])
        prev_idr = float(idr_c.iloc[-2]) if len(idr_c) >= 2 else curr_idr
        idr_chg = ((curr_idr - prev_idr) / prev_idr) * 100

        # 3. Teknikal IHSG (EMA20, EMA50, RSI14)
        ema20 = float(ihsg_c.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(ihsg_c.ewm(span=50, adjust=False).mean().iloc[-1])

        delta = ihsg_c.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi14 = float(100 - (100 / (1 + rs.iloc[-1])))

        # Perhitungan Skor Komposit Prediksi (-100 s/d +100)
        score = 0
        factors = []

        # Bobot 1: S&P 500 semalam (Bobot 35%)
        if sp_ret >= 0.8:
            score += 35
            factors.append(f"🟢 Wall Street reli solid (S&P 500 {sp_ret:+.2f}%)")
        elif sp_ret >= 0.2:
            score += 20
            factors.append(f"🟢 Wall Street hijau moderat ({sp_ret:+.2f}%)")
        elif sp_ret <= -1.0:
            score -= 40
            factors.append(f"🔴 Wall Street koreksi dalam/crash ({sp_ret:+.2f}%)")
        elif sp_ret <= -0.4:
            score -= 25
            factors.append(f"🔴 Wall Street merah ({sp_ret:+.2f}%)")
        else:
            factors.append(f"⚪ Wall Street bervariasi/flat ({sp_ret:+.2f}%)")

        # Bobot 2: Kurs Rupiah (Bobot 25%)
        if idr_chg <= -0.2:
            score += 25
            factors.append(f"🟢 Rupiah menguat ke Rp{int(curr_idr):,} ({idr_chg:+.2f}%)")
        elif idr_chg >= 0.4:
            score -= 25
            factors.append(f"🔴 Rupiah melemah tertekan ke Rp{int(curr_idr):,} ({idr_chg:+.2f}%)")
        else:
            factors.append(f"⚪ Kurs Rupiah stabil di Rp{int(curr_idr):,}")

        # Bobot 3: RSI 14 Mean Reversion (Bobot 20%)
        if rsi14 <= 32:
            score += 20
            factors.append(f"💎 IHSG jenuh jual / Oversold (RSI {rsi14:.1f}) -> Potensi Rebound!")
        elif rsi14 >= 72:
            score -= 20
            factors.append(f"⚠️ IHSG jenuh beli / Overbought (RSI {rsi14:.1f}) -> Rawan Profit Taking")
        else:
            factors.append(f"⚪ RSI 14 seimbang di {rsi14:.1f}")

        # Bobot 4: Tren EMA20 (Bobot 20%)
        if curr_ihsg > ema20:
            score += 20
            factors.append("🟢 Tren IHSG di atas EMA20 (Uptrend Structure)")
        else:
            score -= 20
            factors.append("🔴 Tren IHSG di bawah EMA20 (Downtrend Structure)")

        # Estimasi Support & Resistance Harian
        atr5 = float((ihsg_c.diff().abs().rolling(5).mean().iloc[-1]))
        est_support = curr_ihsg - atr5
        est_resistance = curr_ihsg + atr5

        # Penentuan Arah Prediksi & Probabilitas
        if score >= 20:
            direction = "🟢 BULLISH (CENDERUNG NAIK)"
            confidence = min(85, int(55 + (score * 0.3)))
            guidance = "Peluang pasar positif. Momentum kondusif untuk entry pada saham Tier S & A yang diakumulasi Whale."
        elif score <= -20:
            direction = "🔴 BEARISH (CENDERUNG TURUN)"
            confidence = min(85, int(55 + (abs(score) * 0.3)))
            guidance = "Waspada potensi tekanan jual / gap down. Jangan menangkap pisau jatuh. Prioritaskan amankan modal dan hold cash."
        else:
            direction = "⚪ SIDEWAYS (KONSOLIDASI / MIXED)"
            confidence = 50
            guidance = "Sentimen pasar berimbang / minim katalis. Fokus hanya pada saham second-liner dengan rumor aksi korporasi mandiri."

        return {
            "ihsg_current": curr_ihsg,
            "ihsg_last_chg": ihsg_last_chg,
            "sp500_ret": sp_ret,
            "nasdaq_ret": nasdaq_ret,
            "usd_idr": curr_idr,
            "idr_chg": idr_chg,
            "rsi14": rsi14,
            "ema20": ema20,
            "ema50": ema50,
            "score": score,
            "direction": direction,
            "confidence": confidence,
            "guidance": guidance,
            "factors": factors,
            "support": est_support,
            "resistance": est_resistance
        }

    except Exception as e:
        return {"error": str(e)}
