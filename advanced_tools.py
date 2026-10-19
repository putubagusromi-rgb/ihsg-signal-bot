"""
Modul Fitur Canggih:
1. CHART GENERATOR (/chart [KODE]): Menggambar Candlestick + MA20/MA50 + Target TP/SL & kirim gambar ke Telegram.
2. LOT & RISK CALCULATOR (/calc [KODE] [MODAL]): Menghitung batas aman lot dan potensi profit/loss.
3. SECTOR ROTATION RADAR (/sektor): Memantau rotasi arus dana antar sektor di IHSG.
"""

import io
import os
import re
from typing import Dict, Any, List
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from signal_engine import fetch_stock_data, calculate_support_resistance


def generate_stock_chart(ticker: str) -> io.BytesIO:
    """
    Membuat gambar visual chart candlestick teknikal lengkap dengan indikator & level trading plan.
    """
    clean = ticker.replace(".JK", "").strip().upper()
    df = fetch_stock_data(clean, period="3mo", interval="1d")
    if df is None or len(df) < 15:
        return None

    # Ambil 45 candle terakhir agar grafik tajam dan jelas
    df_plot = df.tail(45).copy()
    levels = calculate_support_resistance(df)

    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.5), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
    fig.patch.set_facecolor('#0e1117')
    ax1.set_facecolor('#0e1117')
    ax2.set_facecolor('#0e1117')

    # Gambar Candlestick manual yang presisi
    width = 0.6
    width2 = 0.1
    col_up = '#00f576'
    col_down = '#ff3355'

    x_dates = range(len(df_plot))
    df_plot['idx'] = list(x_dates)

    up_idx = df_plot[df_plot.Close >= df_plot.Open]
    down_idx = df_plot[df_plot.Close < df_plot.Open]

    # Bar body & wicks
    ax1.bar(up_idx['idx'], up_idx.Close - up_idx.Open, width, bottom=up_idx.Open, color=col_up, alpha=0.9)
    ax1.bar(up_idx['idx'], up_idx.High - up_idx.Close, width2, bottom=up_idx.Close, color=col_up)
    ax1.bar(up_idx['idx'], up_idx.Low - up_idx.Open, width2, bottom=up_idx.Open, color=col_up)

    ax1.bar(down_idx['idx'], down_idx.Open - down_idx.Close, width, bottom=down_idx.Close, color=col_down, alpha=0.9)
    ax1.bar(down_idx['idx'], down_idx.High - down_idx.Open, width2, bottom=down_idx.Open, color=col_down)
    ax1.bar(down_idx['idx'], down_idx.Low - down_idx.Close, width2, bottom=down_idx.Open, color=col_down)

    # Moving Averages
    ax1.plot(df_plot['idx'], df_plot['EMA_20'], color='#00d8f6', label='EMA 20', linewidth=1.5)
    ax1.plot(df_plot['idx'], df_plot['EMA_50'], color='#ffbb00', label='EMA 50', linewidth=1.5)

    # Garis Trading Plan Horizontal
    close_val = float(df_plot['Close'].iloc[-1])
    tp1 = levels['resistance_1']
    sl = levels['support_1'] * 0.97

    ax1.axhline(tp1, color='#33bbff', linestyle='--', linewidth=1.2, label=f'Target TP1: Rp{int(tp1):,}')
    ax1.axhline(sl, color='#ff4444', linestyle='--', linewidth=1.2, label=f'Stop Loss: Rp{int(sl):,}')

    ax1.set_title(f"CHART & TRADING PLAN: #{clean} (Rp{int(close_val):,})", fontsize=14, fontweight='bold', color='white', pad=12)
    ax1.grid(color='#222734', linestyle=':', linewidth=0.8)
    ax1.legend(loc='upper left', framealpha=0.3, fontsize=9)

    # Volume Subplot
    ax2.bar(up_idx['idx'], up_idx.Volume / 1000, width, color=col_up, alpha=0.7)
    ax2.bar(down_idx['idx'], down_idx.Volume / 1000, width, color=col_down, alpha=0.7)
    ax2.set_ylabel('Vol (K)', fontsize=9, color='#888')
    ax2.grid(color='#222734', linestyle=':', linewidth=0.8)

    # Label tanggal x-axis
    step = max(1, len(df_plot) // 6)
    ticks_pos = list(range(0, len(df_plot), step))
    ticks_label = [df_plot.index[i].strftime('%d %b') for i in ticks_pos]
    ax2.set_xticks(ticks_pos)
    ax2.set_xticklabels(ticks_label, rotation=0, fontsize=9, color='#aaa')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, facecolor=fig.get_facecolor(), edgecolor='none')
    buf.seek(0)
    plt.close(fig)
    return buf


def calculate_position_sizing(ticker: str, capital_str: str) -> Dict[str, Any]:
    """
    Menghitung batas aman lot dan rasio profit/loss berdasarkan modal user.
    """
    clean = ticker.replace(".JK", "").strip().upper()
    df = fetch_stock_data(clean, period="3mo", interval="1d")
    if df is None:
        return {"error": f"Saham #{clean} tidak ditemukan."}

    # Parse input modal (contoh: 10jt, 10000000, 50juta, 5jt)
    cap_raw = capital_str.lower().replace("rp", "").replace(".", "").replace(",", "").strip()
    if "jt" in cap_raw or "juta" in cap_raw:
        val_str = re.sub(r"[^\d.]", "", cap_raw.replace("juta", "").replace("jt", ""))
        val = float(val_str) if val_str else 0.0
        capital = val * 1_000_000
    else:
        digits_only = re.sub(r"[^\d]", "", cap_raw)
        capital = float(digits_only) if digits_only else 0.0

    if capital <= 0:
        return {"error": "Nominal modal tidak valid. Contoh: <code>/calc BBCA 10jt</code>"}

    levels = calculate_support_resistance(df)
    close = float(df["Close"].iloc[-1])
    tp1 = levels["resistance_1"]
    sl = levels["support_1"] * 0.97

    # Aturan Manajemen Risiko: Maksimal kerugian 2% dari total modal
    max_risk_amount = capital * 0.02
    risk_per_share = close - sl

    if risk_per_share <= 0:
        risk_per_share = close * 0.03  # Default 3% risk

    # 1 Lot = 100 Lembar
    shares_allowed = max_risk_amount / risk_per_share
    lots_by_risk = int(shares_allowed / 100)

    # Maksimal alokasi modal: tidak boleh melebihi total modal
    cost_per_lot = close * 100
    max_lots_by_capital = int(capital / cost_per_lot)

    recommended_lots = max(1, min(lots_by_risk, max_lots_by_capital))
    total_spent = recommended_lots * cost_per_lot
    total_potential_profit = recommended_lots * 100 * (tp1 - close)
    total_potential_loss = recommended_lots * 100 * (close - sl)

    reward_risk_ratio = round((tp1 - close) / (close - sl), 2) if (close - sl) > 0 else 1.0

    return {
        "ticker": clean,
        "capital": capital,
        "price": int(close),
        "cost_per_lot": int(cost_per_lot),
        "recommended_lots": recommended_lots,
        "total_spent": int(total_spent),
        "cash_remaining": int(capital - total_spent),
        "tp1": int(tp1),
        "sl": int(sl),
        "profit_potential": int(total_potential_profit),
        "loss_potential": int(total_potential_loss),
        "profit_pct": round(((tp1 - close) / close) * 100, 2),
        "loss_pct": round(((sl - close) / close) * 100, 2),
        "rr_ratio": reward_risk_ratio
    }


def scan_sector_rotation() -> List[Dict[str, Any]]:
    """
    Memantau rotasi arus dana dan performa sektor-sektor utama di BEI.
    """
    SECTOR_LEADERS = {
        "🏦 Financials (Bank)": ["BBCA", "BBRI", "BMRI", "BBNI"],
        "⚡ Energy & Coal": ["ADRO", "PTBA", "MEDC", "PGAS"],
        "🛒 Consumer Goods": ["ICBP", "INDF", "UNVR", "MYOR"],
        "🧱 Basic Materials": ["AMMN", "MDKA", "ANTM", "INCO"],
        "🏗️ Infrastructure & Telco": ["TLKM", "JSMR", "TOWR", "ISAT"]
    }

    sector_results = []
    for sector_name, tickers in SECTOR_LEADERS.items():
        changes = []
        best_stock = ""
        best_change = -999.0

        for sym in tickers:
            try:
                formatted = sym + ".JK"
                t = yf.Ticker(formatted)
                h = t.history(period="2d")
                if len(h) >= 2:
                    c = float(h["Close"].iloc[-1])
                    p = float(h["Close"].iloc[-2])
                    pct = ((c - p) / p) * 100
                    changes.append(pct)
                    if pct > best_change:
                        best_change = pct
                        best_stock = sym
            except Exception:
                continue

        avg_change = sum(changes) / len(changes) if changes else 0.0
        sector_results.append({
            "sector": sector_name,
            "avg_change": round(avg_change, 2),
            "leader": best_stock,
            "leader_pct": round(best_change, 2)
        })

    sector_results.sort(key=lambda x: x["avg_change"], reverse=True)
    return sector_results
