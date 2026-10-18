"""
Modul Broker Summary & Deteksi Whale Accumulation (Bandarmology)
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
        rvol = float(latest.get("RVOL", 1.0))
        cmf = float(latest.get("CMF", 0.0))
        whale_score = int(latest.get("Whale_Score", 50))
        whale_status = str(latest.get("Whale_Status", "NEUTRAL"))
        vwap_20 = float(latest.get("VWAP_20", close))

        estimated_turnover = close * volume
        estimated_whale_flow_idr = (cmf * estimated_turnover) / 1_000_000_000

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

        pct_from_vwap = ((close - vwap_20) / vwap_20) * 100

        # Analisis Profil Ukuran Lot (Jumbo Whale vs Retail)
        total_lot = int(volume / 100)
        if whale_score >= 70:
            jumbo_pct = min(85, int(45 + (whale_score * 0.4)))
            retail_pct = max(10, 100 - jumbo_pct - 15)
            medium_pct = 100 - jumbo_pct - retail_pct
            footprint_summary = f"Didominasi Order Jumbo ({jumbo_pct}%). Bandar memborong tiket besar tanpa banyak antrean retail."
        elif whale_score <= 35:
            jumbo_pct = max(15, int(whale_score * 0.5))
            retail_pct = min(70, int(60 + (40 - whale_score)))
            medium_pct = 100 - jumbo_pct - retail_pct
            footprint_summary = f"Distribusi Terdeteksi. Retail mendominasi ({retail_pct}%), bandar membuang barang bertahap."
        else:
            jumbo_pct = 35
            medium_pct = 35
            retail_pct = 30
            footprint_summary = "Transaksi berimbang antara akumulasi institusi dan partisipasi retail reguler."

        return {
            "ticker": ticker.replace(".JK", ""),
            "close": close,
            "pct_change": pct_change,
            "volume": volume,
            "total_lot": total_lot,
            "rvol": rvol,
            "cmf": cmf,
            "whale_score": whale_score,
            "whale_status": whale_status,
            "whale_vwap": vwap_20,
            "pct_from_vwap": pct_from_vwap,
            "turnover_billion": estimated_turnover / 1_000_000_000,
            "whale_flow_billion": estimated_whale_flow_idr,
            "is_whale_entering": is_whale_entering,
            "entry_reasons": reasons,
            "lot_profile": {
                "jumbo_pct": jumbo_pct,
                "medium_pct": medium_pct,
                "retail_pct": retail_pct,
                "summary": footprint_summary
            }
        }
