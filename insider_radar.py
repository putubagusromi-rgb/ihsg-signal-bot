"""
Modul Radar Insider & Deep Value Screener untuk Saham IDX
1. INSIDER RADAR (/insider): Memantau aksi korporasi, akuisisi, dividen interim, dan transaksi orang dalam.
2. DEEP VALUE SCREENER (/undervalued): Memindai saham-saham 'Mercy Harga Avanza' (PBV murah, PER rendah, fundamental kuat).
"""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
from typing import Dict, Any, List
import yfinance as yf

def clean_ticker(s: str) -> str:
    s = s.strip().upper()
    if s.startswith("^"):
        return s
    return s if s.endswith(".JK") else f"{s}.JK"


def fetch_insider_corporate_actions(limit: int = 5) -> List[Dict[str, str]]:
    query = "saham keterbukaan informasi OR akuisisi OR dividen OR tender offer OR buyback"
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=id&gl=ID&ceid=ID:id"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    actions = []
    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            tree = ET.fromstring(response.read())
            for item in tree.findall(".//item")[:limit]:
                title = item.find("title").text if item.find("title") is not None else ""
                pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""

                clean_title = re.sub(r"\s*-\s*[^-]+$", "", title)
                source_match = re.search(r"-\s*([^-]+)$", title)
                source = source_match.group(1).strip() if source_match else "IDX News"

                t_lower = title.lower()
                if "akuisisi" in t_lower or "caplok" in t_lower:
                    cat = "🤝 AKUISISI / M&A"
                    badge = "🔥"
                elif "dividen" in t_lower:
                    cat = "💰 DIVIDEN JUMBO"
                    badge = "💵"
                elif "buyback" in t_lower:
                    cat = "🛒 BUYBACK EMITEN"
                    badge = "💎"
                elif "tender offer" in t_lower or "pengendali" in t_lower:
                    cat = "👑 GANTI PENGENDALI"
                    badge = "🚀"
                else:
                    cat = "📢 KETERBUKAAN INFO"
                    badge = "📌"

                actions.append({
                    "badge": badge,
                    "category": cat,
                    "title": clean_title,
                    "source": source,
                    "date": pub_date[:16] if pub_date else ""
                })
    except Exception as e:
        print(f"[Insider Error] {e}")

    return actions


def scan_undervalued_stocks(tickers: List[str], limit: int = 5) -> List[Dict[str, Any]]:
    results = []
    for sym in tickers[:15]:
        try:
            formatted = sym.upper() + ".JK" if not sym.endswith(".JK") else sym.upper()
            t = yf.Ticker(formatted)
            info = t.info
            
            pbv = info.get("priceToBook")
            per = info.get("trailingPE")
            div_yield = info.get("dividendYield", 0)
            roe = info.get("returnOnEquity", 0)
            current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

            if pbv and pbv > 0 and per and per > 0:
                if pbv < 2.0 and per < 15:
                    discount_score = int(max(10, min(99, (2.0 - pbv) * 35 + (15 - per) * 2)))

                    # Normalisasi Dividend Yield
                    formatted_div = 0.0
                    if div_yield:
                        formatted_div = round(div_yield if div_yield <= 100 else div_yield / 100, 2)
                        if formatted_div < 1.0 and formatted_div > 0:
                            formatted_div = round(formatted_div * 100, 2)

                    # Normalisasi ROE
                    formatted_roe = 0.0
                    if roe:
                        formatted_roe = round(roe * 100 if roe < 1.0 else roe, 1)

                    results.append({
                        "ticker": sym.replace(".JK", ""),
                        "price": current_price,
                        "pbv": round(pbv, 2),
                        "per": round(per, 2),
                        "div_yield": formatted_div,
                        "roe": formatted_roe,
                        "discount_score": discount_score
                    })
        except Exception:
            continue

    results.sort(key=lambda x: x["discount_score"], reverse=True)
    return results[:limit]
