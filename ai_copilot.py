"""
Modul AI Market Copilot:
Menjawab pertanyaan analisis pasar & saham dalam bahasa natural.
Menggabungkan data teknikal, bandarmology, valuasi fundamental, dan sentimen berita.
"""

import re
from typing import Optional
from signal_engine import analyze_ihsg, analyze_single_stock, scan_whale_watchlist
from insider_radar import get_single_stock_valuation, fetch_insider_corporate_actions
from advanced_tools import scan_sector_rotation
from config import LQ45_WATCHLIST, ALL_IDX_TICKERS

# Kata-kata 4 huruf bahasa Indonesia yang bukan ticker saham kecuali ditulis dengan hashtag misal #AMAN
STOPWORDS_ID = {
    "AMAN", "BELI", "JUAL", "DULU", "PADA", "DARI", "HARI", "AKAN", "BISA",
    "CARA", "KITA", "SAYA", "KAMU", "LALU", "SAAT", "YANG", "JIKA", "AGAR",
    "BAIK", "NAIK", "RUGI", "TREN", "ARUS", "DANA", "BAGI", "APAK", "INFO",
    "KATA", "MAU", "KIRA", "SIAP", "SOAL", "SEGI", "SUDA", "KOK", "KAPAN"
}


def extract_ticker_from_query(query: str) -> Optional[str]:
    """
    Mendeteksi kode saham IDX dari teks pertanyaan user.
    """
    # 1. Deteksi prioritas jika user menyertakan hashtag #BBCA atau $BBCA
    explicit = re.findall(r"[#$]([A-Za-z]{4})\b", query.upper())
    if explicit:
        return explicit[0]

    # 2. Deteksi saham terpopuler / LQ45 terlebih dahulu
    words = re.findall(r"\b[A-Za-z]{4}\b", query.upper())
    for w in words:
        if w in LQ45_WATCHLIST:
            return w

    # 3. Deteksi seluruh saham BEI dengan mengabaikan kata umum bahasa Indonesia
    for w in words:
        if w in STOPWORDS_ID:
            continue
        if ALL_IDX_TICKERS and w in ALL_IDX_TICKERS:
            return w

    POPULAR = {"BBCA", "BBRI", "BMRI", "BBNI", "ASII", "TLKM", "GOTO", "AMMN", "ADRO", "PTBA", "ANTM", "MEDC", "ICBP", "INDF", "UNVR", "KLBF", "BRIS", "BREN", "CUAN", "PGAS"}
    for w in words:
        if w in POPULAR:
            return w

    return None


def generate_ai_stock_consultation(ticker: str, user_question: str) -> str:
    """
    Menganalisis saham secara mendalam dan merangkum jawaban natural ala analis profesional.
    """
    stock = analyze_single_stock(ticker)
    if "error" in stock:
        return f"❌ Maaf, data untuk saham #{ticker} tidak dapat diakses saat ini: {stock['error']}"

    val = get_single_stock_valuation(ticker)
    w = stock["whale"]
    tp = stock["trading_plan"]
    price = int(stock["close"])
    pct = stock["pct_change"]
    chg_sym = "+" if pct >= 0 else ""

    # Diagnosa Trend & Momentum
    rsi = stock["rsi"]
    ema20 = stock["ema20"]
    ema50 = stock["ema50"]

    bull_points = []
    bear_points = []

    # Evaluasi Bandar
    if w["whale_score"] >= 70:
        bull_points.append(f"Akumulasi Whale sangat kuat (Skor: <b>{w['whale_score']}/100</b>, Net Flow: <b>Rp{w['whale_flow_billion']:.1f} M</b>).")
    elif w["whale_score"] <= 40:
        bear_points.append(f"Indikasi distribusi atau pelepasan barang oleh Big Money (Skor: <b>{w['whale_score']}/100</b>).")
    else:
        bull_points.append(f"Arus akumulasi netral cenderung akumulasi halus (Skor: <b>{w['whale_score']}/100</b>).")

    # Evaluasi Order Jumbo
    lot = w.get("lot_profile", {})
    jumbo = lot.get("jumbo_pct", 50)
    if jumbo >= 60:
        bull_points.append(f"Didominasi tiket order Jumbo/Institusi (<b>{jumbo}%</b> transaksi).")

    # Evaluasi Teknikal
    if price > ema20 and ema20 > ema50:
        bull_points.append("Tren Uptrend solid (Harga berada di atas EMA 20 & EMA 50).")
    elif price < ema20 and price < ema50:
        bear_points.append("Tren Downtrend jangka pendek (Harga di bawah EMA 20 & EMA 50).")

    if rsi < 35:
        bull_points.append(f"RSI di level <code>{rsi:.1f}</code> (Oversold/Jenuh Jual, potensi pantulan teknikal).")
    elif rsi > 70:
        bear_points.append(f"RSI di level <code>{rsi:.1f}</code> (Overbought/Jenuh Beli, rawan koreksi ambil untung).")

    # Evaluasi Valuasi
    if "error" not in val:
        if val["pbv"] < 1.5 and val["roe"] > 10:
            bull_points.append(f"Valuasi tergolong murah (PBV: <b>{val['pbv']}x</b> dengan ROE solid: <b>{val['roe']}%</b>).")
        if val["div_yield"] > 4.0:
            bull_points.append(f"Pemberi dividen royal (Dividend Yield: <b>{val['div_yield']}%</b>).")
        if val["pbv"] > 5.0 and val["per"] > 35:
            bear_points.append(f"Valuasi premium / sudah priced-in (PBV: <b>{val['pbv']}x</b>, PER: <b>{val['per']}x</b>).")

    # Sentimen Berita
    sent = stock.get("sentiment", {})
    if sent and sent.get("sentiment") == "BULLISH":
        bull_points.append(f"Sentimen media positif: {sent.get('catalyst_summary', '')}")
    elif sent and sent.get("sentiment") == "BEARISH":
        bear_points.append(f"Ada katalis pemberat di media: {sent.get('catalyst_summary', '')}")

    # Rekomendasi Kesimpulan
    if len(bull_points) >= len(bear_points) + 2:
        verdict = "🟢 <b>LAYAK BELI / SWING BUY (HIGH PROBABILITY)</b>"
        action_plan = (
            f"Bagus untuk swing trade. Disarankan masuk bertahap di area <code>Rp{tp['entry_area']}</code>. "
            f"Target terdekat (TP1) di <code>Rp{tp['tp1']:,}</code> dan pasang batas proteksi Stop Loss di <code>Rp{tp['stop_loss']:,}</code>."
        )
    elif len(bear_points) >= len(bull_points) + 1:
        verdict = "🔴 <b>WAIT & SEE / JANGAN TERBURU-BURU MASUK</b>"
        action_plan = (
            f"Tekanan jual dan risiko teknikal masih membayangi. "
            f"Tunggu konfirmasi pantulan di area Support kuat <code>Rp{int(stock['levels']['support_1']):,}</code> atau sinyal akumulasi balik."
        )
    else:
        verdict = "🟡 <b>NETRAL / BUY ON WEAKNESS (CICIL SANTAI)</b>"
        action_plan = (
            f"Kondisi saham sedang konsolidasi. Cocok untuk strategi Buy on Weakness mendekati support <code>Rp{int(stock['levels']['support_1']):,}</code> "
            f"dengan porsi wajar dan tidak terburu-buru all-in."
        )

    pros_str = "\n".join([f" • ✅ {p}" for p in bull_points]) if bull_points else " • Belum ada katalis teknikal signifikan."
    cons_str = "\n".join([f" • ⚠️ {c}" for c in bear_points]) if bear_points else " • Tidak terdeteksi risiko teknikal mayor saat ini."

    return (
        f"🤖 <b>AI MARKET COPILOT: KONSULTASI #{ticker}</b>\n"
        f"❓ <i>Pertanyaan: \"{user_question}\"</i>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Status Harga:</b> <code>Rp{price:,}</code> ({chg_sym}{pct:.2f}%)\n"
        f"🐋 <b>Whale Score:</b> <b>{w['whale_score']}/100</b> ({w['whale_status']})\n\n"
        f"🔍 <b>FAKTOR PENDUKUNG (BULLISH):</b>\n{pros_str}\n\n"
        f"⚠️ <b>FAKTOR RISIKO (BEARISH):</b>\n{cons_str}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>KESIMPULAN &amp; SARAN AI:</b>\n"
        f"👉 {verdict}\n\n"
        f"💡 <i>{action_plan}</i>"
    )


def answer_market_query(query: str) -> str:
    """
    Fungsi utama AI Market Copilot untuk memproses segala jenis pertanyaan user.
    """
    clean_q = query.strip()
    ticker = extract_ticker_from_query(clean_q)

    # 1. Jika menanyakan saham spesifik (contoh: "apakah aman beli BBRI?", "prospek BBCA")
    if ticker:
        return generate_ai_stock_consultation(ticker, clean_q)

    q_lower = clean_q.lower()

    # 2. Jika menanyakan kondisi IHSG / pasar umum
    if any(k in q_lower for k in ["ihsg", "market", "bursa", "kondisi pasar", "indeks"]):
        ihsg = analyze_ihsg()
        change_sym = "+" if ihsg.get("pct_change", 0) >= 0 else ""
        return (
            f"🤖 <b>AI COPILOT: DIAGNOSA PASAR IHSG</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Level IHSG:</b> <code>{ihsg.get('close', 0):,.2f}</code> ({change_sym}{ihsg.get('pct_change', 0):.2f}%)\n"
            f"📈 <b>Kondisi Tren:</b> {ihsg.get('trend_emoji', '')} <b>{ihsg.get('trend', '')}</b>\n"
            f"⚡ <b>Momentum:</b> <b>{ihsg.get('momentum', '')}</b> (RSI: <code>{ihsg.get('rsi', 0)}</code>)\n"
            f"🏛️ <b>Support / Resistance:</b> <code>{ihsg.get('support', 0):,.2f}</code> / <code>{ihsg.get('resistance', 0):,.2f}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <b>Pandangan Strategi:</b>\n"
            f"👉 <i>{ihsg.get('recommendation', 'Tetap utamakan disiplin trading dan pantau rotasi sektor.')}</i>"
        )

    # 3. Jika menanyakan rotasi sektor
    if any(k in q_lower for k in ["sektor", "rotasi", "sektor apa", "fund flow"]):
        sectors = scan_sector_rotation()
        if not sectors:
            return "⚠️ Belum dapat memuat data rotasi sektor saat ini."
        top_sec = sectors[0]
        bot_sec = sectors[-1]
        return (
            f"🤖 <b>AI COPILOT: PANDANGAN ROTASI SEKTOR</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 <b>Sektor Terkuat Hari Ini:</b>\n"
            f"• <b>{top_sec['sector']}</b> (Rata-rata: <b>{top_sec['avg_change']:+.2f}%</b>)\n"
            f"  👉 Saham Pemimpin: <b>#{top_sec['leader']}</b> ({top_sec['leader_pct']:+.2f}%)\n\n"
            f"❄️ <b>Sektor Terlemah (Laggard):</b>\n"
            f"• <b>{bot_sec['sector']}</b> (Rata-rata: <b>{bot_sec['avg_change']:+.2f}%</b>)\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <b>Tips Copilot:</b> Fokuskan transaksi pada saham berfundamental bagus di sektor yang sedang memimpin arus dana (Inflow)."
        )

    # 4. Jika menanyakan rekomendasi atau saham pilihan
    if any(k in q_lower for k in ["rekomendasi", "saham apa", "beli apa", "pilihan", "watchlist"]):
        stocks = scan_whale_watchlist(LQ45_WATCHLIST)
        top = stocks[:3]
        if not top:
            return "⚠️ Belum ada saham yang memenuhi kriteria akumulasi agresif saat ini."
        lines = [
            "🤖 <b>AI COPILOT: TOP 3 SAHAM PILIHAN AKUMULASI HARI INI</b>\n"
            "<i>Berdasarkan algoritma Whale Flow & Volume Breakout:</i>\n"
            "━━━━━━━━━━━━━━━━━━━"
        ]
        for idx, s in enumerate(top, 1):
            w = s["whale"]
            tp = s["trading_plan"]
            lines.append(
                f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['close']):,}</code>)\n"
                f"   • Alasan: Status <b>{w['whale_status']}</b> (Skor: {w['whale_score']}/100)\n"
                f"   • Rencana: Beli <code>Rp{tp['entry_area']}</code> | TP: <code>{tp['tp1']:,}</code> | SL: <code>{tp['stop_loss']:,}</code>\n"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 <i>Ketik <code>/scan KODE</code> atau gunakan tombol interaktif untuk rincian mendalam.</i>")
        return "\n".join(lines)

    # 5. Panduan penggunaan umum
    return (
        "🤖 <b>AI MARKET COPILOT SIAP MEMBANTU!</b>\n\n"
        "Anda dapat bertanya dengan bahasa bebas, contohnya:\n"
        "• <code>/tanya apakah aman beli BBRI sekarang?</code>\n"
        "• <code>/tanya bagaimana prospek dividen BBCA?</code>\n"
        "• <code>/tanya kondisi pasar IHSG hari ini bagaimana?</code>\n"
        "• <code>/tanya sektor apa yang paling menarik sekarang?</code>\n"
        "• <code>/tanya rekomendasi saham swing trade</code>\n\n"
        "Silakan ajukan pertanyaan Anda!"
    )
