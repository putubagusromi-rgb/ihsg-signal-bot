import yfinance as yf
import pandas as pd
import numpy as np

tickers = ["PTRO.JK", "DEWA.JK", "BIPI.JK", "PANI.JK", "CUAN.JK", "BRMS.JK", "PSAB.JK"]
print("Downloading multi-year historical data for deep bandar study...")
raw = yf.download(tickers, start="2023-01-01", end="2026-10-23", progress=False)

closes = raw["Close"]
highs = raw["High"]
lows = raw["Low"]
volumes = raw["Volume"]

results = []

for t in tickers:
    c = closes[t].dropna()
    h = highs[t].reindex(c.index)
    l = lows[t].reindex(c.index)
    v = volumes[t].reindex(c.index)
    
    if len(c) < 50:
        continue

    # Cari titik awal reli monster (Lowest low sebelum super run)
    min_idx = l.idxmin()
    max_idx = h[h.index >= min_idx].idxmax() if min_idx in h.index else h.idxmax()
    min_p = float(l.loc[min_idx])
    max_p = float(h.loc[max_idx])
    gain_pct = (max_p / min_p - 1) * 100
    
    # 1. Analisis 60 hari SEBELUM Ignition (Fase Akumulasi Senyap)
    # Periode sebelum harga mulai breakout tajam
    # Hari pertama harga naik > 5% dengan volume > 2.5x SMA20
    v_sma20 = v.rolling(20).mean()
    rvol = v / v_sma20
    
    # Squeeze / ATR (Kompresi Volatilitas)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr20 = tr.rolling(20).mean()
    atr_pct = atr20 / c * 100
    
    # VWAP 20 (Harga Modal Bandar)
    pv = ((h + l + c) / 3.0) * v
    vwap20 = pv.rolling(20).sum() / v.rolling(20).sum()
    
    # Chaikin Money Flow (CMF)
    hl = (h - l).replace(0, np.nan)
    mfm = ((c - l) - (h - c)) / hl
    cmf20 = (mfm.fillna(0) * v).rolling(20).sum() / v.rolling(20).sum()
    
    # Cari tanggal ignition pertama setelah lowest low
    post_low = c[c.index >= min_idx]
    ignition_candidates = post_low[(rvol >= 2.0) & (c.pct_change() >= 0.04)]
    ignition_date = ignition_candidates.index[0] if len(ignition_candidates) > 0 else min_idx
    
    # Data sebelum ignition (fase silent accumulation)
    pre_ignition = c[(c.index < ignition_date) & (c.index >= ignition_date - pd.Timedelta(days=60))]
    pre_cmf = cmf20.reindex(pre_ignition.index).mean()
    pre_atr = atr_pct.reindex(pre_ignition.index).mean()
    pre_vol = v.reindex(pre_ignition.index).mean()
    
    # Data saat ignition
    ign_rvol = float(rvol.loc[ignition_date]) if ignition_date in rvol.index else 0
    ign_price = float(c.loc[ignition_date]) if ignition_date in c.index else 0
    ign_cmf = float(cmf20.loc[ignition_date]) if ignition_date in cmf20.index else 0
    
    # Pullback / Shakeout terbesar selama reli naik dari ignition ke peak
    run_window = c[(c.index >= ignition_date) & (c.index <= max_idx)]
    running_max = run_window.cummax()
    drawdowns = (running_max - run_window) / running_max * 100
    max_shakeout = drawdowns.max() if len(drawdowns) > 0 else 0
    
    results.append({
        "ticker": t.replace(".JK", ""),
        "lowest_price": min_p,
        "lowest_date": min_idx.strftime("%Y-%m-%d"),
        "peak_price": max_p,
        "peak_date": max_idx.strftime("%Y-%m-%d"),
        "bagger_mult": max_p / min_p,
        "gain_pct": gain_pct,
        "ignition_date": ignition_date.strftime("%Y-%m-%d"),
        "ignition_price": ign_price,
        "pre_cmf_mean": pre_cmf,
        "pre_atr_pct": pre_atr,
        "ignition_rvol": ign_rvol,
        "ignition_cmf": ign_cmf,
        "max_shakeout_pct": max_shakeout
    })

df_res = pd.DataFrame(results)
print("\n" + "="*80)
print("DEEP EMPIRICAL STUDY: SIKLUS HIDUP BANDAR DI SAHAM MONSTER BEI")
print("="*80)
for idx, r in df_res.iterrows():
    print(f"\n--- {r['ticker']} ---")
    print(f"Harga Terendah: Rp{r['lowest_price']:.0f} ({r['lowest_date']})")
    print(f"Puncak Reli:    Rp{r['peak_price']:.0f} ({r['peak_date']}) -> Naik +{r['gain_pct']:.1f}% ({r['bagger_mult']:.1f}x lipat!)")
    print(f"Fase Akumulasi: Volatilitas harian (ATR%) menyusut ke {r['pre_atr_pct']:.1f}%, CMF rata-rata {r['pre_cmf_mean']:.3f} (Senyap/Bid Absorption)")
    print(f"Hari Ignition:  {r['ignition_date']} di harga Rp{r['ignition_price']:.0f} (Volume lonjak {r['ignition_rvol']:.1f}x lipat, CMF berbalik ke {r['ignition_cmf']:+.3f})")
    print(f"Shakeout Ritel: Selama reli menuju puncak, bandar membanting harga hingga -{r['max_shakeout_pct']:.1f}% untuk membuang ritel")


print("\n" + "="*80)
print("ANALISIS FASE DISTRIBUSI PUCUK (CUCI PIRING BANDAR):")
print("="*80)

for t in tickers:
    c = closes[t].dropna()
    h = highs[t].reindex(c.index)
    l = lows[t].reindex(c.index)
    v = volumes[t].reindex(c.index)
    
    peak_date = h.idxmax()
    peak_high = float(h.loc[peak_date])
    peak_close = float(c.loc[peak_date])
    peak_low = float(l.loc[peak_date])
    peak_vol = float(v.loc[peak_date])
    
    v_sma20 = v.rolling(20).mean()
    rvol_at_peak = peak_vol / v_sma20.loc[peak_date]
    
    pv = ((h + l + c) / 3.0) * v
    vwap20 = pv.rolling(20).sum() / v.rolling(20).sum()
    dist_vwap = (peak_high - vwap20.loc[peak_date]) / vwap20.loc[peak_date] * 100
    
    # Upper shadow candle pucuk (ekor atas penanda guyuran)
    candle_range = peak_high - peak_low
    upper_shadow = (peak_high - max(peak_close, float(raw["Open"][t].loc[peak_date]))) / (candle_range if candle_range > 0 else 1) * 100
    
    print(f"[{t.replace('.JK', '')}] Pucuk {peak_date.strftime('%Y-%m-%d')} di Rp{peak_high:.0f}:")
    print(f"   • Jarak dari VWAP 20D (Harga Modal): +{dist_vwap:.1f}% (Jauh melambung)")
    print(f"   • Climax Volume (RVOL): {rvol_at_peak:.1f}x rata-rata")
    print(f"   • Jarum Pucuk (Upper Shadow / Ekor Atas): {upper_shadow:.1f}% dari rentang lilin (Reversal guyuran)")
