"""
Modul Broker Summary & Deteksi Whale Accumulation (Bandarmology)

Catatan:
Yahoo Finance menyediakan data OHLCV historis & intraday secara gratis, namun
data kode broker mentah (seperti ZP, AK, BK, YP, dsb) pasca penutupan bursa IDX
adalah data proprietary dari feed BEI.

Modul ini menyediakan 2 pendekatan:
1. NATIVE WHALE ENGINE (Gratis via Yahoo Finance):
   Menggunakan model kuantitatif Money Flow (CMF, RVOL, OBV Breakout, dan VWAP Accumulation)
   untuk mendeteksi secara akurat saham mana yang sedang dimasuki Big Money / Whale,
   menghitung estimasi rata-rata harga masuk Whale (Whale Average Price),
   serta estimasi nilai transaksi akumulasi (dalam Miliar Rupiah).

2. BROKER SUMMARY CONNECTOR (Extensible):
   Struktur siap pakai jika pengguna ingin menyuntikkan data broker summary dari sekuritas,
   file CSV, atau API pihak ketiga (GoAPI, Stockbit, dll.) untuk menghitung rasio Top 3 / Top 5 Broker.
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


class WhaleAccumulationAnalyzer:
    """
    Menganalisis pergerakan Big Money / Whale berdasarkan aksi harga dan volume (Bandarmology Kuantitatif).
    """

    @staticmethod
    def analyze_stock_whale_flow(ticker: str, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Menganalisis tanda-tanda akumulasi whale pada saham tertentu.
        """
        if df.empty or len(df) < 20:
            return {
                "ticker": ticker,
                "status": "DATA_INSUFFICIENT",
                "whale_score": 0
            }

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        close = float(latest["Close"])
        prev_close = float(prev["Close"])
        pct_change = ((close - prev_close) / prev_close) * 100

        volume = float(latest["Volume"])
        vol_sma20 = float(latest.get("Vol_SMA20", volume))
        rvol = float(latest.get("RVOL", 1.0))
        cmf = float(latest.get("CMF", 0.0))
        whale_score = int(latest.get("Whale_Score", 50))
        whale_status = str(latest.get("Whale_Status", "NEUTRAL"))
        vwap_20 = float(latest.get("VWAP_20", close))

        # Estimasi Nilai Transaksi Hari Ini (dalam Rupiah)
        estimated_turnover = close * volume

        # Estimasi Net Flow Whale (Money Flow Volume estimasi dalam Miliar IDR)
        # Menggunakan Chaikin Money Flow x Total Turnover
        estimated_whale_flow_idr = (cmf * estimated_turnover) / 1_000_000_000

        # Deteksi Sinyal Entri Whale
        is_whale_entering = False
        reasons = []

        if rvol >= 1.5 and cmf > 0.05 and close >= prev_close:
            is_whale_entering = True
            reasons.append(f"Lonjakan volume {rvol:.1f}x dari rata-rata dengan penutupan positif.")

        if latest.get("OBV", 0) > latest.get("OBV_EMA20", 0) and prev.get("OBV", 0) <= prev.get("OBV_EMA20", 0):
            is_whale_entering = True
            reasons.append("Breakout OBV ke atas garis EMA20 (akumulasi masif dimulai).")

        if whale_score >= 75:
            reasons.append(f"Skor Akumulasi sangat tinggi ({whale_score}/100).")

        # Jarak harga sekarang terhadap rata-rata akumulasi (Whale VWAP)
        pct_from_vwap = ((close - vwap_20) / vwap_20) * 100

        return {
            "ticker": ticker.replace(".JK", ""),
            "close": close,
            "pct_change": pct_change,
            "volume": volume,
            "rvol": rvol,
            "cmf": cmf,
            "whale_score": whale_score,
            "whale_status": whale_status,
            "whale_vwap": vwap_20,
            "pct_from_vwap": pct_from_vwap,
            "turnover_billion": estimated_turnover / 1_000_000_000,
            "whale_flow_billion": estimated_whale_flow_idr,
            "is_whale_entering": is_whale_entering,
            "entry_reasons": reasons
        }


class BrokerSummaryAdapter:
    """
    Adapter opsional untuk membaca data Broker Summary eksternal
    (Top 1, Top 3, Top 5 Buyer vs Seller Broker).
    """

    @staticmethod
    def calculate_bandar_ratio(top_buyers_volume: float, top_sellers_volume: float, total_volume: float) -> Dict[str, Any]:
        """
        Menghitung konsentrasi broker:
        Jika Top 3 Broker Buyer menguasai > 50% dari volume total sementara seller tersebar,
        maka terjadi Big Accumulation (Bandar mengumpulkan barang).
        """
        if total_volume <= 0:
            return {"ratio": 0, "status": "UNKNOWN"}

        buyer_concentration = (top_buyers_volume / total_volume) * 100
        seller_concentration = (top_sellers_volume / total_volume) * 100
        net_ratio = buyer_concentration - seller_concentration

        if net_ratio > 30 and buyer_concentration > 50:
            status = "BIG ACCUMULATION (Broker Summary)"
        elif net_ratio > 10:
            status = "ACCUMULATION (Broker Summary)"
        elif net_ratio < -30 and seller_concentration > 50:
            status = "BIG DISTRIBUTION (Broker Summary)"
        elif net_ratio < -10:
            status = "DISTRIBUTION (Broker Summary)"
        else:
            status = "NEUTRAL (Broker Summary)"

        return {
            "buyer_concentration": buyer_concentration,
            "seller_concentration": seller_concentration,
            "net_ratio": net_ratio,
            "status": status
        }
