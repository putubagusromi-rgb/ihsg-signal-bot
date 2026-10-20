"""
Multibagger & Rumor Catalyst Engine (IHSG / BEI):
Mendeteksi saham yang berpotensi naik ratusan persen (Multi-Bagger) dengan menggabungkan:
1. Bau Rumor & Aksi Korporasi: Akuisisi, Pengendali Baru (Konglomerat Masuk), Tender Offer, Rights Issue Jumbo.
2. Jejak Akumulasi Bandar (Whale Awakening): Unusual Volume Surge (RVOL 2.5x - 10x) di saham murah/tidur.
3. Zona Diskon Modal Bandar: Membeli sebelum berita resmi meledak di publik saat harga masih di bawah modal Whale.
"""

from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
import re
from insider_radar import fetch_insider_corporate_actions
from whale_radar import analyze_whale_footprint

MULTIBAGGER_UNIVERSE = [
    "BIPI", "BRMS", "BUMI", "DEWA", "ENRG", "PANI",
    "CUAN", "BRPT", "TPIA", "BREN", "PSAB", "DOID",
    "VKTR", "PGEO", "MEDC", "MDKA", "BFIN", "ACES",
    "BBHI", "ARTO", "DSSA", "AMMN", "ADRO", "PTBA"
]

CATALYST_KEYWORDS = {
    "akuisisi": 35,
    "caplok": 35,
    "pengendali": 30,
    "ganti pemilik": 30,
    "tender offer": 28,
    "rights issue": 25,
    "private placement": 25,
    "buyback": 20,
    "bakrie": 25,
    "salim": 25,
    "prajogo": 25,
    "aguan": 25,
    "dividen": 15,
    "laba": 15
}


def analyze_multibagger_rumor(ticker: str) -> Dict[str, Any]:
    """
    Mendiagnosis potensi Multi-Bagger berdasarkan kombinasi Rumor Aksi Korporasi & Akumulasi Bandar.
    Bisa digunakan untuk SAHAM APA SAJA di BEI.
    """
    clean = ticker.replace(".JK", "").strip().upper()

    whale_data = analyze_whale_footprint(clean)
    if "error" in whale_data:
        return {"error": whale_data["error"]}

    corporate_news = fetch_insider_corporate_actions(clean, limit=4)

    catalyst_score = 10
    detected_catalysts = []

    for item in corporate_news:
        title_lower = item["title"].lower()
        for kw, pts in CATALYST_KEYWORDS.items():
            if kw in title_lower and kw not in [c["keyword"] for c in detected_catalysts]:
                catalyst_score += pts
                detected_catalysts.append({
                    "keyword": kw.upper(),
                    "title": item["title"],
                    "category": item["category"],
                    "badge": item["badge"]
                })

    catalyst_score = min(40, catalyst_score)

    rvol = whale_data.get("rvol", 1.0)
    vol_score = 10
    if rvol >= 3.0:
        vol_score = 35
    elif rvol >= 2.0:
        vol_score = 25
    elif rvol >= 1.4:
        vol_score = 15

    pct_vwap = whale_data.get("pct_diff_vwap20", 0)
    cost_score = 10
    if pct_vwap < -10.0:
        cost_score = 25
    elif pct_vwap < -2.0:
        cost_score = 18
    elif abs(pct_vwap) <= 5.0:
        cost_score = 12

    total_mb_score = min(98, catalyst_score + vol_score + cost_score)

    close = whale_data.get("close", 0)
    vwap20 = whale_data.get("vwap_20d", close)
    cmf20 = whale_data.get("cmf_20", 0)

    if total_mb_score >= 80 and pct_vwap < 0:
        phase = "🚀 FASE 1: AKUMULASI SENYAP & RUMOR AWAL"
        phase_badge = "🔥 <b>ULTRA POTENSI MULTI-BAGGER (TITIK MASUK EMAS)</b>"
        verdict = (
            "Bandar sedang memborong besar-besaran di harga diskon sebelum kabar aksi korporasi/akuisisi "
            "diumumkan secara resmi ke publik. Ini adalah fase di mana potensi kenaikan ratusan persen dimulai!"
        )
        action = f"Cicil Beli (Buy on Weakness) di kisaran Rp{int(close):,}. Pasang target bertahap."
    elif total_mb_score >= 70 and rvol >= 2.0:
        phase = "⚡ FASE 2: MARK-UP BRUTAL & RUMOR MULAI RAMAI"
        phase_badge = "🚀 <b>MOMENTUM FLYING (IKUTI ARUS BANDAR)</b>"
        verdict = (
            "Volume meledak tinggi dan rumor mulai tersebar di pasar. Saham sedang dalam fase tarikan cepat. "
            "Ikuti tren momentum dengan trailing stop ketat."
        )
        action = f"Buy on Breakout / Ride the Trend. Pasang Stop Loss ketat di Rp{int(whale_data['sl']):,}."
    elif pct_vwap > 25.0:
        phase = "⚠️ FASE 3: DISTRIBUSI PUCUK (SELL ON NEWS)"
        phase_badge = "🔴 <b>WASPADA JEBAKAN RETAIL (DISTRIBUSI)</b>"
        verdict = (
            "Harga saham sudah naik sangat tinggi dan berita aksi korporasi sudah ramai di media massa. "
            "Hati-hati! Bandar biasanya memanfaatkan euforia retail untuk melepas barang."
        )
        action = "Amankan profit (Take Profit) bertahap. Jangan FOMO membeli di pucuk!"
    else:
        phase = "⏳ FASE KONSOLIDASI / MENUNGGU KATALIS"
        phase_badge = "⚪ <b>OBSERVASI & MASUK WATCHLIST</b>"
        verdict = "Ada aktivitas pergerakan, namun butuh konfirmasi lonjakan volume bandar yang lebih masif."
        action = f"Pantau pergerakan antrean dan akumulasi di level support Rp{int(whale_data['sup_20']):,}."

    return {
        "ticker": clean,
        "close": close,
        "vwap_20d": vwap20,
        "pct_diff_vwap20": pct_vwap,
        "rvol": rvol,
        "cmf_20": cmf20,
        "mb_score": total_mb_score,
        "phase": phase,
        "phase_badge": phase_badge,
        "verdict": verdict,
        "action": action,
        "cost_status": whale_data["cost_status"],
        "tp1": whale_data["tp1"],
        "tp2": whale_data["tp2"],
        "sl": whale_data["sl"],
        "news": corporate_news[:3],
        "catalysts": detected_catalysts
    }


def scan_top_multibagger_picks(limit: int = 5, watchlist: Optional[List[str]] = None, max_workers: int = 8) -> List[Dict[str, Any]]:
    """
    Memindai semesta saham Multi-Bagger secara paralel untuk mencari kandidat terbaik.
    """
    tickers = watchlist or MULTIBAGGER_UNIVERSE
    results = []

    def _worker(t):
        try:
            return analyze_multibagger_rumor(t)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        raw_list = list(ex.map(_worker, tickers))

    for r in raw_list:
        if r and "error" not in r:
            results.append(r)

    results.sort(key=lambda x: x["mb_score"], reverse=True)
    return results[:limit]
