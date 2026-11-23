"""
Modul RWY Alpha Scanner (Real-Time Market-Wide Scanner):
Memindai seluruh semesta saham likuid IDX dengan logika Robot RWY V2:
1. Kompas Arah Pasar IHSG (Market Direction Compass)
2. Filter Stage 2 Uptrend Saham (Price > SMA20 > SMA50)
3. Filter Relative Strength (RS vs IHSG)
4. Deteksi Akumulasi Bandar Masif (High-Conviction Breakout & Whale Pre-Closing / BSJP)
"""

import yfinance as yf
import pandas as pd
import numpy as np
import html
from datetime import datetime
from typing import List, Dict, Any

try:
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
except Exception:
    WIB = None

from config import LQ45_WATCHLIST, KOMPAS100_WATCHLIST

SCANNER_UNIVERSE = sorted(list(set(
    LQ45_WATCHLIST + [
        "PANI", "BREN", "CUAN", "TPIA", "BRPT", "BRMS", "DEWA", "BUMI", 
        "WIFI", "RAJA", "PSAB", "VKTR", "TOBA", "DOID", "ELSA", "MEDC",
        "PTRO", "BIPI", "ADRO", "ITMG", "PTBA", "ANTM", "MDKA", "MBMA", 
        "HRUM", "PGAS", "PGEO", "ESSA", "INKP", "TKIM", "ERAA", "CPIN", 
        "JPFA", "CLEO", "CMRY", "MYOR", "ACES", "AUTO", "ASII", "AMMN",
        "BRIS", "BBCA", "BMRI", "BBRI", "BBNI", "TLKM", "GOTO", "KLBF"
    ]
)))

def get_market_compass() -> Dict[str, Any]:
    """Mendiagnosa arah dan rezim tren IHSG (Market Compass)."""
    try:
        ihsg = yf.download("^JKSE", period="6mo", interval="1d", progress=False)
        if ihsg is None or len(ihsg) < 50:
            return {"status": "UNKNOWN", "score": 50, "regime": "Data Terbatas"}

        c = ihsg["Close"]
        if isinstance(c, pd.DataFrame):
            c = c.iloc[:, 0]

        curr_c = float(c.iloc[-1])
        c_prev = float(c.iloc[-2]) if len(c) > 1 else curr_c
        c_p5 = float(c.iloc[-6]) if len(c) >= 6 else c_prev
        
        sma20 = float(c.rolling(20).mean().iloc[-1])
        sma50 = float(c.rolling(50).mean().iloc[-1])

        chg_1d = ((curr_c - c_prev) / c_prev) * 100
        chg_5d = ((curr_c - c_p5) / c_p5) * 100

        # Cek Rezim
        is_bullish = curr_c > sma20 and sma20 > sma50
        is_bearish = curr_c < sma20 and sma20 < sma50

        if is_bullish:
            regime = "BULLISH / RISK-ON (Zona Berburu Agresif)"
            status = "BULLISH"
            color_emoji = "🟢"
            advice = "IHSG di atas SMA20 & SMA50. Momentum pasar kuat, aman berburu saham breakout & runner!"
        elif is_bearish:
            regime = "BEARISH / RISK-OFF (Pasar Downtrend)"
            status = "BEARISH"
            color_emoji = "🔴"
            advice = "IHSG di bawah SMA20 & SMA50. Pasar dalam tekanan jual. Disiplin cash defense!"
        else:
            regime = "KONSOLIDASI / NETRAL (Selective Picking)"
            status = "NEUTRAL"
            color_emoji = "🟡"
            advice = "IHSG sedang sideway/menguji area moving average. Fokus hanya pada saham dengan Relative Strength tertinggi!"

        return {
            "status": status,
            "regime": regime,
            "color_emoji": color_emoji,
            "close": curr_c,
            "chg_1d": chg_1d,
            "chg_5d": chg_5d,
            "sma20": sma20,
            "sma50": sma50,
            "advice": advice
        }
    except Exception as e:
        return {
            "status": "UNKNOWN",
            "regime": f"Error: {e}",
            "color_emoji": "⚪",
            "close": 0,
            "chg_1d": 0,
            "chg_5d": 0,
            "sma20": 0,
            "sma50": 0,
            "advice": "Gunakan manajemen risiko mandiri."
        }


def run_rwy_alpha_scanner(universe: List[str] = None, min_turnover: float = 3_000_000_000) -> Dict[str, Any]:
    """
    Pemindai pasar multi-saham yang menyaring seluruh semesta saham IDX
    menggunakan formula Robot RWY V2 (Stage 2 Uptrend, Relative Strength, Volume Absorption, CMF).
    """
    if universe is None:
        universe = SCANNER_UNIVERSE

    compass = get_market_compass()
    all_syms = [f"{t}.JK" for t in universe] + ["^JKSE"]
    raw = yf.download(all_syms, period="4mo", interval="1d", progress=False, group_by="ticker")

    # Hitung Return 20 Hari IHSG
    ihsg_ret20 = 0.0
    if "^JKSE" in raw and len(raw["^JKSE"]) >= 21:
        ihsg_c = raw["^JKSE"]["Close"].dropna()
        if len(ihsg_c) >= 21:
            ihsg_ret20 = float((ihsg_c.iloc[-1] - ihsg_c.iloc[-21]) / ihsg_c.iloc[-21])

    candidates = []

    for ticker in universe:
        sym = f"{ticker}.JK"
        if sym not in raw:
            continue
        df = raw[sym].dropna()
        if len(df) < 25:
            continue

        c = df["Close"]
        h = df["High"]
        l = df["Low"]
        o = df["Open"]
        v = df["Volume"]

        c_today = float(c.iloc[-1])
        c_prev = float(c.iloc[-2])
        h_today = float(h.iloc[-1])
        l_today = float(l.iloc[-1])
        v_today = float(v.iloc[-1])

        turnover_today = c_today * v_today
        if turnover_today < min_turnover or c_today < 70:
            continue

        sma20 = float(c.rolling(20).mean().iloc[-1])
        sma50 = float(c.rolling(50).mean().iloc[-1])
        ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])

        # 1. Filter Stage 2 Uptrend Saham
        if c_today < sma20 or sma20 < sma50:
            continue

        # 2. Filter Relative Strength vs IHSG
        ret20_stock = float((c_today - c.iloc[-21]) / c.iloc[-21]) if len(c) >= 21 else 0.0
        rs_score = ret20_stock - ihsg_ret20
        if ret20_stock <= ihsg_ret20:
            continue # Saham kalah kuat dari IHSG, singkirkan!

        # 3. Dominasi Buyer pada Candle Hari Ini (Close Position)
        hl_span = max(1e-5, h_today - l_today)
        close_pos = (c_today - l_today) / hl_span
        if close_pos < 0.60:
            continue # Terlalu banyak jarum suntik / rejection wick

        # 4. Anti Pucuk (Jangan beli jika sudah > 15% di atas EMA20)
        if c_today > ema20 * 1.15:
            continue

        pct_chg = ((c_today - c_prev) / c_prev) * 100
        v_sma20 = float(v.rolling(20).mean().iloc[-1])
        rvol = v_today / (v_sma20 + 1e-9)

        # Chaikin Money Flow (CMF 20 Hari)
        hl_series = (h - l).replace(0, np.nan)
        mfm = ((c - l) - (h - c)) / hl_series
        cmf20 = float((mfm.fillna(0) * v).rolling(20).sum().iloc[-1] / (v.rolling(20).sum().iloc[-1] + 1e-9))

        high_20 = float(h.rolling(20).max().iloc[-2]) if len(h) >= 21 else h_today
        is_breakout_20 = c_today >= (high_20 * 0.995)

        # Evaluasi Kategori Setup
        category = None
        score = 0

        # Kategori 1: High-Conviction Breakout
        if is_breakout_20 and pct_chg >= 2.5 and rvol >= 1.8 and cmf20 >= 0.10:
            category = "HIGH-CONVICTION BREAKOUT"
            score = 85 + (pct_chg * 1.8) + (rvol * 5.0) + (cmf20 * 40.0)
            tag = "🚀 BREAKOUT 20D"

        # Kategori 2: Whale Pre-Closing Mark-up (BSJP Sore)
        elif pct_chg >= 2.0 and rvol >= 1.8 and cmf20 >= 0.10:
            category = "WHALE PRE-CLOSING (BSJP)"
            score = 80 + (pct_chg * 1.6) + (rvol * 4.5) + (cmf20 * 35.0)
            tag = "🌇 WHALE BSJP"

        # Kategori 3: Stage-2 Alpha Leader (Strong Uptrend Consolidation / Rebound)
        elif pct_chg >= 1.0 and rvol >= 1.3 and cmf20 >= 0.12 and rs_score >= 0.05:
            category = "STAGE-2 ALPHA LEADER"
            score = 75 + (pct_chg * 1.2) + (rvol * 3.5) + (cmf20 * 30.0) + (rs_score * 50.0)
            tag = "💎 ALPHA LEADER"

        if category:
            candidates.append({
                "ticker": ticker,
                "close": int(c_today),
                "pct_chg": round(pct_chg, 2),
                "rvol": round(rvol, 2),
                "cmf": round(cmf20, 2),
                "rs_score": round(rs_score * 100, 1),
                "close_pos": round(close_pos * 100, 0),
                "turnover_m": round(turnover_today / 1e9, 1),
                "category": category,
                "tag": tag,
                "score": round(score, 1),
                "stop_loss": int(c_today * 0.945), # Strict SL 5.5%
                "tp1": int(c_today * 1.07),
                "tp2": int(c_today * 1.15)
            })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    return {
        "timestamp": datetime.now(WIB).strftime("%d %b %Y, %H:%M WIB") if WIB else datetime.now().strftime("%d %b %Y, %H:%M WIB"),
        "compass": compass,
        "total_scanned": len(universe),
        "total_passed": len(candidates),
        "candidates": candidates
    }


def format_rwy_scanner_message(scan_result: Dict[str, Any]) -> str:
    """Memformat output scanner ke pesan Telegram berstandar institusi."""
    compass = scan_result.get("compass", {})
    candidates = scan_result.get("candidates", [])
    ts = scan_result.get("timestamp", "")

    lines = [
        "📡 <b>RADAR SCANNER RWY ALPHA ENGINE (REAL-TIME)</b> ⚡",
        f"⏱️ <i>Waktu Pemindaian: {ts}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🧭 <b>KOMPAS ARAH IHSG:</b> {compass.get('color_emoji', '⚪')} <b>{compass.get('regime', 'NORMAL')}</b>",
        f"• Indeks IHSG : <code>{compass.get('close', 0):,.0f}</code> ({'+' if compass.get('chg_1d', 0)>=0 else ''}{compass.get('chg_1d', 0):.2f}% 1D)",
        f"• Status MA   : SMA20 <code>{compass.get('sma20', 0):,.0f}</code> | SMA50 <code>{compass.get('sma50', 0):,.0f}</code>",
        f"💡 <i>{compass.get('advice', '')}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━"
    ]

    if not candidates:
        lines.append("🔍 <b>Hasil Scanner:</b> <i>Tidak ada saham yang lolos kriteria ketat saat ini.</i>")
        lines.append("💡 <i>Kriteria RWY V2 sangat disiplin (Stage 2 Uptrend + Volume $\ge$ 2x + CMF Positif). Pasar sedang selektif atau cash is king!</i>")
    else:
        lines.append(f"🎯 <b>Ditemukan {len(candidates)} Saham Lolos Kriteria Akumulasi &amp; Breakout:</b>\n")
        for idx, c in enumerate(candidates[:8], 1):
            chg_sign = "+" if c["pct_chg"] >= 0 else ""
            lines.append(
                f"<b>{idx}. #{c['ticker']}</b> — <b>Rp {c['close']:,}</b> ({chg_sign}{c['pct_chg']}%) [{c['tag']}]\n"
                f"   • 📊 <b>Volume Surge :</b> <code>RVOL {c['rvol']}x</code> | <code>Turnover: Rp {c['turnover_m']} M</code>\n"
                f"   • 🐋 <b>Smart Money  :</b> <code>CMF: {c['cmf']:+.2f}</code> | <code>RS vs IHSG: +{c['rs_score']}%</code>\n"
                f"   • 🎯 <b>Target TP    :</b> <code>TP1 Rp {c['tp1']:,} (+7%)</code> | <code>TP2 Rp {c['tp2']:,} (+15%)</code>\n"
                f"   • ⛔ <b>Batas SL     :</b> <code>Rp {c['stop_loss']:,} (-5.5%)</code> <i>[Wajib Ketat!]</i>\n"
            )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(
        "💡 <b>PANDUAN EKSEKUSI SCANNER:</b>\n"
        "1. <b>Beda dengan Daily Pick:</b> Scanner ini menampilkan seluruh saham yang sedang aktif diakumulasi saat ini secara dinamis.\n"
        "2. <b>Aturan Tangga Proteksi:</b> Begitu profit mencapai <b>+3.5%</b>, geser Stop Loss ke modal (+0.8% net). Jangan biarkan saham yang sudah hijau berbalik merah!\n"
        "3. <b>Uncapped Runner:</b> Jika saham ditarik kencang, ikuti dengan trailing stop (+20%, +40%)."
    )
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/pick</code> untuk melihat 3 Saham Pilihan Resmi dengan Trading Plan Komplit.</i>")

    return "\n".join(lines)

if __name__ == "__main__":
    print("Testing RWY Alpha Scanner...")
    res = run_rwy_alpha_scanner()
    print(f"Total Scanned: {res['total_scanned']} | Total Passed: {res['total_passed']}")
    print(format_rwy_scanner_message(res))
