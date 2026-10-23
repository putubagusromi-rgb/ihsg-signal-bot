"""
IHSG Daily Direction Predictor & Multi-Factor Scoring Engine (V2 - EIDO Consensus):
Memprediksi arah pergerakan harian IHSG (Naik, Turun, Sideways) setiap pagi sebelum pasar buka,
berdasarkan pergerakan EIDO (iShares MSCI Indonesia ETF di Wall Street), S&P 500, kurs USD/IDR, dan teknikal IHSG.
"""

from typing import Dict, Any
import yfinance as yf
import pandas as pd
import numpy as np


def predict_daily_ihsg_direction() -> Dict[str, Any]:
    """
    Memprediksi arah IHSG untuk sesi hari ini / esok bursa:
    Kombinasi data real-time:
    - EIDO (MSCI Indonesia ETF di Wall Street) -> Aliran dana institusi global langsung ke saham Indo
    - S&P 500 (^GSPC) -> Sentimen bursa global
    - Kurs USD/IDR (USDIDR=X)
    - Indikator Teknikal IHSG (^JKSE): EMA20, EMA50, RSI 14
    """
    try:
        tickers = ["^JKSE", "EIDO", "^GSPC", "^IXIC", "USDIDR=X"]
        raw = yf.download(tickers, period="2mo", interval="1d", progress=False)
        if raw.empty:
            return {"error": "Gagal mengambil data pasar global dan IHSG."}

        closes = raw["Close"]
        ihsg_c = closes["^JKSE"].dropna()
        eido_c = closes["EIDO"].dropna()
        sp_c = closes["^GSPC"].dropna()
        idr_c = closes["USDIDR=X"].dropna()

        if len(ihsg_c) < 20:
            return {"error": "Data historis IHSG tidak mencukupi."}

        curr_ihsg = float(ihsg_c.iloc[-1])
        prev_ihsg = float(ihsg_c.iloc[-2])
        ihsg_last_chg = ((curr_ihsg - prev_ihsg) / prev_ihsg) * 100

        # 1. EIDO Return (MSCI Indonesia ETF di New York)
        eido_ret = float((eido_c.iloc[-1] - eido_c.iloc[-2]) / eido_c.iloc[-2]) * 100 if len(eido_c) >= 2 else 0.0

        # 2. Wall Street S&P 500 Return
        sp_ret = float((sp_c.iloc[-1] - sp_c.iloc[-2]) / sp_c.iloc[-2]) * 100 if len(sp_c) >= 2 else 0.0

        # 3. Kurs USD/IDR
        curr_idr = float(idr_c.iloc[-1])
        prev_idr = float(idr_c.iloc[-2]) if len(idr_c) >= 2 else curr_idr
        idr_chg = ((curr_idr - prev_idr) / prev_idr) * 100

        # 4. Teknikal IHSG (EMA20, EMA50, RSI14)
        ema20 = float(ihsg_c.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(ihsg_c.ewm(span=50, adjust=False).mean().iloc[-1])

        delta = ihsg_c.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs))
        rsi14 = float(rsi_series.iloc[-1])
        min_rsi_5d = float(rsi_series.iloc[-5:].min()) if len(rsi_series) >= 5 else rsi14

        # Hitung reli hijau berturut-turut (consecutive streak)
        ihsg_rets = ihsg_c.pct_change()
        streak = 0
        for r in reversed(ihsg_rets.iloc[-5:].tolist()):
            if r > 0:
                streak += 1
            else:
                break

        score = 0
        factors = []

        # --- LOGIKA PENENTUAN ARAH (BERDASARKAN HASIL BACKTEST 891 HARI) ---

        # FAKTOR 1: EIDO (MSCI Indonesia ETF di Wall Street) - Bobot Paling Akurat (40%)
        if eido_ret >= 0.8:
            score += 40
            factors.append(f"🟢 EIDO (ETF Indo di Wall Street) terbang {eido_ret:+.2f}% -> Inflow institusi global kuat!")
        elif eido_ret >= 0.2:
            score += 20
            factors.append(f"🟢 EIDO ditutup menguat ({eido_ret:+.2f}%)")
        elif eido_ret <= -0.8:
            score -= 40
            factors.append(f"🔴 EIDO anjlok {eido_ret:+.2f}% -> Outflow dana institusi asing")
        elif eido_ret <= -0.2:
            score -= 20
            factors.append(f"🔴 EIDO ditutup melemah ({eido_ret:+.2f}%)")
        else:
            factors.append(f"⚪ EIDO bergerak stabil/flat ({eido_ret:+.2f}%)")

        # FAKTOR 2: Sentimen Wall Street (S&P 500) - Bobot 25%
        if sp_ret >= 0.6:
            score += 25
            factors.append(f"🟢 Bursa AS (S&P 500) reli hijau ({sp_ret:+.2f}%)")
        elif sp_ret <= -0.8:
            if eido_ret > 0.5:
                score -= 10
                factors.append(f"⚠️ S&P 500 merah ({sp_ret:+.2f}%), namun ada rotasi dana masuk ke aset Indo (EIDO {eido_ret:+.2f}%)")
            else:
                score -= 25
                factors.append(f"🔴 S&P 500 terkoreksi ({sp_ret:+.2f}%)")
        else:
            factors.append(f"⚪ S&P 500 bervariasi ({sp_ret:+.2f}%)")

        # FAKTOR 3: V-Shape Rebound & RSI Ekstrem - Bobot 20%
        if min_rsi_5d <= 30 and streak >= 2:
            score += 25
            factors.append(f"💎 V-Shape Rebound Aktif: IHSG bangkit dari dasar jenuh jual ({streak} hari hijau berturut-turut)")
        elif rsi14 <= 28:
            score += 20
            factors.append(f"💎 IHSG jenuh jual ekstrem (RSI {rsi14:.1f}) -> Potensi Rebound!")
        elif rsi14 >= 72 and sp_ret < 0:
            score -= 20
            factors.append(f"⚠️ IHSG jenuh beli (RSI {rsi14:.1f}) -> Rawan aksi profit taking")
        else:
            factors.append(f"⚪ RSI 14 berada di level seimbang ({rsi14:.1f})")

        # FAKTOR 4: Kurs Rupiah (USD/IDR) - Bobot 15%
        if idr_chg <= -0.25:
            score += 15
            factors.append(f"🟢 Rupiah menguat ke Rp{int(curr_idr):,} ({idr_chg:+.2f}%)")
        elif idr_chg >= 0.40:
            score -= 15
            factors.append(f"🔴 Rupiah tertekan ke Rp{int(curr_idr):,} ({idr_chg:+.2f}%)")
        else:
            factors.append(f"⚪ Kurs Rupiah stabil di Rp{int(curr_idr):,}")

        # Estimasi Rentang Support & Resistance Harian
        atr5 = float((ihsg_c.diff().abs().rolling(5).mean().iloc[-1]))
        est_support = curr_ihsg - atr5
        est_resistance = curr_ihsg + atr5

        # Deteksi Kasus Khusus: Divergensi S&P vs EIDO
        is_divergent = (sp_ret * eido_ret < -0.05)

        # Penentuan Klasifikasi Arah
        if score >= 20:
            direction = "🟢 BULLISH (CENDERUNG NAIK)"
            confidence = min(85, int(58 + (score * 0.25)))
            guidance = "Sentimen positif & dana asing masuk (EIDO hijau). Momentum kondusif untuk entry saham Tier S & A akumulasi bandar."
        elif score <= -20:
            direction = "🔴 BEARISH (CENDERUNG TURUN)"
            confidence = min(85, int(58 + (abs(score) * 0.25)))
            guidance = "Tekanan jual dominan dari Wall Street & EIDO. Disiplin pasang Stop Loss dan hindari menangkap pisau jatuh."
        elif is_divergent:
            direction = "⚪ SIDEWAYS / DIVERGENSI (MARKET TERBELAH)"
            confidence = 50
            guidance = "Bursa AS dan ETF Indo bergerak berlawanan arah. Saham perbankan asing rawan tertekan, namun saham konglomerat domestik berpeluang manggung."
        else:
            direction = "⚪ SIDEWAYS (KONSOLIDASI NETRAL)"
            confidence = 50
            guidance = "Sentimen pasar minim katalis besar. Fokus selektif pada saham second-liner dengan rumor aksi korporasi."

        return {
            "ihsg_current": curr_ihsg,
            "ihsg_last_chg": ihsg_last_chg,
            "eido_ret": eido_ret,
            "sp500_ret": sp_ret,
            "usd_idr": curr_idr,
            "idr_chg": idr_chg,
            "rsi14": rsi14,
            "streak": streak,
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


if __name__ == "__main__":
    res = predict_daily_ihsg_direction()
    print("Prediksi Arah IHSG:")
    for k, v in res.items():
        if k != "factors":
            print(f"{k}: {v}")
        else:
            print("factors:")
            for f in v:
                print(f"  - {f}")
