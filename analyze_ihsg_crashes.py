"""
Studi Forensik Crash IHSG (2020 - 2026):
Menganalisis setiap peristiwa kejatuhan / koreksi dalam IHSG:
1. Crash COVID-19 (Feb - Mar 2020)
2. Crash Tightening / Inflasi Global (Mei 2022)
3. Koreksi Tajam Silicon Valley Bank / US Regional Banking (Mar 2023)
4. Geopolitik & Rupiah 16.000+ (Apr - Jun 2024)
5. Black Monday Yen Carry Trade Unwind (Agt 2024)
6. Outflow Trump Election / DXY Surge (Okt - Nov 2024)

Mengukur metrik kuantitatif:
- Perubahan IHSG 1-hari & 5-hari
- Posisi terhadap SMA20, SMA50, SMA200
- Return EIDO semalam
- Pergerakan USD/IDR
- Return S&P 500 (^GSPC)
"""

import yfinance as yf
import pandas as pd
import numpy as np

def analyze_historical_crashes():
    tickers = ["^JKSE", "EIDO", "USDIDR=X", "^GSPC"]
    print("Mengunduh data historis multi-tahun (2019 - 2026)...")
    raw = yf.download(tickers, start="2019-12-01", end="2026-11-20", progress=False)

    closes = raw["Close"]
    ihsg = closes["^JKSE"].dropna()
    eido = closes["EIDO"].dropna()
    idr = closes["USDIDR=X"].dropna()
    sp = closes["^GSPC"].dropna()

    # Gabungkan ke satu DataFrame
    df = pd.DataFrame({
        "ihsg": ihsg,
        "ihsg_sma20": ihsg.rolling(20).mean(),
        "ihsg_sma50": ihsg.rolling(50).mean(),
        "ihsg_sma200": ihsg.rolling(200).mean(),
        "ihsg_chg1d": ihsg.pct_change() * 100,
        "ihsg_chg5d": ihsg.pct_change(5) * 100,
        "eido": eido,
        "eido_chg1d": eido.pct_change() * 100,
        "idr": idr,
        "idr_chg1d": idr.pct_change() * 100,
        "sp_chg1d": sp.pct_change() * 100
    }).dropna()

    # Cari hari-hari dengan koreksi tajam IHSG (Drop > 1.5% atau Drop 5-hari > 3.5%)
    severe_drops = df[(df["ihsg_chg1d"] <= -1.5) | (df["ihsg_chg5d"] <= -3.5)]
    print(f"\nTotal hari koreksi tajam/crash terdeteksi: {len(severe_drops)} hari perdagangan.")

    # Kasus-kasus Crash Terkenal
    crash_periods = {
        "COVID-19 Crash (Feb - Mar 2020)": ("2020-02-15", "2020-03-31"),
        "Fed Rate Hike & Inflasi Global (Mei 2022)": ("2022-05-01", "2022-05-31"),
        "Krisis SVB & Perbankan AS (Maret 2023)": ("2023-03-01", "2023-03-31"),
        "Geopolitik Timteng & Rupiah 16k (April 2024)": ("2024-04-10", "2024-05-15"),
        "Black Monday Global (Agustus 2024)": ("2024-08-01", "2024-08-10"),
        "Trump Win & DXY Outflow (Okt - Nov 2024)": ("2024-10-20", "2024-11-20"),
        "MEGA CRASH AWAL 2026 (Jan - Mei 2026)": ("2026-01-20", "2026-05-31")
    }

    print("\n" + "=" * 80)
    print("ANALISIS METRIK KUANTITATIF SETIAP PERISTIWA CRASH IHSG")
    print("=" * 80)

    for name, (start_dt, end_dt) in crash_periods.items():
        sub = df.loc[start_dt:end_dt]
        if sub.empty:
            continue
        max_drop_1d = sub["ihsg_chg1d"].min()
        max_drop_5d = sub["ihsg_chg5d"].min()
        avg_eido_lead = sub["eido_chg1d"].mean()
        min_eido_drop = sub["eido_chg1d"].min()
        max_idr_spike = sub["idr_chg1d"].max()
        pct_below_sma50 = (sub["ihsg"] < sub["ihsg_sma50"]).mean() * 100
        
        # Titik awal drop
        first_peak = sub["ihsg"].iloc[0]
        trough = sub["ihsg"].min()
        total_decline = ((trough - first_peak) / first_peak) * 100

        print(f"\n📌 {name.upper()}")
        print(f"• Total Penurunan Indeks : {total_decline:.2f}% (Trough: {trough:,.0f})")
        print(f"• Drop 1-Hari Terburuk   : {max_drop_1d:.2f}%")
        print(f"• Drop 5-Hari Terburuk   : {max_drop_5d:.2f}%")
        print(f"• Posisi di bawah SMA50  : {pct_below_sma50:.1f}% hari")
        print(f"• Drop EIDO Terburuk     : {min_eido_drop:.2f}% (Leading Wall Street)")
        print(f"• Lonjakan Kurs USD/IDR  : +{max_idr_spike:.2f}% per hari")

    # Uji Efektivitas Aturan Crash Shield:
    # Rule 1: EIDO semalam <= -2.0%
    # Rule 2: IHSG < SMA50 DAN ihsg_chg5d <= -2.5%
    # Rule 3: IHSG Drop 1 hari <= -1.2%
    # Rule 4: USD/IDR naik >= +0.7% DAN S&P 500 <= -1.5%
    
    df["shield_active"] = (
        (df["eido_chg1d"] <= -2.0) |
        ((df["ihsg"] < df["ihsg_sma50"]) & (df["ihsg_chg5d"] <= -2.5)) |
        (df["ihsg_chg1d"] <= -1.2) |
        ((df["idr_chg1d"] >= 0.7) & (df["sp_chg1d"] <= -1.5))
    )

    shield_days = df[df["shield_active"]]
    print("\n" + "=" * 80)
    print("EVALUASI ATURAN 'IHSG CRASH SHIELD'")
    print("=" * 80)
    print(f"Total Hari Diuji (2020 - 2026) : {len(df)} Hari Bursa")
    print(f"Hari Crash Shield Aktif        : {len(shield_days)} Hari ({len(shield_days)/len(df)*100:.1f}%)")
    
    # Hitung rata-rata return IHSG pada hari setelah shield aktif (t+1)
    df["next_day_ret"] = df["ihsg"].shift(-1).pct_change() * 100
    avg_ret_shield = df[df["shield_active"]]["next_day_ret"].mean()
    win_pct_loss_avoided = (df[df["shield_active"]]["next_day_ret"] <= 0).mean() * 100
    print(f"Probabilitas Hari Lanjutan Turun/Negatif: {win_pct_loss_avoided:.1f}%")
    print(f"Rata-rata Return Hari Lanjutan         : {avg_ret_shield:.2f}%")

if __name__ == "__main__":
    analyze_historical_crashes()
