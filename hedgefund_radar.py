"""
Modul Hedge Fund Smart Money & Wyckoff Method:
Mengadopsi strategi kuantitatif Hedge Fund institusi untuk mengikuti jejak Bandar:
1. Wyckoff Phases: Silent Accumulation, Spring/Shakeout (Jebakan Retail), Markup (Sign of Strength), Distribution.
2. Volume Spread Analysis (VSA): Stopping Volume, Absorption, Climax.
3. Institutional VWAP Discount Zone: Membeli di harga diskon di bawah modal bandar.
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from signal_engine import fetch_stock_data, calculate_support_resistance
from config import LQ45_WATCHLIST


def analyze_hedgefund_wyckoff(ticker: str, df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """
    Menganalisis fase akumulasi dan footprint bandar ala Hedge Fund.
    """
    clean = ticker.replace(".JK", "").strip().upper()
    if df is None or len(df) < 30:
        df = fetch_stock_data(clean, period="6mo", interval="1d")

    if df is None or len(df) < 30:
        return {"error": f"Data saham #{clean} tidak cukup untuk analisis Hedge Fund."}

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(latest["Close"])
    open_p = float(latest["Open"])
    high = float(latest["High"])
    low = float(latest["Low"])
    volume = float(latest["Volume"])

    # 1. Hitung Chaikin Money Flow & Relative Volume
    mfv = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / ((df['High'] - df['Low']) + 1e-9) * df['Volume']
    cmf_10 = float(mfv.iloc[-10:].sum() / (df['Volume'].iloc[-10:].sum() + 1e-9))
    cmf_20 = float(mfv.iloc[-20:].sum() / (df['Volume'].iloc[-20:].sum() + 1e-9))

    vol_sma20 = float(df['Volume'].iloc[-20:].mean())
    rvol = float(volume / (vol_sma20 + 1e-9))

    # 2. Hitung Institutional VWAP (Modal Rata-rata Bandar 20 Hari)
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    vwap_20 = float((typical_price * df['Volume']).iloc[-20:].sum() / (df['Volume'].iloc[-20:].sum() + 1e-9))
    pct_from_vwap = ((close - vwap_20) / vwap_20) * 100

    # 3. Support & Resistance 20 Hari
    sup_20 = float(df['Low'].iloc[-21:-1].min())
    res_20 = float(df['High'].iloc[-21:-1].max())

    # 4. Deteksi The Spring / Shakeout (Jebakan Bandar Buang Penumpang)
    body = abs(close - open_p)
    lower_wick = min(close, open_p) - low
    is_spring = (low < sup_20 and close >= sup_20 and lower_wick >= body * 0.7)

    # 5. Deteksi Silent Accumulation (Penyerapan Diam-diam)
    chg_10d = ((close - float(df['Close'].iloc[-10])) / float(df['Close'].iloc[-10])) * 100
    is_silent_acc = (cmf_10 > 0.08 and chg_10d <= 3.0)

    # 6. Deteksi Sign of Strength (SOS / Breakout Mark-Up)
    is_sos = (close > res_20 and rvol >= 1.4 and cmf_20 > 0.05)

    # 7. Deteksi Distribusi / Bull Trap
    is_distribution = (chg_10d < -5.0 and cmf_10 < -0.15) or (close >= res_20 * 0.98 and cmf_10 < -0.10)

    # Menentukan Fase Wyckoff
    if is_spring:
        phase = "PHASE C: THE SPRING / SHAKEOUT"
        phase_badge = "🪤 <b>SPRING REVERSAL (JEBAKAN RETAIL)</b>"
        phase_desc = (
            "Bandar sengaja membanting harga jebol Support untuk memancing Stop Loss retail, "
            "lalu memborong kembali sebelum harga diterbangkan. Ini titik beli terbaik Hedge Fund!"
        )
        recommendation = "STRONG BUY ON SPRING (Beli sekarang dengan Stop Loss ketat di bawah Low jarum)."
        hedge_score = 92

    elif is_silent_acc:
        phase = "PHASE B: SILENT ABSORPTION"
        phase_badge = "🤫 <b>AKUMULASI DIAM-DIAM (SILENT WHALE)</b>"
        phase_desc = (
            f"Harga saham masih sideways/tertekan ({chg_10d:+.1f}%), tapi arus uang bandar sangat deras masuk "
            f"(CMF 10-hari: +{cmf_10:.2f}). Bandar sedang menyerap barang tanpa bikin gaduh pasar."
        )
        recommendation = "ACCUMULATIVE BUY (Cicil beli mumpung harga belum digoreng naik)."
        hedge_score = 85

    elif is_sos:
        phase = "PHASE D: SIGN OF STRENGTH (MARKUP)"
        phase_badge = "🚀 <b>SIGN OF STRENGTH (BREAKOUT INSTITUSI)</b>"
        phase_desc = (
            f"Fase lepas landas! Saham menjebol resistance 20 hari dengan lonjakan volume {rvol:.1f}x "
            f"dan konfirmasi dana institusi. Tahap awal tren naik besar."
        )
        recommendation = "BUY ON BREAKOUT (Ikuti momentum dengan trailing stop)."
        hedge_score = 88

    elif is_distribution:
        phase = "DISTRIBUTION: SMART MONEY EXIT"
        phase_badge = "🔴 <b>DISTRIBUSI / PELEPASAN BARANG</b>"
        phase_desc = "Bandar sedang membuang muatan secara bertahap. Arus dana keluar deras."
        recommendation = "AVOID / TAKE PROFIT (Hindari atau amankan modal)."
        hedge_score = 25

    else:
        if pct_from_vwap < -2.0:
            phase = "PHASE A: DISCOUNT CONSOLIDATION"
            phase_badge = "🏷️ <b>ZONA DISKON DI BAWAH MODAL BANDAR</b>"
            phase_desc = f"Harga saat ini berada {pct_from_vwap:.1f}% di bawah estimasi harga modal rata-rata bandar (Rp{int(vwap_20):,})."
            recommendation = "BUY ON WEAKNESS (Area beli aman mendekati support)."
            hedge_score = 65
        else:
            phase = "NEUTRAL: CONSOLIDATION"
            phase_badge = "⚪ <b>KONSOLIDASI NORMAL</b>"
            phase_desc = "Pergerakan harga dan volume berimbang tanpa aktivitas institusi yang dominan."
            recommendation = "MONITORING (Pantau pergerakan volume berikutnya)."
            hedge_score = 50

    return {
        "ticker": clean,
        "price": int(close),
        "phase": phase,
        "phase_badge": phase_badge,
        "phase_desc": phase_desc,
        "hedge_score": hedge_score,
        "recommendation": recommendation,
        "vwap_20": int(vwap_20),
        "pct_from_vwap": round(pct_from_vwap, 2),
        "cmf_10": round(cmf_10, 3),
        "rvol": round(rvol, 2),
        "support_20": int(sup_20),
        "resistance_20": int(res_20),
        "spring_low": int(low) if is_spring else int(sup_20 * 0.98),
        "tp_target": int(res_20 * 1.05) if is_sos else int(res_20)
    }


def scan_hedgefund_picks(limit: int = 6) -> List[Dict[str, Any]]:
    """
    Menyaring saham-saham pilihan yang saat ini berada di radar fase Hedge Fund
    (Spring Shakeout atau Silent Absorption).
    """
    picks = []
    for sym in LQ45_WATCHLIST:
        try:
            res = analyze_hedgefund_wyckoff(sym)
            if "error" in res:
                continue
            if res["hedge_score"] >= 80:
                picks.append(res)
        except Exception:
            continue

    picks.sort(key=lambda x: x["hedge_score"], reverse=True)
    return picks[:limit]
