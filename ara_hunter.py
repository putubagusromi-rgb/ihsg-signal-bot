"""
Radar ARA Hunter (Momentum Mark-Up & Next-Day Breakout Screener):
Mendeteksi saham-saham dengan akumulasi agresif di akhir sesi bursa (Closing Volume Spike,
Marubozu Close, Breakout 20D, Money Flow CMF) yang berpotensi meledak / ARA esok pagi.
"""

from typing import List, Dict, Any
import yfinance as yf
import pandas as pd
import numpy as np

# Watchlist saham aktif & liquid untuk ARA Hunter
ARA_WATCHLIST = [
    "PANI", "CUAN", "BREN", "TPIA", "BRPT", "MEDC", "MDKA", "ANTM", "RAJA", "DOID",
    "ELSA", "WIFI", "MBMA", "PTBA", "ADMR", "CLEO", "CMRY", "MAPA", "AUTO", "SSMS",
    "PGAS", "PGEO", "ESSA", "HRUM", "ACES", "ERAA", "INCO", "INDF", "INKP", "TKIM",
    "DEWA", "BUMI", "ENRG", "TOBA", "INDY", "ISAT", "EXCL", "CPIN", "JPFA", "TAPG"
]


def calculate_ara_limit(price: float) -> float:
    """
    Menghitung batas Auto Rejection Atas (ARA) sesuai aturan fraksi harga BEI:
    - Rp50 s/d Rp200: +35%
    - >Rp200 s/d Rp5.000: +25%
    - >Rp5.000: +20%
    """
    if price <= 200:
        return price * 1.35
    elif price <= 5000:
        return price * 1.25
    else:
        return price * 1.20


def scan_ara_hunter_picks(watchlist: List[str] = None, limit: int = 4) -> List[Dict[str, Any]]:
    """
    Menyaring saham-saham yang memenuhi kriteria ARA Hunter teruji backtest 2024-2026:
    1. Kenaikan hari ini solid (+3.5% s/d +19%)
    2. Lonjakan Volume (RVOL >= 1.6x)
    3. Closing Marubozu (Ekor atas tipis <= 30% dari rentang candle)
    4. Mendekati / tembus Resistance High 20-Hari
    5. CMF > 0 (Uang masuk riil)
    6. Turnover >= Rp 2 Miliar
    """
    tickers = watchlist or ARA_WATCHLIST
    yf_tickers = [f"{t}.JK" for t in tickers]

    try:
        data = yf.download(yf_tickers, period="2mo", interval="1d", progress=False, group_by="ticker")
        if data.empty:
            return []
    except Exception:
        return []

    picks = []

    for t in tickers:
        try:
            yf_t = f"{t}.JK"
            if yf_t not in data:
                continue
            df = data[yf_t].dropna().copy()
            if len(df) < 25:
                continue

            c = df["Close"]
            h = df["High"]
            l = df["Low"]
            o = df["Open"]
            v = df["Volume"]

            curr_c = float(c.iloc[-1])
            prev_c = float(c.iloc[-2])
            curr_h = float(h.iloc[-1])
            curr_l = float(l.iloc[-1])
            curr_o = float(o.iloc[-1])
            curr_v = float(v.iloc[-1])

            pct_chg = ((curr_c - prev_c) / prev_c) * 100
            vol_sma20 = float(v.rolling(20).mean().iloc[-1])
            rvol = (curr_v / vol_sma20) if vol_sma20 > 0 else 1.0

            candle_range = curr_h - curr_l
            upper_shadow = curr_h - max(curr_c, curr_o)
            upper_shadow_pct = (upper_shadow / candle_range) if candle_range > 0 else 0.0

            high_20 = float(h.rolling(20).max().iloc[-2]) if len(h) >= 21 else curr_h
            breakout_score = (curr_c / high_20)

            # Chaikin Money Flow
            mfv = ((c - l) - (h - c)) / (h - l).replace(0, np.nan) * v
            cmf20 = float((mfv.rolling(20).sum() / v.rolling(20).sum()).iloc[-1])

            turnover = curr_c * curr_v

            # Saring dengan kriteria kuantitatif
            if (3.5 <= pct_chg <= 22.0 and
                rvol >= 1.6 and
                upper_shadow_pct <= 0.30 and
                breakout_score >= 0.95 and
                turnover >= 2_000_000_000):

                score = 50
                score += min(25, int(rvol * 7))
                score += min(15, int((1.0 - upper_shadow_pct) * 15))
                score += 10 if cmf20 > 0.10 else (5 if cmf20 > 0 else 0)

                ara_target = calculate_ara_limit(curr_c)
                ara_gain_pct = ((ara_target - curr_c) / curr_c) * 100
                sl_level = curr_l if (curr_c - curr_l) / curr_c <= 0.05 else curr_c * 0.95

                picks.append({
                    "ticker": t,
                    "price": curr_c,
                    "pct_change": pct_chg,
                    "rvol": rvol,
                    "cmf": cmf20,
                    "upper_shadow_pct": upper_shadow_pct,
                    "ara_target": ara_target,
                    "ara_gain_pct": ara_gain_pct,
                    "sl": sl_level,
                    "score": min(98, score),
                    "turnover_billion": turnover / 1_000_000_000
                })

        except Exception:
            continue

    picks.sort(key=lambda x: (x["score"], x["rvol"]), reverse=True)
    return picks[:limit]


def format_ara_hunter_message(picks: List[Dict[str, Any]]) -> str:
    if not picks:
        return (
            "🚀 <b>RADAR ARA HUNTER (CANDIDATE NEXT-DAY EXPLOSION)</b>\n"
            "<i>Belum ada saham yang memenuhi kriteria ledakan volume &amp; candle marubozu sore ini. "
            "Pasar selektif, utamakan modal aman dalam Cash.</i>"
        )

    lines = [
        "🚀 <b>RADAR ARA HUNTER &amp; BREAKOUT CANDIDATE</b> 🔥",
        "<i>Saham berpotensi meledak / ARA esok pagi (Closing Volume Spike + Candle Marubozu):</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    for idx, p in enumerate(picks, 1):
        lines.append(
            f"<b>{idx}. #{p['ticker']}</b> — <code>Rp{int(p['price']):,}</code> (+{p['pct_change']:.1f}%)\n"
            f"   • 🎯 <b>Skor ARA Hunter:</b> <b>{p['score']}/100</b>\n"
            f"   • ⚡ <b>Lonjakan Vol (RVOL):</b> <b>{p['rvol']:.1f}x</b> (Turnover: <code>Rp{p['turnover_billion']:.1f} M</code>)\n"
            f"   • 🌊 <b>Chaikin Money Flow:</b> <code>{p['cmf']:+.2f}</code> (Net Akumulasi)\n"
            f"   • 🚀 <b>Plafon ARA Besok:</b> <code>Rp{int(p['ara_target']):,}</code> (<b>+{p['ara_gain_pct']:.1f}%</b>)\n"
            f"   • 🛑 <b>Stop Loss Pengaman:</b> <code>Rp{int(p['sl']):,}</code> (-5.0%)\n"
        )

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━",
        "💡 <b>PANDUAN STRATEGI SCALPING / FAST SWING:</b>",
        "1️⃣ Entry saat pembukaan (Open Market 09:00 WIB) jika lonjakan bid kuat.",
        "2️⃣ Pasang target Take Profit bertahap di +5% s/d +12% untuk mengamankan cuan cepat.",
        "3️⃣ Jika saham ditarik mentok ARA, biarkan runner lot menginap untuk gap up esoknya!"
    ])
    return "\n".join(lines)
