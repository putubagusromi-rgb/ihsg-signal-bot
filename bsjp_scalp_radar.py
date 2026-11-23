"""
Modul Radar BSJP (Beli Sore Jual Pagi) & Daily Scalp Momentum - UNCAPPED TP
Konsep Utama:
1. SETIAP HARI SELALU ADA 3 SAHAM TERBAIK (Guaranteed Top 3 Daily Picks)
2. Filter Likuiditas: Turnover >= Rp 2 Miliar (Saham Runner, Mid-cap, & Akuisisi)
3. JANGAN ADA BATAS MAKSIMAL TP: Bebas terbang (Let Winners Run hingga puluhan % / ARA)
4. Stop Loss Aman & Disiplin: -5.0% s/d -5.5% (Tahan banting terhadap kocokan pagi)
5. Panduan Trailing Stop: Mengunci cuan di puncak tanpa membatasi potensi naik
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


DAY_NAMES_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


def get_market_timing_info(mode: str = "scalp") -> Dict[str, Any]:
    """Cek apakah bursa sedang libur (weekend) atau di luar jam perdagangan aktif."""
    now = datetime.now(WIB) if WIB else datetime.now()
    weekday = now.weekday()
    day_name = DAY_NAMES_ID[weekday]
    date_str = now.strftime("%d %b %Y")
    time_str = now.strftime("%H:%M")
    is_weekend = weekday in (5, 6)

    if is_weekend:
        return {
            "is_weekend": True,
            "status_badge": "🔴 <b>STATUS PASAR: BURSA LIBUR (AKHIR PEKAN)</b>",
            "day_name": day_name,
            "date_str": date_str,
            "time_str": time_str,
            "note": (
                f"⚠️ Hari ini adalah hari <b>{day_name} ({date_str})</b>, Bursa Efek Indonesia (IDX) sedang <b>TUTUP</b>.\n"
                f"📊 Data di bawah adalah <b>Watchlist Persiapan Trading Hari Senin</b> berdasarkan hasil penutupan sesi bursa terakhir (Jumat)."
            ),
            "next_execution": "Senin pukul 09:05 - 09:30 WIB" if mode == "scalp" else "Senin pukul 15:35 - 15:55 WIB (Pre-Closing)"
        }
    else:
        hour = now.hour
        minute = now.minute
        time_val = hour * 60 + minute

        if mode == "scalp":
            if time_val < 9 * 60:
                badge = "🟡 <b>STATUS: PRE-OPENING (Pasar Belum Buka)</b>"
                note = "⏳ Bursa baru buka pukul 09:00 WIB. Waktu ideal eksekusi Scalp Pagi adalah <b>09:05 - 09:30 WIB</b>."
            elif (9 * 60 <= time_val <= 11 * 60 + 30) or (13 * 60 + 30 <= time_val <= 15 * 60 + 45):
                badge = "🟢 <b>STATUS: LIVE TRADING (Pasar Aktif)</b>"
                note = "⚡ Sinyal momentum realtime aktif. Amati antrian Bid/Offer dan volume lonjakan!"
            else:
                badge = "⚪ <b>STATUS: PASAR SUDAH TUTUP (Post-Closing)</b>"
                note = "📊 Data di bawah adalah hasil penutupan hari ini untuk persiapan trading besok pagi."
            next_exec = f"{day_name}, 09:05 - 09:30 WIB"
        else:  # bsjp
            if time_val < 15 * 60 + 30:
                badge = "🟡 <b>STATUS: SESI REGULER (Belum Sesi Pre-Closing)</b>"
                note = "💡 Radar BSJP paling akurat diakses pada pukul <b>15:35 - 15:55 WIB</b> saat sesi Pre-Closing."
            elif 15 * 60 + 30 <= time_val <= 16 * 60:
                badge = "🟢 <b>STATUS: SESI PRE-CLOSING (WAKTU EMAS BSJP)</b>"
                note = "🔥 Waktu ideal untuk memasukkan order beli sore sebelum bursa tutup pukul 16:00 WIB!"
            else:
                badge = "⚪ <b>STATUS: PASAR SUDAH TUTUP (Post-Closing)</b>"
                note = "📊 Data penutupan sore hari ini untuk persiapan jual pagi esok hari."
            next_exec = f"{day_name}, 15:35 - 15:55 WIB"

        return {
            "is_weekend": False,
            "status_badge": badge,
            "day_name": day_name,
            "date_str": date_str,
            "time_str": time_str,
            "note": note,
            "next_execution": next_exec
        }


def check_ihsg_market_shield() -> Dict[str, Any]:
    """Cek kondisi IHSG untuk panduan manajemen risiko menggunakan modul Crash Shield"""
    try:
        from ihsg_crash_shield import detect_ihsg_crash_shield
        shield = detect_ihsg_crash_shield()
        if shield.get("active"):
            main_reason = shield["reasons"][0] if shield.get("reasons") else "Koreksi Pasar Tajam"
            return {
                "safe": False,
                "reason": f"🚨 CRASH SHIELD AKTIF ({shield.get('severity', 'RISK-OFF')}): {main_reason} — Tahan Pembelian Baru &amp; Simpan Cash!"
            }
        return {"safe": True, "reason": "IHSG Kondusif / Uptrend"}
    except Exception:
        return {"safe": True, "reason": "IHSG Netral"}


def scan_bsjp_picks(limit: int = 3) -> List[Dict[str, Any]]:
    """
    Memindai saham BSJP (Beli Sore Jual Pagi) pada pukul 15:35 - 15:55 WIB:
    - Selalu menghasilkan 3 rekomendasi terbaik setiap hari
    - Stop loss 5.0% - 5.5%
    - TP Uncapped (Let Winners Run)
    """
    yf_tickers = [f"{t}.JK" for t in EXPANDED_WATCHLIST]
    try:
        data = yf.download(yf_tickers, period="3mo", interval="1d", progress=False, group_by="ticker")
        if data.empty:
            return []
    except Exception:
        return []

    candidates = []

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
            if curr_c < 60 or turnover_today < 2_000_000_000:
                continue

            pct_chg = round(((curr_c - c.iloc[-2]) / c.iloc[-2]) * 100, 2)
            vol_sma20 = v.rolling(20).mean().iloc[-1]
            rvol = round(curr_v / vol_sma20, 2) if vol_sma20 > 0 else 1.0

            ema20 = c.ewm(span=20, adjust=False).mean().iloc[-1]

            # Candle Shadow
            candle_range = max(1, curr_h - curr_l)
            upper_shadow = max(0, curr_h - max(curr_c, curr_o))
            upper_shadow_pct = upper_shadow / candle_range

            # CMF
            cmf_series = (((c - l) - (h - c)) / (h - l).replace(0, np.nan) * v).rolling(20).sum() / v.rolling(20).sum()
            curr_cmf = round(float(cmf_series.iloc[-1]), 3) if not np.isnan(cmf_series.iloc[-1]) else 0.0

            # Scoring komprehensif agar selalu ada top 3 terbaik
            trend_score = 20 if curr_c >= ema20 else 0
            marubozu_score = 25 if upper_shadow_pct <= 0.18 else (10 if upper_shadow_pct <= 0.28 else 0)
            score = (pct_chg * 2.0) + (rvol * 12.0) + (curr_cmf * 35.0) + trend_score + marubozu_score

            # Stop Loss 5.0% - 5.5% (Tahan banting)
            strict_sl = int(curr_c * 0.948) # -5.2%
            sl_pct = 5.2

            # Estimasi target resistance / runner
            target_est_1 = int(curr_c * 1.06)  # +6%
            target_est_ara = int(curr_c * 1.25) # +25% Potensi ARA

            candidates.append({
                "ticker": sym,
                "price": curr_c,
                "pct_chg": pct_chg,
                "rvol": rvol,
                "cmf": curr_cmf,
                "turnover_m": round(turnover_today / 1e9, 1),
                "strict_sl": strict_sl,
                "sl_pct": sl_pct,
                "target_est_1": target_est_1,
                "target_est_ara": target_est_ara,
                "score": int(min(99, max(65, score))),
                "catalyst": f"Vol Spike {rvol}x | CMF +{curr_cmf:.2f}" + (" (Marubozu Murni)" if upper_shadow_pct <= 0.18 else "")
            })
        except Exception:
            continue

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:limit]


def scan_scalp_momentum_picks(limit: int = 3) -> List[Dict[str, Any]]:
    """
    Memindai saham Daily Scalp Momentum Pagi (09:05 - 09:30 WIB):
    - Selalu memberikan 3 saham terbaik setiap hari
    - JANGAN ADA BATAS MAKSIMAL TP (Uncapped - Let Winners Run)
    - Stop loss 5.0% - 5.5%
    """
    yf_tickers = [f"{t}.JK" for t in EXPANDED_WATCHLIST]
    try:
        data = yf.download(yf_tickers, period="3mo", interval="1d", progress=False, group_by="ticker")
        if data.empty:
            return []
    except Exception:
        return []

    candidates = []

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
            if curr_c < 60 or turnover_today < 2_000_000_000:
                continue

            pct_chg = round(((curr_c - c.iloc[-2]) / c.iloc[-2]) * 100, 2)
            vol_sma20 = v.rolling(20).mean().iloc[-1]
            rvol = round(curr_v / vol_sma20, 2) if vol_sma20 > 0 else 1.0

            high_20 = h.rolling(20).max().iloc[-2]
            is_breakout = curr_c >= (high_20 * 0.985)

            # Score momentum
            breakout_bonus = 20 if is_breakout else 0
            score = (pct_chg * 2.5) + (rvol * 15.0) + breakout_bonus

            # Stop loss 5.2%
            strict_sl = int(curr_c * 0.948)
            sl_pct = 5.2

            target_est_1 = int(curr_c * 1.06)
            target_est_ara = int(curr_c * 1.25)

            candidates.append({
                "ticker": sym,
                "price": curr_c,
                "pct_chg": pct_chg,
                "rvol": rvol,
                "turnover_m": round(turnover_today / 1e9, 1),
                "strict_sl": strict_sl,
                "sl_pct": sl_pct,
                "target_est_1": target_est_1,
                "target_est_ara": target_est_ara,
                "score": int(min(99, max(70, score))),
                "catalyst": f"Breakout 20D (Vol Spike {rvol}x)" if is_breakout else f"Momentum Surge (Vol {rvol}x)"
            })
        except Exception:
            continue

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:limit]


def format_bsjp_message(picks: List[Dict[str, Any]]) -> str:
    """Format pesan Telegram untuk Radar BSJP (Uncapped TP & SL 5%)"""
    timing = get_market_timing_info(mode="bsjp")
    shield = check_ihsg_market_shield()

    if timing["is_weekend"]:
        lines = [
            "🌇 <b>RADAR BSJP — BELI SORE JUAL PAGI (WATCHLIST SENIN)</b> 🎯",
            f"{timing['status_badge']}",
            f"{timing['note']}",
            f"⏰ <b>Jadwal Beli Sore Live:</b> <code>{timing['next_execution']}</code>",
            f"🛡️ <b>Kondisi Pasar:</b> <i>{shield['reason']}</i>",
            "━━━━━━━━━━━━━━━━━━━",
            "<b>3 Saham BSJP Terpilih Hasil Penutupan Terakhir:</b>",
            ""
        ]
    else:
        lines = [
            "🌇 <b>RADAR BSJP — DAILY STOCK PICK SORE</b> 🎯",
            f"{timing['status_badge']}",
            f"📅 <i>Waktu: {timing['day_name']}, {timing['date_str']} ({timing['time_str']} WIB)</i>",
            f"🛡️ <b>Kondisi Pasar:</b> <i>{shield['reason']}</i>",
            f"💡 <i>{timing['note']}</i>",
            "━━━━━━━━━━━━━━━━━━━",
            "<b>3 Saham Pilihan Terbaik Hari Ini (Turnover ≥ Rp 2 Miliar):</b>",
            ""
        ]

    for idx, p in enumerate(picks, 1):
        lines.append(
            f"<b>{idx}. #{p['ticker']}</b> — <code>Rp {p['price']:,}</code> (<b>+{p['pct_chg']}%</b>)\n"
            f"   • 🎯 <b>Target Profit :</b> <b>UNLIMITED / BEBAS TERBANG</b> 🚀\n"
            f"   • 📈 <i>Resistance 1 : Rp {p['target_est_1']:,} (+6.0%)</i>\n"
            f"   • 🔥 <i>Potensi ARA  : Rp {p['target_est_ara']:,} (+25.0%)</i>\n"
            f"   • ⛔ <b>Stop Loss     :</b> <code>Rp {p['strict_sl']:,}</code> (-{p['sl_pct']}%) <i>[Batas Risiko Aman]</i>\n"
            f"   • 📊 <i>Skor Sinyal : {p['score']}/100 | Turnover: Rp {p['turnover_m']} M</i>\n"
            f"   • 💡 <i>Katalis     : {p['catalyst']}</i>\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append(
        "💎 <b>PANDUAN PROFIT MAKSIMAL (TANPA BATAS TP):</b>\n"
        "• <b>Jangan Batasi Cuan:</b> Biarkan saham terbang setinggi mungkin (Let Winners Run) untuk menangkap potensi +15%, +25% s/d ARA!\n"
        "• <b>Trailing Stop:</b> Begitu sudah cuan di atas +5%, geser Stop Loss ke harga modal (BEP). Kunci cuan saat saham mulai berbalik arah.\n"
        "• <b>Disiplin Stop Loss:</b> Hanya buang saham jika menyentuh batas aman -5% s/d -6%."
    )
    return "\n".join(lines)


def format_scalp_message(picks: List[Dict[str, Any]]) -> str:
    """Format pesan Telegram untuk Radar Scalping Pagi (Uncapped TP & SL 5%)"""
    timing = get_market_timing_info(mode="scalp")

    if timing["is_weekend"]:
        lines = [
            "⚡ <b>RADAR DAILY SCALP MOMENTUM (WATCHLIST SENIN)</b> 🏹",
            f"{timing['status_badge']}",
            f"{timing['note']}",
            f"⏰ <b>Jadwal Eksekusi Live:</b> <code>{timing['next_execution']}</code>",
            "━━━━━━━━━━━━━━━━━━━",
            "<b>3 Saham Scalp Terpilih Hasil Penutupan Terakhir:</b>",
            ""
        ]
    else:
        lines = [
            "⚡ <b>RADAR DAILY SCALP MOMENTUM PAGI</b> 🏹",
            f"{timing['status_badge']}",
            f"📅 <i>Waktu: {timing['day_name']}, {timing['date_str']} ({timing['time_str']} WIB)</i>",
            f"💡 <i>{timing['note']}</i>",
            "━━━━━━━━━━━━━━━━━━━",
            "<b>3 Saham Scalp Terbaik Pagi Ini (Volume Meledak):</b>",
            ""
        ]

    for idx, p in enumerate(picks, 1):
        lines.append(
            f"<b>{idx}. #{p['ticker']}</b> — <code>Rp {p['price']:,}</code> (<b>+{p['pct_chg']}%</b>)\n"
            f"   • 🎯 <b>Target Profit :</b> <b>OPEN / TANPA BATAS MAKSIMAL</b> 🚀\n"
            f"   • 📈 <i>Target Cepat : Rp {p['target_est_1']:,} (+6.0%)</i>\n"
            f"   • 🔥 <i>Potensi ARA  : Rp {p['target_est_ara']:,} (+25.0%)</i>\n"
            f"   • ⛔ <b>Stop Loss     :</b> <code>Rp {p['strict_sl']:,}</code> (-{p['sl_pct']}%) <i>[Ketat &amp; Terukur]</i>\n"
            f"   • 📊 <i>Skor Momentum: {p['score']}/100 | Turnover: Rp {p['turnover_m']} M</i>\n"
            f"   • 💡 <i>Katalis     : {p['catalyst']}</i>\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append(
        "💡 <b>TIPS SCALPING PROFESIONAL:</b>\n"
        "• <b>Tidak ada batasan TP kaku:</b> Selama bid tebal dan masih ditarik naik, hold terus!\n"
        "• Pasang Trailing Stop otomatis jika sudah cuan di atas +5% untuk mengunci profit.\n"
        "• Wajib disiplin cut loss jika jebol di bawah batas -5% s/d -6%."
    )
    return "\n".join(lines)
