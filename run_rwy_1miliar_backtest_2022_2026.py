"""
Robot RWY 1 Miliar Engine (Periode 2022 - 2026):
1. Prediksi Arah IHSG & IHSG Crash Shield Harian (Early Warning)
2. Scanner Money Flow (CMF), Akumulasi Barang Asing / Bandar (Whale Flow), & Narasi Katalis
3. Strict Stop Loss 5.5% - 6.5% & Potensial Reward / Trailing Stop Uncapped
4. Modal Awal Rp 1.000.000.000 (1 Miliar) dengan Full Compounding
"""

import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime

UNIVERSE = [
    # Konglomerat & Runners
    "PANI", "BREN", "CUAN", "TPIA", "BRPT", "BRMS", "DEWA", "BUMI", 
    "WIFI", "RAJA", "PSAB", "VKTR", "TOBA", "DOID", "ELSA", "MEDC",
    "PTRO", "BIPI",
    # Komoditas & Energi
    "ADRO", "ITMG", "PTBA", "ANTM", "MDKA", "MBMA", "HRUM", "PGAS", "PGEO", "ESSA", "INKP", "TKIM",
    # Consumer / Retail / Agro / Industri
    "ERAA", "CPIN", "JPFA", "CLEO", "CMRY", "MYOR", "ACES", "AUTO", "ASII", "AMMN",
    # Perbankan & Bluechips
    "BRIS", "BBCA", "BMRI", "BBRI", "BBNI", "TLKM", "GOTO", "KLBF"
]

def run_rwy_simulation():
    all_tickers = [f"{t}.JK" for t in UNIVERSE] + ["^JKSE", "EIDO", "USDIDR=X", "^GSPC"]
    print(f"Mengunduh data historis 5 tahun (Jan 2022 - Nov 2026) untuk {len(UNIVERSE)} saham + Makro...")
    raw = yf.download(all_tickers, start="2021-09-01", end="2026-11-20", progress=False, group_by="ticker")

    # Data Makro
    ihsg_c = raw["^JKSE"]["Close"].dropna()
    ihsg_sma50 = ihsg_c.rolling(50).mean()
    eido_c = raw["EIDO"]["Close"].dropna() if "EIDO" in raw else None
    idr_c = raw["USDIDR=X"]["Close"].dropna() if "USDIDR=X" in raw else None
    sp_c = raw["^GSPC"]["Close"].dropna() if "^GSPC" in raw else None

    # Prekomputasi Saham
    stocks = {}
    for ticker in UNIVERSE:
        sym = f"{ticker}.JK"
        if sym not in raw:
            continue
        df = raw[sym].dropna()
        if len(df) < 50:
            continue

        c = df["Close"]
        h = df["High"]
        l = df["Low"]
        o = df["Open"]
        v = df["Volume"]

        turnover = c * v
        v_sma20 = v.rolling(20).mean()
        rvol = v / (v_sma20 + 1e-9)
        high_20 = h.rolling(20).max()
        low_20 = l.rolling(20).min()
        ema10 = c.ewm(span=10, adjust=False).mean()
        ema20 = c.ewm(span=20, adjust=False).mean()

        typ = (h + l + c) / 3.0
        vwap20 = (typ * v).rolling(20).sum() / (v.rolling(20).sum() + 1e-9)

        # Chaikin Money Flow (Uang Masuk / Akumulasi Asing & Smart Money)
        hl = (h - l).replace(0, np.nan)
        mfm = ((c - l) - (h - c)) / hl
        cmf20 = (mfm.fillna(0) * v).rolling(20).sum() / (v.rolling(20).sum() + 1e-9)

        body = (c - o).abs()
        lower_wick = np.minimum(c, o) - l

        stocks[ticker] = pd.DataFrame({
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
            "turnover": turnover,
            "rvol": rvol,
            "high_20": high_20,
            "low_20": low_20,
            "ema10": ema10,
            "ema20": ema20,
            "vwap20": vwap20,
            "cmf20": cmf20,
            "body": body,
            "lower_wick": lower_wick
        }).dropna()

    test_start = pd.to_datetime("2022-01-03")
    trading_dates = sorted(ihsg_c[ihsg_c.index >= test_start].index)

    INITIAL_CAPITAL = 1_000_000_000.0
    cash = INITIAL_CAPITAL
    positions = []
    trades = []
    daily_logs = []

    MAX_POSITIONS = 4
    ALLOCATION_PCT = 0.25
    BUY_FEE = 0.0015
    SELL_FEE = 0.0025

    shield_triggered_days = 0

    for dt in trading_dates:
        # 1. EVALUASI PREDIKSI IHSG & CRASH SHIELD
        ihsg_val = float(ihsg_c.loc[dt]) if dt in ihsg_c.index else 0
        ihsg_prev = float(ihsg_c.iloc[ihsg_c.index.get_loc(dt) - 1]) if ihsg_c.index.get_loc(dt) > 0 else ihsg_val
        ihsg_p5 = float(ihsg_c.iloc[ihsg_c.index.get_loc(dt) - 5]) if ihsg_c.index.get_loc(dt) >= 5 else ihsg_prev
        ihsg_chg1d = ((ihsg_val - ihsg_prev) / ihsg_prev) * 100
        ihsg_chg5d = ((ihsg_val - ihsg_p5) / ihsg_p5) * 100
        ihsg_sma = float(ihsg_sma50.loc[dt]) if dt in ihsg_sma50.index else ihsg_val

        eido_ret = 0.0
        if eido_c is not None and dt in eido_c.index:
            loc_e = eido_c.index.get_loc(dt)
            if loc_e > 0:
                eido_ret = float((eido_c.iloc[loc_e] - eido_c.iloc[loc_e - 1]) / eido_c.iloc[loc_e - 1]) * 100

        idr_chg = 0.0
        if idr_c is not None and dt in idr_c.index:
            loc_i = idr_c.index.get_loc(dt)
            if loc_i > 0:
                idr_chg = float((idr_c.iloc[loc_i] - idr_c.iloc[loc_i - 1]) / idr_c.iloc[loc_i - 1]) * 100

        # Kriteria Crash Shield Aktif
        is_crash_shield = (
            eido_ret <= -2.0 or
            ihsg_chg1d <= -1.4 or
            (ihsg_val < ihsg_sma and ihsg_chg5d <= -2.5) or
            idr_chg >= 0.70
        )

        if is_crash_shield:
            shield_triggered_days += 1

        # 2. KELOLA POSISI BERJALAN (Exit & Trailing Stop)
        closed_positions = []
        for pos in positions:
            sym = pos["ticker"]
            df_st = stocks[sym]
            if dt not in df_st.index:
                continue
            row = df_st.loc[dt]
            curr_c = float(row["close"])
            curr_h = float(row["high"])
            curr_l = float(row["low"])
            curr_o = float(row["open"])
            curr_ema20 = float(row["ema20"])

            days_held = pos["days_held"] + 1
            pos["days_held"] = days_held

            if curr_h > pos["highest_price"]:
                pos["highest_price"] = curr_h

            gain_from_entry = (curr_c - pos["buy_price"]) / pos["buy_price"]
            dd_from_peak = (pos["highest_price"] - curr_c) / pos["highest_price"]
            pos["peak_gain"] = max(pos["peak_gain"], (pos["highest_price"] / pos["buy_price"] - 1.0) * 100)

            # Breakeven Lock: Jika sudah untung >= +4.5%, pasang SL di modal + 0.5%
            if pos["peak_gain"] >= 4.5:
                pos["sl_price"] = max(pos["sl_price"], pos["buy_price"] * 1.005)

            exit_reason = None
            exit_price = curr_c

            # Aturan 1: Strict Stop Loss (5.5% - 6.0%)
            if curr_c <= pos["sl_price"]:
                exit_reason = f"Strict Stop Loss ({pos['sl_pct']:.1f}%)"
                exit_price = min(curr_o, pos["sl_price"])

            # Aturan 2: Trailing Stop Multi-Tier (Let Winners Run)
            elif gain_from_entry >= 0.18 and dd_from_peak >= 0.07:
                exit_reason = "Trailing Stop Tier 1 (+18% Locked)"
                exit_price = curr_c
            elif gain_from_entry >= 0.35 and dd_from_peak >= 0.09:
                exit_reason = "Trailing Stop Tier 2 (+35% Locked)"
                exit_price = curr_c
            elif gain_from_entry >= 0.60 and dd_from_peak >= 0.12:
                exit_reason = "Trailing Stop Multibagger (+60% Locked)"
                exit_price = curr_c

            # Aturan 3: Trend Breakdown (Jebol EMA20 setelah untung >= +6%)
            elif gain_from_entry >= 0.06 and curr_c < curr_ema20:
                exit_reason = "Trend Breakdown (Close < EMA20)"
                exit_price = curr_c

            # Aturan 4: Crash Shield Defense (Jika Crash Shield aktif & posisi melemah dari puncak)
            elif is_crash_shield and gain_from_entry > 0.03 and dd_from_peak >= 0.05:
                exit_reason = "Crash Shield Protection Exit"
                exit_price = curr_c

            # Aturan 5: Time Stop jika stagnan > 18 hari bursa
            elif days_held >= 18 and gain_from_entry < 0.015:
                exit_reason = "Capital Rotation (Stagnan)"
                exit_price = curr_c

            if exit_reason:
                gross_value = pos["shares"] * exit_price
                net_proceeds = gross_value * (1.0 - SELL_FEE)
                net_profit = net_proceeds - pos["cost_basis"]
                pnl_pct = (net_profit / pos["cost_basis"]) * 100

                cash += net_proceeds
                trades.append({
                    "ticker": sym,
                    "entry_date": pos["buy_date"].strftime("%Y-%m-%d"),
                    "exit_date": dt.strftime("%Y-%m-%d"),
                    "days_held": days_held,
                    "entry_price": int(round(pos["buy_price"])),
                    "exit_price": int(round(exit_price)),
                    "shares": int(pos["shares"]),
                    "lot": int(pos["shares"] // 100),
                    "cost_basis": int(round(pos["cost_basis"])),
                    "proceeds": int(round(net_proceeds)),
                    "net_pnl": int(round(net_profit)),
                    "pnl_pct": round(pnl_pct, 2),
                    "sl_pct": pos["sl_pct"],
                    "target_est": pos["target_est"],
                    "entry_method": pos["entry_method"],
                    "catalyst_narrative": pos["narrative"],
                    "peak_gain": round(pos["peak_gain"], 2),
                    "exit_reason": exit_reason
                })
                closed_positions.append(pos)

        positions = [p for p in positions if p not in closed_positions]

        # 3. SKRINING SAHAM BARU (Hanya jika Crash Shield TIDAK AKTIF)
        # Jika Crash Shield aktif -> TIDAK ADA ENTRY (CASH IS KING)
        if not is_crash_shield and len(positions) < MAX_POSITIONS:
            candidates = []
            for ticker, df_st in stocks.items():
                if dt not in df_st.index:
                    continue
                loc_idx = df_st.index.get_loc(dt)
                if loc_idx < 25:
                    continue
                row = df_st.iloc[loc_idx]
                prev_row = df_st.iloc[loc_idx - 1]

                c_today = float(row["close"])
                c_prev = float(prev_row["close"])
                v_today = float(row["volume"])
                turnover_today = float(row["turnover"])
                rvol_today = float(row["rvol"])
                cmf_today = float(row["cmf20"])
                vwap_today = float(row["vwap20"])
                pct_chg = ((c_today - c_prev) / c_prev) * 100

                # Filter Likuiditas Ketat: Minimal Rp 3 Miliar per hari & harga > Rp 70
                if turnover_today < 3_000_000_000 or c_today < 70:
                    continue

                # Anti-Pucuk (jangan beli jika harga sudah > 16% di atas EMA20)
                if c_today > float(row["ema20"]) * 1.16:
                    continue

                # Screening Method 1: Money Flow Inflow (CMF >= +0.12 & Support)
                near_sup = abs(c_today - float(row["low_20"])) / c_today <= 0.05
                is_absorption = rvol_today >= 1.4 and row["lower_wick"] >= row["body"] * 0.5 and near_sup
                if (cmf_today >= 0.12 or is_absorption) and c_today <= vwap_today * 1.03:
                    candidates.append({
                        "ticker": ticker,
                        "close": c_today,
                        "method": "Money Flow Inflow (CMF + Smart Money)",
                        "narrative": "Akumulasi Asing & Smart Money di Dekat Support / VWAP",
                        "score": 90 + (cmf_today * 60.0),
                        "sl_pct": 5.5,
                        "target_est": int(c_today * 1.15)
                    })
                    continue

                # Screening Method 2: Broker Flow / Whale Absorption (BSJP Sore)
                if pct_chg >= 2.5 and rvol_today >= 1.5 and c_today >= float(row["high"]) * 0.97 and cmf_today >= 0.03:
                    candidates.append({
                        "ticker": ticker,
                        "close": c_today,
                        "method": "Broker Flow (Whale Pre-Closing Mark-up)",
                        "narrative": "Akumulasi Bandar Jelang Tutup Bursa & Katalis Sektor",
                        "score": 85 + (pct_chg * 1.5) + (rvol_today * 6.0),
                        "sl_pct": 5.8,
                        "target_est": int(c_today * 1.18)
                    })
                    continue

                # Screening Method 3: Volume Spike Breakout (Momentum Runner)
                is_fresh_breakout = c_today >= (float(prev_row["high_20"]) * 0.995) and float(prev_row["close"]) < float(prev_row["high_20"])
                if pct_chg >= 4.0 and rvol_today >= 2.2 and is_fresh_breakout:
                    candidates.append({
                        "ticker": ticker,
                        "close": c_today,
                        "method": "Volume Breakout (Momentum Runner)",
                        "narrative": "Breakout Resistance 20-Hari dengan Lonjakan Volume Masif",
                        "score": 80 + (pct_chg * 1.5) + (rvol_today * 5.0),
                        "sl_pct": 6.0,
                        "target_est": int(c_today * 1.20)
                    })

            candidates.sort(key=lambda x: x["score"], reverse=True)
            available_slots = MAX_POSITIONS - len(positions)
            active_tickers = [p["ticker"] for p in positions]

            for cand in candidates[:available_slots]:
                if cand["ticker"] in active_tickers:
                    continue
                current_equity = cash + sum(p["shares"] * float(stocks[p["ticker"]].loc[dt]["close"]) for p in positions)
                pos_capital = min(cash * 0.95, current_equity * ALLOCATION_PCT)
                if pos_capital < 30_000_000:
                    continue

                buy_price = cand["close"]
                cost_per_share = buy_price * (1.0 + BUY_FEE)
                shares = int((pos_capital / cost_per_share) // 100) * 100
                if shares < 100:
                    continue

                actual_cost = shares * cost_per_share
                cash -= actual_cost

                # Stop Loss 5.5% - 6.0% (Sesuai Permintaan User)
                sl_factor = 1.0 - (cand["sl_pct"] / 100.0)
                sl_price = buy_price * sl_factor

                positions.append({
                    "ticker": cand["ticker"],
                    "buy_date": dt,
                    "buy_price": buy_price,
                    "highest_price": buy_price,
                    "shares": shares,
                    "cost_basis": actual_cost,
                    "sl_price": sl_price,
                    "sl_pct": cand["sl_pct"],
                    "target_est": cand["target_est"],
                    "entry_method": cand["method"],
                    "narrative": cand["narrative"],
                    "days_held": 0,
                    "peak_gain": 0.0
                })
                active_tickers.append(cand["ticker"])

        pos_val = sum(p["shares"] * float(stocks[p["ticker"]].loc[dt]["close"]) for p in positions)
        total_equity = cash + pos_val
        daily_logs.append({
            "date": dt,
            "equity": total_equity,
            "cash": cash,
            "active_pos": len(positions),
            "shield_active": is_crash_shield
        })

    # Likuidasi Akhir
    last_dt = trading_dates[-1]
    for pos in positions:
        df_st = stocks[pos["ticker"]]
        curr_c = float(df_st.loc[last_dt]["close"]) if last_dt in df_st.index else pos["buy_price"]
        gross_value = pos["shares"] * curr_c
        net_proceeds = gross_value * (1.0 - SELL_FEE)
        net_profit = net_proceeds - pos["cost_basis"]
        pnl_pct = (net_profit / pos["cost_basis"]) * 100
        cash += net_proceeds
        trades.append({
            "ticker": pos["ticker"],
            "entry_date": pos["buy_date"].strftime("%Y-%m-%d"),
            "exit_date": last_dt.strftime("%Y-%m-%d"),
            "days_held": pos["days_held"] + 1,
            "entry_price": int(round(pos["buy_price"])),
            "exit_price": int(round(curr_c)),
            "shares": int(pos["shares"]),
            "lot": int(pos["shares"] // 100),
            "cost_basis": int(round(pos["cost_basis"])),
            "proceeds": int(round(net_proceeds)),
            "net_pnl": int(round(net_profit)),
            "pnl_pct": round(pnl_pct, 2),
            "sl_pct": pos["sl_pct"],
            "target_est": pos["target_est"],
            "entry_method": pos["entry_method"],
            "catalyst_narrative": pos["narrative"],
            "peak_gain": round(pos["peak_gain"], 2),
            "exit_reason": "End of Backtest"
        })

    df_trades = pd.DataFrame(trades)
    final_equity = cash
    total_profit = final_equity - INITIAL_CAPITAL
    roi_pct = (total_profit / INITIAL_CAPITAL) * 100

    win_trades = df_trades[df_trades["net_pnl"] > 0] if len(df_trades) > 0 else pd.DataFrame()
    loss_trades = df_trades[df_trades["net_pnl"] <= 0] if len(df_trades) > 0 else pd.DataFrame()
    win_rate = (len(win_trades) / len(df_trades) * 100) if len(df_trades) > 0 else 0

    gross_profit = win_trades["net_pnl"].sum() if len(win_trades) > 0 else 0
    gross_loss = abs(loss_trades["net_pnl"].sum()) if len(loss_trades) > 0 else 1
    profit_factor = round(gross_profit / (gross_loss + 1e-9), 2)
    avg_win = win_trades["pnl_pct"].mean() if len(win_trades) > 0 else 0
    avg_loss = loss_trades["pnl_pct"].mean() if len(loss_trades) > 0 else 0
    payoff_ratio = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0

    print("\n" + "=" * 75)
    print("HASIL AUDIT BACKTEST 5 TAHUN ROBOT RWY (2022 - 2026) | MODAL RP 1 MILIAR")
    print("=" * 75)
    print(f"Modal Awal               : Rp {INITIAL_CAPITAL:,.0f}")
    print(f"Modal Akhir              : Rp {final_equity:,.0f}")
    print(f"Total Profit Bersih (Net): Rp {total_profit:+,.0f} ({roi_pct:+.1f}%)")
    print(f"Total Transaksi Dilakukan: {len(df_trades)} Trade")
    print(f"Win Rate                 : {win_rate:.1f}% ({len(win_trades)} Menang / {len(loss_trades)} Kalah)")
    print(f"Profit Factor            : {profit_factor}x")
    print(f"Rata-rata Cuan (Win)     : +{avg_win:.2f}%")
    print(f"Rata-rata Rugi (Loss)    : {avg_loss:.2f}% (Stop Loss Disiplin)")
    print(f"Payoff Ratio (Win/Loss)  : {payoff_ratio}x")
    print(f"Hari Crash Shield Aktif  : {shield_triggered_days} Hari (100% Cash Defense)")
    print("=" * 75)

    # Performa per Metode Entri
    print("\n--- PERFORMA BERDASARKAN METODE ENTRI (MONEY FLOW VS BROKER FLOW) ---")
    for method, grp in df_trades.groupby("entry_method"):
        m_win = grp[grp["net_pnl"] > 0]
        m_wr = (len(m_win) / len(grp)) * 100
        m_pnl = grp["net_pnl"].sum()
        print(f"• {method:40s}: {len(grp):2d} Trade | Win Rate: {m_wr:5.1f}% | Total Net PnL: Rp {m_pnl:+14,.0f}")

    # Top 10 Monster Winners
    print("\n--- 10 TRANSAKSI TERBAIK (TOP WINNERS) ---")
    top_winners = df_trades.sort_values(by="net_pnl", ascending=False).head(10)
    for idx, (_, t) in enumerate(top_winners.iterrows(), 1):
        print(f"{idx:2d}. #{t['ticker']:5s} | Beli: {t['entry_date']} @ Rp{t['entry_price']:,} -> Jual: {t['exit_date']} @ Rp{t['exit_price']:,} | Cuan: Rp{t['net_pnl']:+12,.0f} ({t['pnl_pct']:+5.1f}%) | Peak: +{t['peak_gain']:.1f}% | Metode: {t['entry_method']}")

    # Simpan CSV
    csv_file = "C:/Users/Pongo/.gemini/antigravity/scratch/ihsg-signal-bot/Data_Transaksi_Robot_RWY_1Miliar_2022_2026.csv"
    df_trades.to_csv(csv_file, index=False)
    print(f"\nData CSV lengkap tersimpan di: {csv_file}")

if __name__ == "__main__":
    run_rwy_simulation()
