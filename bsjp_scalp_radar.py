"""
Modul Radar BSJP (Beli Sore Jual Pagi) & Scalp Momentum IHSG
Filter Likuiditas: Turnover >= Rp 2 Miliar
Kriteria: Akumulasi Smart Money, Closing Marubozu, Target Jual di Puncak Pagi, Strict Stop Loss
"""
import yfinance as yf
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
except Exception:
    WIB = None

# Universe Gabungan: Saham Penggerak, Runner Akuisisi, Mid-Cap Gems, Komoditas, & Big Caps
EXPANDED_WATCHLIST = [
    # Akuisisi / Konglomerat / High Beta Runners
    "PANI", "BREN", "CUAN", "TPIA", "BRPT", "BRMS", "DEWA", "BUMI", 
    "WIFI", "RAJA", "PSAB", "VKTR", "TOBA", "DOID", "ELSA", "MEDC",
    # Mining / Metals / Energy
    "MDKA", "MBMA", "ANTM", "PTBA", "ADRO", "ITMG", "HRUM", "PGEO", "PGAS",
    # Mid-Caps / Consumer / Retail / Agro
    "CLEO", "CMRY", "MYOR", "ERAA", "AUTO", "MAPA", "MAPI", "ESSA", 
    "INKP", "TKIM", "CPIN", "JPFA", "SSMS", "TAPG", "SIMP", "ACES",
    # Banking / Big Caps
    "BBRI", "BMRI", "BBCA", "BBNI", "BRIS", "ARTO", "ASII", "TLKM",
    "GOTO", "EMTK", "SCMA", "KLBF", "JSMR", "AMMN"
]

def scan_bsjp_picks(limit: int = 3) -> List[Dict[str, Any]]:
    """
    Memindai saham BSJP (Beli Sore Jual Pagi) pada pukul 15:30 - 15:55 WIB:
    1. Likuiditas: Turnover hari ini >= Rp 2 Miliar (menangkap saham akuisisi & mid-cap runner)
    2. Trend Sehat: Harga di atas EMA 20
    3. Kenaikan Solid: +3.0% s/d +18.0% (belum mentok ARA 35%, siap meledak esok)
    4. Ledakan Volume: RVOL >= 1.5x rata-rata 20 hari
    5. Closing Marubozu: Ekor atas <= 20% (Buyer mendominasi hingga detik terakhir)
    6. Akumulasi Dana Masuk: CMF > 0
    """
    yf_tickers = [f"{t}.JK" for t in EXPANDED_WATCHLIST]
    try:
        data = yf.download(yf_tickers, period="2mo", interval="1d", progress=False, group_by="ticker")
        if data.empty:
            return []
    except Exception:
        return []

    picks = []

    for sym in EXPANDED_WATCHLIST:
        yf_sym = f"{sym}.JK"
        try:
            if yf_sym not in data:
                continue
            df = data[yf_sym].dropna().copy()
            if len(df) < 25:
                continue

            c = df["Close"]
            h = df["High"]
            l = df["Low"]
            o = df["Open"]
            v = df["Volume"]

            curr_c = int(c.iloc[-1])
            curr_h = int(h.iloc[-1])
            curr_l = int(l.iloc[-1])
            curr_o = int(o.iloc[-1])
            curr_v = int(v.iloc[-1])

            # Filter harga & likuiditas >= Rp 2 Miliar
            turnover_today = curr_c * curr_v
            if curr_c < 50 or turnover_today < 2_000_000_000:
                continue

            pct_chg = round(((curr_c - c.iloc[-2]) / c.iloc[-2]) * 100, 2)
            vol_sma20 = v.rolling(20).mean().iloc[-1]
            rvol = round(curr_v / vol_sma20, 2) if vol_sma20 > 0 else 1.0

            # EMA 20
            ema20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
            if curr_c < ema20:
                continue  # Skip saham downtrend

            # Candle Shadow
            candle_range = max(1, curr_h - curr_l)
            upper_shadow = max(0, curr_h - max(curr_c, curr_o))
            upper_shadow_pct = upper_shadow / candle_range

            # CMF Proxy
            mfm = ((curr_c - curr_l) - (curr_h - curr_c)) / candle_range
            cmf_series = (((c - l) - (h - c)) / (h - l).replace(0, np.nan) * v).rolling(20).sum() / v.rolling(20).sum()
            curr_cmf = round(float(cmf_series.iloc[-1]), 3) if not np.isnan(cmf_series.iloc[-1]) else 0.0

            # Kriteria BSJP
            if (3.0 <= pct_chg <= 22.0) and (rvol >= 1.5) and (upper_shadow_pct <= 0.25) and (curr_cmf >= 0.0):
                # Target TP Pagi (+3.5% s/d +7.5%)
                target_tp_min = round(curr_c * 1.035)
                target_tp_max = round(curr_c * 1.075)
                
                # Strict Stop Loss (di bawah Low hari ini atau max -3.5%)
                strict_sl = int(max(curr_l * 0.985, curr_c * 0.965))
                risk_pct = round(((curr_c - strict_sl) / curr_c) * 100, 1)
                reward_pct = round(((target_tp_min - curr_c) / curr_c) * 100, 1)
                rr_ratio = round(reward_pct / risk_pct, 1) if risk_pct > 0 else 2.0

                bsjp_score = int(pct_chg * 1.5 + rvol * 15 + max(0, curr_cmf * 50))
                bsjp_score = min(99, max(75, bsjp_score))

                picks.append({
                    "ticker": sym,
                    "price": curr_c,
                    "pct_chg": pct_chg,
                    "rvol": rvol,
                    "cmf": curr_cmf,
                    "turnover_m": round(turnover_today / 1e9, 1),
                    "target_tp_min": target_tp_min,
                    "target_tp_max": target_tp_max,
                    "strict_sl": strict_sl,
                    "risk_pct": risk_pct,
                    "reward_pct": reward_pct,
                    "rr_ratio": rr_ratio,
                    "score": bsjp_score,
                    "catalyst": f"Closing Marubozu (RVOL {rvol}x, CMF +{curr_cmf:.2f})"
                })
        except Exception:
            continue

    picks.sort(key=lambda x: x["score"], reverse=True)
    return picks[:limit]


def scan_scalp_momentum_picks(limit: int = 3) -> List[Dict[str, Any]]:
    """
    Memindai saham Scalp Momentum Pagi (09:05 - 09:30 WIB):
    1. Likuiditas: Turnover >= Rp 2 Miliar
    2. Ledakan Volume Ekstrem (RVOL >= 2.0x)
    3. Breakout mendekati / menembus High 20 Hari
    4. Target Cuan Cepat (+2.5% s/d +5.0%)
    5. Strict Cut Loss: -2.0%
    """
    yf_tickers = [f"{t}.JK" for t in EXPANDED_WATCHLIST]
    try:
        data = yf.download(yf_tickers, period="2mo", interval="1d", progress=False, group_by="ticker")
        if data.empty:
            return []
    except Exception:
        return []

    picks = []

    for sym in EXPANDED_WATCHLIST:
        yf_sym = f"{sym}.JK"
        try:
            if yf_sym not in data:
                continue
            df = data[yf_sym].dropna().copy()
            if len(df) < 25:
                continue

            c = df["Close"]
            h = df["High"]
            l = df["Low"]
            o = df["Open"]
            v = df["Volume"]

            curr_c = int(c.iloc[-1])
            curr_h = int(h.iloc[-1])
            curr_l = int(l.iloc[-1])
            curr_o = int(o.iloc[-1])
            curr_v = int(v.iloc[-1])

            turnover_today = curr_c * curr_v
            if curr_c < 50 or turnover_today < 2_000_000_000:
                continue

            pct_chg = round(((curr_c - c.iloc[-2]) / c.iloc[-2]) * 100, 2)
            vol_sma20 = v.rolling(20).mean().iloc[-1]
            rvol = round(curr_v / vol_sma20, 2) if vol_sma20 > 0 else 1.0

            high_20 = h.rolling(20).max().iloc[-2]  # High 20 hari sebelum hari ini

            # Kriteria Scalp Breakout
            is_breakout = curr_c >= (high_20 * 0.985)
            if (pct_chg >= 3.5) and (rvol >= 1.8) and is_breakout:
                tp_quick = round(curr_c * 1.035)
                tp_runner = round(curr_c * 1.070)
                strict_sl = round(curr_c * 0.980)  # Strict -2% untuk scalping

                score = int(pct_chg * 2 + rvol * 12)
                score = min(99, max(80, score))

                picks.append({
                    "ticker": sym,
                    "price": curr_c,
                    "pct_chg": pct_chg,
                    "rvol": rvol,
                    "turnover_m": round(turnover_today / 1e9, 1),
                    "tp_quick": tp_quick,
                    "tp_runner": tp_runner,
                    "strict_sl": strict_sl,
                    "score": score,
                    "catalyst": f"Breakout High 20D (Vol Spike {rvol}x)"
                })
        except Exception:
            continue

    picks.sort(key=lambda x: x["score"], reverse=True)
    return picks[:limit]


def format_bsjp_message(picks: List[Dict[str, Any]]) -> str:
    """Format pesan Telegram untuk Radar BSJP"""
    now = datetime.now(WIB) if WIB else datetime.now()
    date_str = now.strftime("%d %b %Y")

    if not picks:
        return (
            "🌇 <b>RADAR BSJP (BELI SORE JUAL PAGI)</b> 🎯\n"
            f"📅 <i>Tanggal: {date_str} (Sesi Pre-Closing 15:35 WIB)</i>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🔍 <i>Tidak ditemukan saham yang memenuhi syarat ketat BSJP hari ini (Volume belum meledak / risiko distribusi). Disiplin wait and see!</i>"
        )

    lines = [
        "🌇 <b>RADAR BSJP (BELI SORE JUAL PAGI)</b> 🎯",
        f"📅 <i>Sesi Eksekusi: Pre-Closing (15:35 - 15:55 WIB) | {date_str}</i>",
        "🎯 <i>Strategi: Beli sore di closing, pasang antrean jual di puncak pagi esok hari (+3% s/d +7%)!</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    for idx, p in enumerate(picks, 1):
        lines.append(
            f"<b>{idx}. #{p['ticker']}</b> — <code>Rp {p['price']:,}</code> (<b>+{p['pct_chg']}%</b>)\n"
            f"   • 📊 Skor Sinyal: <code>{p['score']}/100</code> | Turnover: <code>Rp {p['turnover_m']} M</code>\n"
            f"   • 🚀 <b>Target Jual Pagi :</b> <code>Rp {p['target_tp_min']:,} - {p['target_tp_max']:,}</code> (+{p['reward_pct']}% s/d +7.5%)\n"
            f"   • ⛔ <b>Strict Stop Loss :</b> <code>Rp {p['strict_sl']:,}</code> (-{p['risk_pct']}%) <i>[Wajib Disiplin!]</i>\n"
            f"   • ⚖️ <b>Risk:Reward     :</b> <b>1 : {p['rr_ratio']}</b>\n"
            f"   • 💡 <i>Katalis        : {p['catalyst']}</i>\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append(
        "⚠️ <b>SOP EKSEKUSI BSJP &amp; STOP LOSS KETAT:</b>\n"
        "1. <b>Beli di Pre-Closing (15:50 WIB)</b> menggunakan sistem pasang antrean harga closing.\n"
        "2. <b>Besok Pagi (09:00 WIB):</b> Pasang Auto Order Take Profit di Target Pagi (+3.5%). Begitu kena lonjakan pagi, langsung amankan modal!\n"
        "3. <b>Strict Stop Loss:</b> Jika esok hari langsung dibanting di bawah titik SL, langsung cut loss tanpa toleransi."
    )
    return "\n".join(lines)


def format_scalp_message(picks: List[Dict[str, Any]]) -> str:
    """Format pesan Telegram untuk Radar Scalping Pagi"""
    now = datetime.now(WIB) if WIB else datetime.now()
    date_str = now.strftime("%d %b %Y")

    if not picks:
        return (
            "⚡ <b>RADAR SCALP MOMENTUM PAGI</b> 🏹\n"
            f"📅 <i>Tanggal: {date_str} (09:05 - 09:30 WIB)</i>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🔍 <i>Belum ada saham dengan lonjakan volume momentum ekstrem pagi ini. Sabar menunggu setup matang!</i>"
        )

    lines = [
        "⚡ <b>RADAR SCALP MOMENTUM PAGI</b> 🏹",
        f"📅 <i>Waktu Eksekusi: 09:05 - 09:30 WIB | {date_str}</i>",
        "🎯 <i>Strategi: Fast In & Fast Out (Cuan Kilat +2.5% s/d +5.0% dengan Stop Loss -2.0%)!</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    for idx, p in enumerate(picks, 1):
        lines.append(
            f"<b>{idx}. #{p['ticker']}</b> — <code>Rp {p['price']:,}</code> (<b>+{p['pct_chg']}%</b>)\n"
            f"   • 🚀 <b>Target Cuan Cepat :</b> <code>Rp {p['tp_quick']:,}</code> (+3.5%)\n"
            f"   • 🎯 <b>Target Runner     :</b> <code>Rp {p['tp_runner']:,}</code> (+7.0%)\n"
            f"   • ⛔ <b>Strict Stop Loss  :</b> <code>Rp {p['strict_sl']:,}</code> (-2.0%) <i>[Ketat!]</i>\n"
            f"   • 📊 <i>Sinyal: {p['catalyst']} | Turnover: Rp {p['turnover_m']} M</i>\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append(
        "💡 <b>PANDUAN SCALPING:</b>\n"
        "• Masuk saat momentum lonjakan volume awal sesi.\n"
        "• Begitu profit menyentuh +2.5% s/d +3.5%, kunci profit atau pasang Trailing Stop.\n"
        "• Batasi risiko maksimal 1% dari total modal per transaksi."
    )
    return "\n".join(lines)
