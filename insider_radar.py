"""
Modul Radar Insider & Deep Value Screener untuk Saham IDX
1. INSIDER RADAR (/insider [KODE]): Memantau aksi korporasi, akuisisi, dividen interim, dan transaksi orang dalam.
2. DEEP VALUE SCREENER (/undervalued [KODE]): Memindai saham murah (PBV & PER rendah) per sektor / saham tunggal.
3. DIVIDEN RADAR (/dividen): Memindai saham dengan dividend yield tertinggi di bursa.
"""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
from typing import Dict, Any, List, Optional
import yfinance as yf

def clean_ticker(s: str) -> str:
    s = s.strip().upper()
    if s.startswith("^"):
        return s
    return s if s.endswith(".JK") else f"{s}.JK"

def fetch_insider_corporate_actions(ticker: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    if ticker:
        clean = ticker.replace(".JK", "").strip().upper()
        query = f"saham {clean} keterbukaan informasi OR akuisisi OR dividen OR buyback OR pengendali"
    else:
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

                t_lower = clean_title.lower()
                badge = "💎"
                if "akuisisi" in t_lower or "merger" in t_lower or "caplok" in t_lower:
                    cat = "🤝 AKUISISI / M&A"
                    badge = "💎"
                elif "dividen" in t_lower:
                    cat = "💰 DIVIDEN"
                    badge = "💎"
                elif "buyback" in t_lower:
                    cat = "🛒 BUYBACK EMITEN"
                    badge = "💎"
                elif "tender offer" in t_lower or "pengendali" in t_lower:
                    cat = "👑 GANTI PENGENDALI"
                    badge = "💎"
                else:
                    cat = "📢 KETERBUKAAN INFO"
                    badge = "💎"

                actions.append({
                    "badge": badge,
                    "category": cat,
                    "title": clean_title,
                    "source": source,
                    "date": pub_date[:16] if pub_date else "Hari ini"
                })
    except Exception as e:
        print(f"[Insider Error] {e}")

    return actions

def get_single_stock_valuation(ticker: str) -> Dict[str, Any]:
    clean = ticker.replace(".JK", "").strip().upper()
    formatted = clean_ticker(clean)

    try:
        t = yf.Ticker(formatted)
        info = t.info

        pbv = info.get("priceToBook")
        per = info.get("trailingPE")
        div_yield = info.get("dividendYield", 0)
        roe = info.get("returnOnEquity", 0)
        sector = info.get("sector", "General")
        price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

        if not pbv or not per:
            return {"error": f"Data fundamental #{clean} tidak lengkap."}

        formatted_div = 0.0
        if div_yield:
            formatted_div = round(div_yield if div_yield <= 100 else div_yield / 100, 2)
            if 0 < formatted_div < 1.0:
                formatted_div = round(formatted_div * 100, 2)

        formatted_roe = round(roe * 100 if roe and roe < 1.0 else (roe or 0), 1)

        status = "WAJAR"
        verdict = "Valuasi berada di rata-rata industri."
        if pbv < 1.0 and per < 10:
            status = "SANGAT DISKON (DEEP VALUE)"
            verdict = "Kategori Mercy Harga Avanza! Sangat murah secara aset dan laba."
        elif pbv < 1.5 and per < 15:
            status = "UNDERVALUED (MURAH)"
            verdict = "Harga berada di bawah rata-rata historisnya."
        elif pbv > 3.0 or per > 25:
            status = "PREMIUM / OVERVALUED"
            verdict = "Pasar menghargai pertumbuhan tinggi, risiko koreksi jika laba meleset."

        return {
            "ticker": clean,
            "price": price,
            "sector": sector,
            "pbv": round(pbv, 2),
            "per": round(per, 2),
            "roe": formatted_roe,
            "dividend_yield": formatted_div,
            "market_cap_t": round(info.get("marketCap", 0) / 1e12, 2),
            "status": status,
            "verdict": verdict
        }
    except Exception as e:
        return {"error": f"Gagal mengambil fundamental #{clean}: {e}"}

def scan_undervalued_stocks(tickers: List[str], limit: int = 5) -> List[Dict[str, Any]]:
    candidates = []
    for sym in tickers:
        try:
            formatted = clean_ticker(sym)
            t = yf.Ticker(formatted)
            info = t.info

            pbv = info.get("priceToBook")
            per = info.get("trailingPE")
            div_yield = info.get("dividendYield", 0)
            roe = info.get("returnOnEquity", 0)
            sector = info.get("sector", "General")
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

            if pbv and pbv > 0 and per and per > 0:
                if pbv < 2.0 and per < 15:
                    discount_score = int(max(10, min(99, (2.0 - pbv) * 35 + (15 - per) * 2)))

                    formatted_div = 0.0
                    if div_yield:
                        formatted_div = round(div_yield if div_yield <= 100 else div_yield / 100, 2)
                        if 0 < formatted_div < 1.0:
                            formatted_div = round(formatted_div * 100, 2)

                    formatted_roe = round(roe * 100 if roe and roe < 1.0 else (roe or 0), 1)

                    candidates.append({
                        "ticker": sym.replace(".JK", ""),
                        "price": price,
                        "sector": sector,
                        "pbv": round(pbv, 2),
                        "per": round(per, 2),
                        "roe": formatted_roe,
                        "div_yield": formatted_div,
                        "discount_score": discount_score
                    })
        except Exception:
            continue

    candidates.sort(key=lambda x: x["discount_score"], reverse=True)
    return candidates[:limit]

def scan_high_dividend_stocks(tickers: List[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    CASH_COWS = [
        "BSSR.JK", "ITMG.JK", "PTBA.JK", "BBRI.JK", "BMRI.JK",
        "BJTM.JK", "BJBR.JK", "HEXA.JK", "ADRO.JK", "ASII.JK",
        "TLKM.JK", "PGAS.JK", "MPMX.JK", "BBNI.JK"
    ]
    check_list = tickers if tickers and len(tickers) > 0 else CASH_COWS
    results = []

    for sym in check_list[:14]:
        try:
            formatted = clean_ticker(sym)
            t = yf.Ticker(formatted)
            info = t.info
            div_yield = info.get("dividendYield", 0)
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            dr = info.get("dividendRate", 0)

            if div_yield:
                formatted_div = round(div_yield if div_yield <= 100 else div_yield / 100, 2)
                if 0 < formatted_div < 1.0:
                    formatted_div = round(formatted_div * 100, 2)

                if formatted_div >= 4.0:
                    cat = "Super Jumbo (>10%)" if formatted_div >= 10.0 else "Solid Cash Cow (>5%)"
                    div_val = int(dr) if dr else int(price * formatted_div / 100)
                    results.append({
                        "ticker": sym.replace(".JK", ""),
                        "price": int(price),
                        "yield": formatted_div,
                        "dividend_value": div_val,
                        "category": cat,
                        "per": round(info.get("trailingPE", 0), 1) if info.get("trailingPE") else 0
                    })
        except Exception:
            continue

    results.sort(key=lambda x: x["yield"], reverse=True)
    return results[:limit]

def format_dividend_hunter_message(stocks: List[Dict[str, Any]], actions: List[Dict[str, Any]] = None) -> str:
    lines = [
        "💰 <b>DIVIDEND HUNTER &amp; CASH COW SCREENER</b> 👑",
        "<i>Saham-saham dengan pembagian dividen tunai paling royal di Bursa IDX:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    for idx, s in enumerate(stocks[:5], 1):
        lines.append(
            f"<b>{idx}. #{s['ticker']}</b> (<code>Rp {s['price']:,}</code>)\n"
            f"   • 💸 <b>Estimasi Yield :</b> <b>{s['yield']}%</b> | Nilai: <code>Rp {s['dividend_value']:,}/lbr</code>\n"
            f"   • 🏷️ <b>Kategori       :</b> <b>{s['category']}</b> (PER: {s['per']}x)\n"
        )

    if actions:
        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.append("📅 <b>RADAR AKSI KORPORASI &amp; BUYBACK TERKINI:</b>")
        for a in actions[:3]:
            lines.append(f"• {a['badge']} <b>{a['category']}:</b> {a['title']} <i>({a['source']})</i>")

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append(
        "💡 <b>TIPS DIVIDEND HUNTER:</b>\n"
        "• <i>Waspadai 'Dividend Trap' (harga anjlok pasca Ex-Date).\n"
        "• Waktu terbaik akumulasi adalah 1-2 bulan sebelum Cum-Date saat harga di area Support!</i>"
    )
    return "\n".join(lines)
