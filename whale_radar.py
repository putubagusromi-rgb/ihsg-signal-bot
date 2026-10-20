"""
Institutional Whale & Bandarmology Detection Engine (IHSG / BEI):
Mengadopsi metodologi institutional quantitative desk untuk melacak jejak Smart Money / Bandar di Bursa Efek Indonesia:
1. Volume Spread Analysis (VSA - Tom Williams / Richard Wyckoff):
   - Stopping Volume & Whale Absorption (High Volume, Narrow Spread at Support)
   - Supply Dry-Up Test (Volume anjlok drastis < 45% rata-rata di support = barang retail habis, siap mark-up)
   - Churning & Upthrust (High volume at peak without price progress = smart money dumping)
2. Institutional VWAP Anchor:
   - Menghitung estimasi harga modal rata-rata beli Whale (5D, 20D, 50D VWAP)
   - Menentukan apakah harga sedang di "Whale Discount Zone" atau "Mark-Up Zone"
3. Money Flow Divergence (Whale vs Retail):
   - Deteksi divergensi ketika harga saham ditekan turun / sideways, namun akumulasi uang masuk deras
4. Volatility Squeeze Accumulation:
   - Kompresi volatilitas Bollinger Band saat bandar mengontrol harga agar tidak gaduh
5. Whale Accumulation Tier List:
   - Pengelompokan saham ke dalam Tier S (God Tier), Tier A (High Conviction), dan Tier B (Early Accumulation).
"""

from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import numpy as np
from signal_engine import fetch_stock_data, calculate_support_resistance
from config import LQ45_WATCHLIST


def analyze_whale_footprint(ticker: str, df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """
    Analisis mendalam pergerakan Whale / Bandar sekelas institusi untuk satu saham.
    """
    clean = ticker.replace(".JK", "").strip().upper()
    if df is None or len(df) < 35:
        df = fetch_stock_data(clean, period="6mo", interval="1d")

    if df is None or len(df) < 35:
        return {"error": f"Data saham #{clean} tidak cukup untuk analisis Whale Footprint."}

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(latest["Close"])
    open_p = float(latest["Open"])
    high = float(latest["High"])
    low = float(latest["Low"])
    volume = float(latest["Volume"])

    # 1. Volume & Relative Volume Analysis
    vol_sma20 = float(df['Volume'].iloc[-20:].mean())
    vol_sma50 = float(df['Volume'].iloc[-50:].mean()) if len(df) >= 50 else vol_sma20
    rvol = float(volume / (vol_sma20 + 1e-9))

    # 2. Institutional VWAP (Estimasi Modal Bandar)
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3.0
    vol_series = df['Volume'] + 1e-9

    vwap_5d = float((typical_price.iloc[-5:] * vol_series.iloc[-5:]).sum() / vol_series.iloc[-5:].sum())
    vwap_20d = float((typical_price.iloc[-20:] * vol_series.iloc[-20:]).sum() / vol_series.iloc[-20:].sum())
    vwap_50d = float((typical_price.iloc[-50:] * vol_series.iloc[-50:]).sum() / vol_series.iloc[-50:].sum()) if len(df) >= 50 else vwap_20d

    pct_diff_vwap20 = ((close - vwap_20d) / vwap_20d) * 100.0

    # 3. Chaikin Money Flow (Whale Money Flow)
    clv = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / ((df['High'] - df['Low']) + 1e-9)
    mfv = clv * df['Volume']
    cmf_10 = float(mfv.iloc[-10:].sum() / vol_series.iloc[-10:].sum())
    cmf_20 = float(mfv.iloc[-20:].sum() / vol_series.iloc[-20:].sum())

    # 4. Price Spread & True Range (VSA)
    spread = high - low
    body = abs(close - open_p)
    lower_wick = min(close, open_p) - low
    upper_wick = high - max(close, open_p)
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - df['Close'].shift(1)).abs(),
        (df['Low'] - df['Close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    atr_14 = float(tr.iloc[-14:].mean())
    relative_spread = spread / (atr_14 + 1e-9)

    # 5. Support & Resistance Levels
    sup_20 = float(df['Low'].iloc[-21:-1].min())
    res_20 = float(df['High'].iloc[-21:-1].max())

    # 6. Volatility Squeeze (Bollinger Band Compression)
    sma_bb = df['Close'].rolling(20).mean()
    std_bb = df['Close'].rolling(20).std()
    bb_width = (2.0 * std_bb * 2.0) / (sma_bb + 1e-9)
    bb_width_latest = float(bb_width.iloc[-1])
    bb_width_min = float(bb_width.iloc[-60:].min()) if len(df) >= 60 else bb_width_latest
    is_squeeze = bb_width_latest <= (bb_width_min * 1.25)

    # 7. Footprint Detection Criteria
    # A. VSA: Stopping Volume & Absorption (Volume besar, spread sempit di dasar, ekor bawah panjang)
    is_absorption = (rvol >= 1.5 and lower_wick >= body * 0.6 and close <= sup_20 * 1.04)

    # B. VSA: Supply Dry-Up (Penjual habis/kering, volume anjlok < 0.55x SMA20 di dekat support)
    is_supply_dry = (rvol <= 0.55 and abs(close - sup_20) / (sup_20 + 1e-9) <= 0.035 and cmf_20 >= -0.05)

    # C. Wyckoff Bear Trap / Spring (Jebol support semu lalu mantul kembali)
    is_shakeout = (low < sup_20 and close >= sup_20 and lower_wick >= body * 0.5)

    # D. Stealth Accumulation (Harga flat/tertekan, tapi CMF konsisten positif kuat)
    chg_10d = ((close - float(df['Close'].iloc[-10])) / float(df['Close'].iloc[-10])) * 100.0
    is_stealth_acc = (cmf_10 >= 0.08 and chg_10d <= 2.5)

    # E. Mark-Up Momentum (Breakout resistance dengan volume & CMF kuat)
    is_markup = (close >= res_20 * 0.99 and rvol >= 1.3 and cmf_20 > 0.06)

    # F. Distribution Alert (Harga di pucuk dengan CMF negatif tajam atau volume klimaks gagal naik)
    is_distribution = (close >= res_20 * 0.97 and (cmf_10 < -0.10 or (rvol >= 2.0 and upper_wick >= body * 0.7)))

    # 8. Skor Whale Bandarmology (0 - 100)
    whale_score = 50
    if is_shakeout:
        whale_score += 35
    elif is_absorption:
        whale_score += 30
    elif is_supply_dry:
        whale_score += 25
    elif is_stealth_acc:
        whale_score += 25
    elif is_markup:
        whale_score += 28

    if cmf_20 > 0.15:
        whale_score += 15
    elif cmf_20 > 0.05:
        whale_score += 8
    elif cmf_20 < -0.10:
        whale_score -= 20

    if pct_diff_vwap20 < -1.5 and cmf_20 > 0:
        whale_score += 10
    elif pct_diff_vwap20 > 8.0:
        whale_score -= 10

    if is_squeeze and cmf_20 > 0:
        whale_score += 10

    if is_distribution:
        whale_score = min(whale_score, 30)

    whale_score = max(10, min(98, whale_score))

    # 9. Klasifikasi Fase & Rekomendasi Institusi
    if is_shakeout:
        status = "🪤 SHAKEOUT / BEAR TRAP"
        badge = "🟢 <b>SUPER STRONG BUY (JEBAKAN RETAIL)</b>"
        explanation = (
            "Bandar sengaja membanting harga ke bawah Support untuk menyapu Stop Loss retail, "
            "lalu memborong kembali seluruh antrean sebelum bursa tutup. Ini adalah titik masuk terbaik sekelas Smart Money!"
        )
        action_plan = f"Beli sekarang di area {int(close)}. Pasang Stop Loss ketat di {int(low - 10)}."
    elif is_absorption:
        status = "🛡️ WHALE ABSORPTION"
        badge = "🟢 <b>ABSORPSI VOLUME MASIF</b>"
        explanation = (
            f"Lonjakan volume {rvol:.1f}x rata-rata tertahan di dekat support dengan ekor bawah panjang. "
            "Whale sedang menampung guyuran panic selling tanpa membiarkan harga ambles lebih dalam."
        )
        action_plan = f"Akumulasi bertahap di kisaran {int(low)} - {int(close)}. TP1 di {int(vwap_20d * 1.05)}."
    elif is_supply_dry:
        status = "💧 SUPPLY DRY-UP"
        badge = "🚀 <b>BARANG RETAIL HABIS (SIAP TERBANG)</b>"
        explanation = (
            f"Volume transaksi anjlok kering ({rvol:.2f}x rata-rata) saat menguji level support. "
            "Tekanan jual sudah habis total. Ketika floating supply kering, sedikit dorongan bandar akan langsung menerbangkan harga."
        )
        action_plan = f"Buy on Weakness di {int(close)}. Potensi breakout cepat menuju {int(res_20)}."
    elif is_stealth_acc:
        status = "🤫 STEALTH ACCUMULATION"
        badge = "🟢 <b>AKUMULASI SENYAP DIBAWAH RADAR</b>"
        explanation = (
            f"Harga saham sengaja dibuat membosankan ({chg_10d:+.1f}%), namun arus modal institusi "
            f"(CMF 10D: +{cmf_10:.2f}) mengalir sangat deras. Bandar sedang mengumpulkan barang pelan-pelan."
        )
        action_plan = f"Ikuti cicil beli di harga diskon sebelum bandar melakukan Mark-Up."
    elif is_markup:
        status = "🚀 MARK-UP IN PROGRESS"
        badge = "🔥 <b>FASE MARK-UP (LEPAS LANDAS)</b>"
        explanation = (
            f"Whale sudah selesai mengumpulkan barang dan mulai menerbangkan harga menembus Resistance "
            f"dengan volume konfirmasi {rvol:.1f}x. Tren naik kuat sedang berjalan."
        )
        action_plan = f"Buy on Breakout / Follow the Trend. Trailing stop di {int(vwap_20d)}."
    elif is_distribution:
        status = "🔴 WHALE DISTRIBUTION"
        badge = "⚠️ <b>DISTRIBUSI / BANDAR BUANG BARANG</b>"
        explanation = (
            "Terdeteksi pelepasan barang oleh Smart Money di area pucuk. Arus uang keluar drastis "
            "meski harga tampak berusaha dipertahankan. Waspada jebakan Bull Trap bagi retail!"
        )
        action_plan = "Amankan profit (Take Profit) sekarang atau pasang ketat Trailing Stop."
    else:
        status = "⚖️ NETRAL / OBSERVASI"
        badge = "⚪ <b>NETRAL / KONSOLIDASI</b>"
        explanation = "Aktivitas Whale belum menunjukkan dominasi akumulasi maupun distribusi yang agresif. Pasar sedang mencari arah."
        action_plan = "Pantau pergerakan antrean bid/offer dan tunggu sinyal akumulasi yang lebih tegas."

    # Status Harga terhadap Modal Bandar
    if pct_diff_vwap20 < -2.0:
        cost_status = f"💎 <b>DISKON BANDAR ({abs(pct_diff_vwap20):.1f}% di bawah modal Whale)</b>"
    elif abs(pct_diff_vwap20) <= 2.0:
        cost_status = f"🎯 <b>SEIMBANG (Setara modal Whale: Rp {int(vwap_20d):,})</b>"
    else:
        cost_status = f"📈 <b>PREMIUM ({pct_diff_vwap20:+.1f}% di atas modal Whale)</b>"

    return {
        "ticker": clean,
        "close": close,
        "volume": volume,
        "rvol": rvol,
        "whale_score": whale_score,
        "status": status,
        "badge": badge,
        "explanation": explanation,
        "action_plan": action_plan,
        "cost_status": cost_status,
        "vwap_5d": vwap_5d,
        "vwap_20d": vwap_20d,
        "vwap_50d": vwap_50d,
        "pct_diff_vwap20": pct_diff_vwap20,
        "cmf_10": cmf_10,
        "cmf_20": cmf_20,
        "sup_20": sup_20,
        "res_20": res_20,
        "is_squeeze": is_squeeze,
        "tp1": round(res_20, 2),
        "tp2": round(res_20 * 1.08, 2),
        "sl": round(sup_20 * 0.97, 2)
    }


def scan_top_whale_accumulations(watchlist: Optional[List[str]] = None, limit: int = 6, max_workers: int = 8) -> List[Dict[str, Any]]:
    """
    Memindai seluruh saham di watchlist secara paralel untuk mencari akumulasi Whale tertinggi.
    """
    tickers = watchlist or LQ45_WATCHLIST
    results = []

    def _fetch(t):
        try:
            return analyze_whale_footprint(t)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        raw_res = list(ex.map(_fetch, tickers))

    for res in raw_res:
        if res and "error" not in res and res.get("whale_score", 0) >= 70:
            results.append(res)

    results.sort(key=lambda x: x["whale_score"], reverse=True)
    return results[:limit]


def get_whale_tier_list(watchlist: Optional[List[str]] = None, max_workers: int = 8) -> Dict[str, List[Dict[str, Any]]]:
    """
    Menyusun Tier List saham yang sedang diakumulasi Whale:
    - Tier S (Monster Whale & High Conviction): Skor >= 90
    - Tier A (Strong Inflow & Ready to Breakout): Skor 80 - 89
    - Tier B (Early Accumulation / Support Test): Skor 70 - 79
    """
    tickers = watchlist or LQ45_WATCHLIST
    tier_s = []
    tier_a = []
    tier_b = []

    def _fetch(t):
        try:
            return analyze_whale_footprint(t)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        raw_res = list(ex.map(_fetch, tickers))

    for res in raw_res:
        if not res or "error" in res:
            continue
        score = res.get("whale_score", 0)
        if score >= 90:
            tier_s.append(res)
        elif score >= 80:
            tier_a.append(res)
        elif score >= 70:
            tier_b.append(res)

    tier_s.sort(key=lambda x: (x["whale_score"], -x["pct_diff_vwap20"]), reverse=True)
    tier_a.sort(key=lambda x: (x["whale_score"], -x["pct_diff_vwap20"]), reverse=True)
    tier_b.sort(key=lambda x: (x["whale_score"], -x["pct_diff_vwap20"]), reverse=True)

    return {
        "tier_s": tier_s,
        "tier_a": tier_a,
        "tier_b": tier_b
    }
