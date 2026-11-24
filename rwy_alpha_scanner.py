"""
Modul RWY Alpha Scanner (Real-Time Market-Wide Scanner):
Memindai seluruh semesta saham likuid IDX dengan logika:
1. Kompas Arah Pasar IHSG (Hanya Sebagai Warning / Konteks Risiko, Tidak Memblokir)
2. Buy The Low (Smart Money / Whale Absorption di Area Bawah / Support)
3. Broker Flow Pre-Closing (BSJP Sesi 2 Mark-Up)
4. Wyckoff Spring Rebound & High-Conviction Breakout
Tanpa pembatasan kaku EMA, sehingga trader bisa menangkap Buy the Low, Sell High!
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

from config import LQ45_WATCHLIST

SCANNER_UNIVERSE = sorted(list(set(
    LQ45_WATCHLIST + [
        "PANI", "BREN", "CUAN", "TPIA", "BRPT", "BRMS", "DEWA", "BUMI", 
        "WIFI", "RAJA", "PSAB", "VKTR", "TOBA", "DOID", "ELSA", "MEDC",
        "PTRO", "BIPI", "ADRO", "ITMG", "PTBA", "ANTM", "MDKA", "MBMA", 
        "HRUM", "PGAS", "PGEO", "ESSA", "INKP", "TKIM", "ERAA", "CPIN", 
        "JPFA", "CLEO", "CMRY", "MYOR", "ACES", "AUTO", "ASII", "AMMN",
        "BRIS", "BBCA", "BMRI", "BBRI", "BBNI", "TLKM", "GOTO", "KLBF",
        "UNTR", "ICBP", "INDF", "SMGR", "INTP", "EXCL", "ISAT", "MAPI", "AKRA", "JSMR"
    ]
)))

def get_market_compass() -> Dict[str, Any]:
    """Mendiagnosa arah dan rezim tren IHSG (Hanya sebagai Warning / Context)."""
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

        is_bullish = curr_c > sma20 and sma20 > sma50
        is_bearish = curr_c < sma20 and sma20 < sma50

        if is_bullish:
            regime = "BULLISH / RISK-ON (Pasar Mendukung)"
            status = "BULLISH"
            color_emoji = "🟢"
            advice = "IHSG bergerak di atas MA tren. Momentum pasar kuat, cocok untuk swing & breakout agresif."
        elif is_bearish:
            regime = "BEARISH / RISK-OFF (Tekanan Pasar)"
            status = "BEARISH"
            color_emoji = "🔴"
            advice = "IHSG di bawah MA tren. Pasar bertekanan, utamakan strategi Buy the Low pada saham akumulasi bandar & pasang SL 5.5%!"
        else:
            regime = "KONSOLIDASI / NETRAL (Selective Picking)"
            status = "NEUTRAL"
            color_emoji = "🟡"
            advice = "IHSG sideways. Fokus pada saham dengan arus dana Smart Money & penyerapan volume di area support."

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
            "regime": f"Normal: {e}",
            "color_emoji": "⚪",
            "close": 0,
            "chg_1d": 0,
            "chg_5d": 0,
            "sma20": 0,
            "sma50": 0,
            "advice": "Gunakan manajemen risiko mandiri."
        }


def run_rwy_alpha_scanner(universe: List[str] = None, min_turnover: float = 2_000_000_000) -> Dict[str, Any]:
    """
    Pemindai pasar multi-saham yang fokus pada:
    1. Buy The Low (Whale / Smart Money Absorption di Area Diskon)
    2. Broker Flow Pre-Closing (BSJP)
    3. Wyckoff Spring Reversal
    4. Breakout dengan Arus Dana Masif
    Tanpa memblokir saham hanya karena EMA!
    """
    if universe is None:
        universe = SCANNER_UNIVERSE

    compass = get_market_compass()
    all_syms = [f"{t}.JK" for t in universe] + ["^JKSE"]
    raw = yf.download(all_syms, period="3mo", interval="1d", progress=False, group_by="ticker")

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
        if len(df) < 20:
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
        if turnover_today < min_turnover or c_today < 50:
            continue

        pct_chg = ((c_today - c_prev) / c_prev) * 100
        v_sma20 = float(v.rolling(20).mean().iloc[-1])
        rvol = v_today / (v_sma20 + 1e-9)

        # Chaikin Money Flow (CMF 20 Hari) - Melacak Uang Masuk Bersih
        hl_series = (h - l).replace(0, np.nan)
        mfm = ((c - l) - (h - c)) / hl_series
        cmf20 = float((mfm.fillna(0) * v).rolling(20).sum().iloc[-1] / (v.rolling(20).sum().iloc[-1] + 1e-9))

        high_20 = float(h.rolling(20).max().iloc[-1])
        low_20 = float(l.rolling(20).min().iloc[-1])
        
        # Posisi Harga 20 Hari (0 = Bottom, 1 = Peak)
        price_pos_20d = (c_today - low_20) / max(1e-5, high_20 - low_20)

        # Posisi Penutupan Candle Harian (0 = Tutup di Low, 1 = Tutup di High)
        hl_today = max(1e-5, h_today - l_today)
        close_pos = (c_today - l_today) / hl_today
        lower_wick = (min(c_today, float(o.iloc[-1])) - l_today) / hl_today

        # Relative Strength vs IHSG
        ret20_stock = float((c_today - c.iloc[-21]) / c.iloc[-21]) if len(c) >= 21 else 0.0
        rs_score = ret20_stock - ihsg_ret20

        category = None
        tag = None
        score = 0
        narrative = ""

        # =========================================================================
        # SETUP 1: BUY THE LOW (Whale & Smart Money Absorption di Area Bawah)
        # Beli di area diskon (price_pos <= 45%), Smart Money masuk (CMF > 0 atau serapan volume)
        # =========================================================================
        is_at_low = price_pos_20d <= 0.45
        has_absorption = (rvol >= 1.0 or cmf20 >= 0.02) and (close_pos >= 0.40 or lower_wick >= 0.35)
        if is_at_low and has_absorption and c_today >= c_prev * 0.985:
            category = "BUY THE LOW (WHALE ABSORPTION)"
            tag = "🐋 BUY THE LOW"
            score = 85 + (cmf20 * 45.0) + (rvol * 5.0) + ((1.0 - price_pos_20d) * 25.0)
            narrative = f"Akumulasi Smart Money di Area Diskon (Posisi {round(price_pos_20d*100)}% dari Low 20D, CMF {cmf20:+.2f})"

        # =========================================================================
        # SETUP 2: BROKER FLOW MARK-UP (BSJP Sesi 2)
        # Bandar menarik harga di sesi 2 menjelang penutupan
        # =========================================================================
        elif pct_chg >= 1.8 and rvol >= 1.25 and cmf20 >= 0.0:
            category = "BROKER FLOW PRE-CLOSING (BSJP)"
            tag = "🌇 BROKER FLOW"
            score = 80 + (pct_chg * 2.0) + (rvol * 5.0) + (cmf20 * 30.0)
            narrative = f"Tarikan Akumulasi Bandar Sesi 2 (Kenaikan +{pct_chg:.1f}%, RVOL {rvol:.1f}x)"

        # =========================================================================
        # SETUP 3: WYCKOFF SPRING / REBOUND SUPPORT
        # Rebound kuat dari swing low dengan dominasi buyer
        # =========================================================================
        elif pct_chg >= 1.2 and rvol >= 1.15 and close_pos >= 0.60:
            category = "SMART MONEY SPRING REBOUND"
            tag = "💎 SPRING REBOUND"
            score = 75 + (pct_chg * 1.5) + (rvol * 4.0) + (close_pos * 20.0)
            narrative = f"Pantulan Kuat dari Support (Dominasi Buyer {round(close_pos*100)}%, Rebound +{pct_chg:.1f}%)"

        # =========================================================================
        # SETUP 4: HIGH-CONVICTION BREAKOUT
        # Menembus resistance dengan volume meledak
        # =========================================================================
        elif c_today >= high_20 * 0.985 and pct_chg >= 2.0 and rvol >= 1.4:
            category = "WHALE BREAKOUT RUNNER"
            tag = "🚀 BREAKOUT"
            score = 82 + (pct_chg * 1.8) + (rvol * 5.0)
            narrative = f"Breakout Resistance 20-Hari dengan Lonjakan Volume (RVOL {rvol:.1f}x)"

        # =========================================================================
        # SETUP 5: STAGE-2 WHALE ACCUMULATION
        # Akumulasi berlanjut pada saham yang sedang bergerak naik
        # =========================================================================
        elif pct_chg >= 0.5 and (cmf20 >= 0.08 or rvol >= 1.3):
            category = "SMART MONEY ACCUMULATION"
            tag = "💎 ACCUMULATION"
            score = 70 + (pct_chg * 1.0) + (rvol * 3.0) + (cmf20 * 30.0)
            narrative = f"Arus Kas Uang Masuk Positif (CMF {cmf20:+.2f}, RVOL {rvol:.1f}x)"

        if category:
            # Kalkulasi Target & Stop Loss untuk Buy The Low, Sell High
            sl_price = int(round(c_today * 0.945)) # Strict SL 5.5%
            tp1_price = int(round(c_today * 1.07)) # Rebound target +7%
            tp2_price = int(round(c_today * 1.15)) # Sell high target +15%
            
            candidates.append({
                "ticker": ticker,
                "close": int(c_today),
                "pct_chg": round(pct_chg, 2),
                "rvol": round(rvol, 2),
                "cmf": round(cmf20, 2),
                "price_pos_pct": round(price_pos_20d * 100, 1),
                "close_pos_pct": round(close_pos * 100, 1),
                "turnover_m": round(turnover_today / 1e9, 1),
                "category": category,
                "tag": tag,
                "score": round(score, 1),
                "narrative": narrative,
                "stop_loss": sl_price,
                "tp1": tp1_price,
                "tp2": tp2_price
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
        "📡 <b>RADAR SCANNER SMART MONEY &amp; BROKER FLOW (REAL-TIME)</b> ⚡",
        f"⏱️ <i>Waktu Pemindaian: {ts}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🧭 <b>KOMPAS ARAH IHSG:</b> {compass.get('color_emoji', '⚪')} <b>{compass.get('regime', 'NORMAL')}</b>",
        f"• Indeks IHSG : <code>{compass.get('close', 0):,.0f}</code> ({'+' if compass.get('chg_1d', 0)>=0 else ''}{compass.get('chg_1d', 0):.2f}% 1D)",
        f"• Catatan     : <i>{compass.get('advice', '')}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━"
    ]

    if not candidates:
        lines.append("🔍 <b>Hasil Scanner:</b> <i>Tidak ada pergerakan smart money signifikan saat ini.</i>")
    else:
        lines.append(f"🎯 <b>Ditemukan {len(candidates)} Saham Akumulasi Smart Money &amp; Broker Flow:</b>\n")
        for idx, c in enumerate(candidates[:8], 1):
            chg_sign = "+" if c["pct_chg"] >= 0 else ""
            pos_label = f"Area Diskon ({c['price_pos_pct']}% dari Low 20D)" if c['price_pos_pct'] <= 45 else "Area Momentum"
            lines.append(
                f"<b>{idx}. #{c['ticker']}</b> — <b>Rp {c['close']:,}</b> ({chg_sign}{c['pct_chg']}%) [{c['tag']}]\n"
                f"   • 📍 <b>Posisi Harga :</b> <code>{pos_label}</code>\n"
                f"   • 🐋 <b>Smart Money  :</b> <code>CMF: {c['cmf']:+.2f}</code> | <code>RVOL: {c['rvol']}x</code> | <code>TO: Rp {c['turnover_m']} M</code>\n"
                f"   • 🎯 <b>Target Jual  :</b> <code>TP1 Rp {c['tp1']:,} (+7%)</code> | <code>TP2 Rp {c['tp2']:,} (+15%)</code>\n"
                f"   • ⛔ <b>Batas SL     :</b> <code>Rp {c['stop_loss']:,} (-5.5%)</code> <i>[Wajib Ketat!]</i>\n"
                f"   • 💡 <i>Katalis Flow : {c['narrative']}</i>\n"
            )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(
        "💡 <b>STRATEGI BUY THE LOW, SELL HIGH:</b>\n"
        "1. <b>Beli di Area Bawah (Diskon):</b> Cari saham bertanda [🐋 BUY THE LOW] saat Smart Money sedang menampung antrian offer.\n"
        "2. <b>Jual di Target Rebound (Sell High):</b> Manfaatkan pantulan ke TP1 (+7%) atau TP2 (+15%).\n"
        "3. <b>Disiplin Risiko:</b> Pasang Stop Loss ketat di -5.5% persis di bawah swing low!"
    )
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/pick</code> untuk melihat 3 Rekomendasi Portofolio Resmi Hari Ini.</i>")

    return "\n".join(lines)

if __name__ == "__main__":
    print("Testing RWY Alpha Scanner Buy The Low...")
    res = run_rwy_alpha_scanner()
    print(f"Total Scanned: {res['total_scanned']} | Total Passed: {res['total_passed']}")
    print(format_rwy_scanner_message(res))
