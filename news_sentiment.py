"""
Modul Analisis Sentimen Berita Saham IDX (Katalis Pasar & Rumor Bandar)
Mengambil berita terkini dari Google News Indonesia (CNBC, Kontan, Bisnis, Emitennews, dll.)
dan menganalisis skor bau sentimen pasar (Positif, Netral, Negatif).
"""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Dict, Any, List
import re

BULLISH_KEYWORDS = [
    "laba", "melonjak", "meroket", "naik", "tumbuh", "rekor", "dividen", "jumbo",
    "akuisisi", "ekspansi", "kontrak baru", "buyback", "prospek cerah", "rebound",
    "akumulasi", "target harga", "bullish", "inflow", "asing borong", "moncer",
    "optimis", "melesat", "kinerja positif", "raih pinjaman", "rights issue"
]

BEARISH_KEYWORDS = [
    "rugi", "anjlok", "turun", "merosot", "jatuh", "tertekan", "pkpu", "suspensi",
    "gugatan", "mundur", "utang", "beban", "gagal bayar", "investigasi", "bearish",
    "outflow", "asing lepas", "distribusi", "waspada", "pangkas target",
    "sanksi", "kecewa", "delisting", "tekanan jual"
]


def fetch_stock_news(ticker: str, limit: int = 3) -> List[Dict[str, str]]:
    clean_ticker = ticker.replace(".JK", "").strip().upper()
    query = f"saham {clean_ticker}"
    encoded_query = urllib.parse.quote(query)
    
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=id&gl=ID&ceid=ID:id"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )

    news_items = []
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall(".//item")[:limit]:
                title = item.find("title").text if item.find("title") is not None else ""
                pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                
                clean_title = re.sub(r"\s*-\s*[^-]+$", "", title)
                source_match = re.search(r"-\s*([^-]+)$", title)
                source = source_match.group(1).strip() if source_match else "Media"
                date_part = pub_date[:16] if pub_date else ""

                news_items.append({
                    "title": clean_title,
                    "source": source,
                    "date": date_part,
                    "full_title": title
                })
    except Exception as e:
        print(f"[News Error] Gagal fetch berita {clean_ticker}: {e}")

    return news_items


def analyze_news_sentiment(ticker: str) -> Dict[str, Any]:
    news_list = fetch_stock_news(ticker, limit=4)
    if not news_list:
        return {
            "has_news": False,
            "sentiment": "NETRAL (SEPI BERITA)",
            "sentiment_score": 50,
            "badge": "⚪ SEPI",
            "catalyst_summary": "Tidak ada berita besar terkini. Jika volume naik, ini tanda akumulasi senyap (Silent Accumulation).",
            "headlines": []
        }

    positive_count = 0
    negative_count = 0

    headlines_analyzed = []
    for item in news_list:
        title_lower = item["full_title"].lower()
        score = 0
        
        for word in BULLISH_KEYWORDS:
            if word in title_lower:
                score += 1
        for word in BEARISH_KEYWORDS:
            if word in title_lower:
                score -= 1

        if score > 0:
            tag = "🟢"
            positive_count += 1
        elif score < 0:
            tag = "🔴"
            negative_count += 1
        else:
            tag = "⚪"

        headlines_analyzed.append({
            "tag": tag,
            "title": item["title"],
            "source": item["source"],
            "date": item["date"]
        })

    total = positive_count + negative_count
    if total == 0:
        sentiment = "NETRAL"
        sentiment_score = 50
        badge = "🟡 NETRAL"
        catalyst = "Sentimen pemberitaan berimbang/netral. Perhatikan murni pergerakan teknikal & volume bandar."
    elif positive_count > negative_count:
        sentiment = "POSITIF (KATALIS KUAT)"
        sentiment_score = min(95, 60 + (positive_count * 15))
        badge = "🟢 POSITIF"
        catalyst = "Ada bau sentimen positif/rumor bagus di media yang bisa dijadikan bahan bakar bandar mengangkat harga."
    else:
        sentiment = "NEGATIF (WASPADA)"
        sentiment_score = max(10, 40 - (negative_count * 15))
        badge = "🔴 NEGATIF"
        catalyst = "Pemberitaan bernada hati-hati/negatif. Waspadai risiko distribusi barang oleh bandar."

    return {
        "has_news": True,
        "sentiment": sentiment,
        "sentiment_score": sentiment_score,
        "badge": badge,
        "catalyst_summary": catalyst,
        "headlines": headlines_analyzed
    }
