"""
IHSG Macro Regime & Market Intelligence Engine:
Memantau kondisi kesehatan IHSG secara real-time untuk memproteksi modal trading (Risk-On vs Risk-Off),
mendeteksi kapan bursa sedang panik/crash, dan menghitung position sizing / rekomendasi lot modal portofolio.
"""

from typing import Dict, Any
import yfinance as yf
import pandas as pd
import numpy as np


def get_ihsg_market_regime() -> Dict[str, Any]:
    """
    Menganalisis kondisi IHSG harian:
    - Trend (SMA20, SMA50)
    - Volatilitas 1-Day & 5-Day
    - Status: RISK-ON (Aman Belanja), SELECTIVE (Hanya Saham Konglo/Multibagger), atau CASH IS KING (Proteksi Panik)
    """
    try:
        ihsg = yf.download("^JKSE", period="3mo", interval="1d", progress=False)
        if ihsg.empty:
            return {"error": "Gagal mengambil data indeks IHSG."}

        close = ihsg["Close"]["^JKSE"] if isinstance(ihsg["Close"], pd.DataFrame) else ihsg["Close"]
        close = close.dropna()
        if len(close) < 25:
            return {"error": "Data IHSG tidak mencukupi."}

        curr_price = float(close.iloc[-1])
        prev_price = float(close.iloc[-2])
        chg_1d = ((curr_price - prev_price) / prev_price) * 100

        p_5d_ago = float(close.iloc[-5]) if len(close) >= 5 else prev_price
        chg_5d = ((curr_price - p_5d_ago) / p_5d_ago) * 100

        sma20 = float(close.rolling(20).mean().iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else sma20

        # Diagnosis Kondisi IHSG
        if chg_1d <= -1.2 or chg_5d <= -3.0:
            regime = "🔴 PANIC SELL / CRASH DEFENSE"
            status_text = "RISK-OFF (CASH IS KING)"
            advice = (
                "⚠️ IHSG mengalami koreksi tajam/panik! Berdasarkan backtest 2024-2026, "
                "dilarang menangkap pisau jatuh. Tahan pembelian baru dan amankan profit di posisi yang ada."
            )
            allow_bigcaps = False
            allow_multibagger = False
            cash_allocation_pct = 70  # Simpan 70% cash

        elif curr_price < sma50 and curr_price < sma20:
            regime = "🟡 DOWNTREND / SELECTIVE MARKET"
            status_text = "SELECTIVE RISK-ON (HANYA MULTI-BAGGER)"
            advice = (
                "Indeks sedang dalam tren melemah/sideways di bawah rata-rata. Saham Big Caps (BBCA, BBRI, BMRI) rawan terseret, "
                "namun saham second-liner dengan akumulasi Whale & rumor aksi korporasi (seperti PANI, BIPI) tetap berpeluang manggung."
            )
            allow_bigcaps = False
            allow_multibagger = True
            cash_allocation_pct = 40  # Simpan 40% cash

        else:
            regime = "🟢 UPTREND / BULLISH REGIME"
            status_text = "FULL RISK-ON (PASAR KONDUSIF)"
            advice = (
                "IHSG berada dalam kondisi kuat di atas MA20/MA50. Momentum belanja saham akumulasi whale "
                "sangat kondusif baik untuk Bluechip maupun saham Multi-Bagger."
            )
            allow_bigcaps = True
            allow_multibagger = True
            cash_allocation_pct = 15

        return {
            "ihsg_price": curr_price,
            "chg_1d": chg_1d,
            "chg_5d": chg_5d,
            "sma20": sma20,
            "sma50": sma50,
            "regime": regime,
            "status_text": status_text,
            "advice": advice,
            "allow_bigcaps": allow_bigcaps,
            "allow_multibagger": allow_multibagger,
            "cash_pct": cash_allocation_pct
        }

    except Exception as e:
        return {"error": str(e)}


def calculate_position_sizing(total_capital: float, stock_price: float, max_alloc_pct: float = 0.25) -> Dict[str, Any]:
    """
    Menghitung rekomendasi alokasi modal dan jumlah lot trading:
    Contoh Modal Rp 100.000.000 dengan alokasi 25% (Rp 25.000.000)
    """
    if stock_price <= 0:
        return {"error": "Harga saham tidak valid."}

    max_capital = total_capital * max_alloc_pct
    price_per_lot = stock_price * 100
    lots = int(max_capital // price_per_lot)
    actual_spent = lots * price_per_lot

    return {
        "total_capital": total_capital,
        "max_alloc_capital": max_capital,
        "stock_price": stock_price,
        "price_per_lot": price_per_lot,
        "lots": lots,
        "shares": lots * 100,
        "total_cost": actual_spent,
        "remaining_cash": total_capital - actual_spent
    }
