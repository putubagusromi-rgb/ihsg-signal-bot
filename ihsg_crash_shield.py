"""
IHSG Crash Shield & Early Warning Circuit Breaker:
Modul Deteksi Dini Bahaya Sistemik & Koreksi Tajam IHSG
Tujuan:
1. Mencegah bot memberikan rekomendasi beli saat pasar dalam risiko crash (Cash is King).
2. Mengirimkan peringatan darurat ke Telegram dengan rincian data global & valas.
"""

from typing import Dict, Any, List
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
except Exception:
    WIB = None


def detect_ihsg_crash_shield() -> Dict[str, Any]:
    """
    Memeriksa 4 Sensor Utama Pasar sebelum Jam Pembukaan Bursa:
    1. Sensor Global Lead: EIDO semalam drop <= -2.0%
    2. Sensor Valas: Kurs Rupiah (USD/IDR) melonjak panik >= +0.7%
    3. Sensor Wall Street / Global Risk: S&P 500 (^GSPC) drop <= -1.8%
    4. Sensor Tren & Panik IHSG: IHSG di bawah SMA50 dan Drop 5D <= -2.5% atau Drop 1D <= -1.2%
    """
    tickers = ["^JKSE", "EIDO", "USDIDR=X", "^GSPC"]
    try:
        raw = yf.download(tickers, period="3mo", interval="1d", progress=False)
        if raw.empty:
            return {"active": False, "reasons": [], "status": "SAFE"}

        closes = raw["Close"]
        ihsg_c = closes["^JKSE"].dropna()
        eido_c = closes["EIDO"].dropna()
        idr_c = closes["USDIDR=X"].dropna()
        sp_c = closes["^GSPC"].dropna()

        if len(ihsg_c) < 25:
            return {"active": False, "reasons": [], "status": "SAFE"}

        # 1. Metrik IHSG
        curr_ihsg = float(ihsg_c.iloc[-1])
        prev_ihsg = float(ihsg_c.iloc[-2])
        ihsg_chg1d = ((curr_ihsg - prev_ihsg) / prev_ihsg) * 100
        p_5d = float(ihsg_c.iloc[-5]) if len(ihsg_c) >= 5 else prev_ihsg
        ihsg_chg5d = ((curr_ihsg - p_5d) / p_5d) * 100

        sma20 = float(ihsg_c.rolling(20).mean().iloc[-1])
        sma50 = float(ihsg_c.rolling(50).mean().iloc[-1]) if len(ihsg_c) >= 50 else sma20

        # 2. Metrik EIDO (Wall Street Overnight)
        eido_ret = float((eido_c.iloc[-1] - eido_c.iloc[-2]) / eido_c.iloc[-2]) * 100 if len(eido_c) >= 2 else 0.0

        # 3. Metrik Kurs Rupiah (USD/IDR)
        curr_idr = float(idr_c.iloc[-1]) if len(idr_c) >= 1 else 16000.0
        prev_idr = float(idr_c.iloc[-2]) if len(idr_c) >= 2 else curr_idr
        idr_chg1d = ((curr_idr - prev_idr) / prev_idr) * 100

        # 4. Metrik S&P 500
        sp_ret = float((sp_c.iloc[-1] - sp_c.iloc[-2]) / sp_c.iloc[-2]) * 100 if len(sp_c) >= 2 else 0.0

        # Evaluasi Pemicu Bahaya
        reasons = []

        # Pemicu 1: EIDO Drop Tajam (Asing Keluar Semalam di New York)
        if eido_ret <= -2.0:
            reasons.append(f"EIDO (MSCI Indonesia ETF) anjlok {eido_ret:.2f}% di Wall Street semalam (Sinyal Outflow Asing Masif)")

        # Pemicu 2: Kurs Rupiah Melemah Panik
        if idr_chg1d >= 0.70:
            reasons.append(f"Kurs Rupiah anjlok tajam +{idr_chg1d:.2f}% ke level Rp {curr_idr:,.0f} per USD (Pelemahan Valas Berbahaya)")

        # Pemicu 3: IHSG Breakdown di Bawah SMA50 + Panic Sell 5 Hari
        if curr_ihsg < sma50 and ihsg_chg5d <= -2.5:
            reasons.append(f"IHSG terkonfirmasi Breakdown di bawah SMA50 ({curr_ihsg:,.0f} < {sma50:,.0f}) dengan pelemahan 5 hari {ihsg_chg5d:.2f}%")

        # Pemicu 4: Drop 1 Hari Ekstrem (Flash Crash / Selloff)
        if ihsg_chg1d <= -1.4:
            reasons.append(f"IHSG mengalami koreksi tajam {ihsg_chg1d:.2f}% dalam 1 hari perdagangan terakhir")

        # Pemicu 5: Kombinasi Wall Street Drop + Pelemahan Rupiah
        if sp_ret <= -1.8 and idr_chg1d >= 0.40:
            reasons.append(f"Wall Street (S&P 500) anjlok {sp_ret:.2f}% bersamaan dengan tekanan nilai tukar Rupiah")

        is_crash_active = len(reasons) > 0

        severity = "AMAN"
        if len(reasons) >= 2 or ihsg_chg1d <= -2.0 or eido_ret <= -3.0:
            severity = "🚨 DARURAT CRASH (EXTREME DANGER)"
        elif is_crash_active:
            severity = "⚠️ WASPADA TINGGI (HIGH RISK-OFF)"

        return {
            "active": is_crash_active,
            "severity": severity,
            "reasons": reasons,
            "ihsg_price": curr_ihsg,
            "ihsg_chg1d": ihsg_chg1d,
            "ihsg_chg5d": ihsg_chg5d,
            "sma50": sma50,
            "eido_ret": eido_ret,
            "curr_idr": curr_idr,
            "idr_chg1d": idr_chg1d,
            "sp_ret": sp_ret
        }
    except Exception as e:
        print(f"[CrashShield Error] {e}")
        return {"active": False, "reasons": [], "status": "SAFE"}


def format_crash_shield_warning(shield: Dict[str, Any]) -> str:
    """Format pesan peringatan darurat untuk Telegram"""
    now = datetime.now(WIB) if WIB else datetime.now()
    date_str = now.strftime("%d %b %Y | %H:%M WIB")

    lines = [
        "🚨 <b>PERINGATAN DARURAT: IHSG CRASH SHIELD AKTIF!</b> 🛡️",
        f"📅 <i>Status Per: {date_str}</i>",
        f"🔴 <b>Level Risiko:</b> <b>{shield['severity']}</b>",
        "━━━━━━━━━━━━━━━━━━━",
        "⛔ <b>BOT MEMBEKUKAN SEMUA REKOMENDASI PEMBELIAN HARI INI!</b>",
        "",
        "<b>🔍 Indikator Bahaya Sistemik Terdeteksi:</b>"
    ]

    for idx, r in enumerate(shield.get("reasons", []), 1):
        lines.append(f"{idx}. ⚠️ <i>{r}</i>")

    lines.append("")
    lines.append(
        f"📊 <b>Snapshot Pasar Real-Time:</b>\n"
        f"• IHSG: <code>{shield['ihsg_price']:,.0f}</code> ({'+' if shield['ihsg_chg1d']>=0 else ''}{shield['ihsg_chg1d']:.2f}% 1D | {shield['ihsg_chg5d']:.2f}% 5D)\n"
        f"• EIDO (MSCI Indonesia US): <code>{'+' if shield['eido_ret']>=0 else ''}{shield['eido_ret']:.2f}%</code>\n"
        f"• Kurs USD/IDR: <code>Rp {shield['curr_idr']:,.0f}</code> ({'+' if shield['idr_chg1d']>=0 else ''}{shield['idr_chg1d']:.2f}%)\n"
        f"• S&amp;P 500: <code>{'+' if shield['sp_ret']>=0 else ''}{shield['sp_ret']:.2f}%</code>"
    )
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append(
        "💡 <b>PANDUAN PENYELAMATAN MODAL (CASH IS KING):</b>\n"
        "1. <b>DILARANG Menangkap Pisau Jatuh:</b> Jangan beli saham apa pun hari ini meskipun harganya terlihat 'murah'. Saham bagus akan tetap terseret kepanikan pasar.\n"
        "2. <b>Amankan Modal:</b> Jika Anda memiliki posisi saham yang sedang berjalan, segera pasang/ketatkan Trailing Stop.\n"
        "3. <b>Simpan Cash 100%:</b> Uang tunai adalah posisi terbaik saat badai berlangsung. Bot akan otomatis aktif merekomendasikan saham kembali begitu pasar stabil."
    )
    return "\n".join(lines)


if __name__ == "__main__":
    res = detect_ihsg_crash_shield()
    print("Status Crash Shield:", res)
    if res["active"]:
        print("\nPesan Warning:")
        print(format_crash_shield_warning(res))
    else:
        print("\nPasar saat ini aman (Crash Shield Tidak Aktif).")
