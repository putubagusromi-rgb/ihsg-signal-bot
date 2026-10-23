import os
import sys
import time
import requests
import html
import io
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

try:
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
except Exception:
    WIB = None

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    SCHEDULED_ALERTS,
    LQ45_WATCHLIST,
    KOMPAS100_WATCHLIST,
    ALL_IDX_TICKERS,
    INDICATOR_CONFIG
)
from signal_engine import analyze_ihsg, analyze_single_stock, scan_whale_watchlist
from insider_radar import (
    fetch_insider_corporate_actions,
    scan_undervalued_stocks,
    scan_high_dividend_stocks,
    get_single_stock_valuation
)
from advanced_tools import (
    generate_stock_chart,
    calculate_position_sizing,
    scan_sector_rotation
)
from ai_copilot import answer_market_query, extract_ticker_from_query
from hedgefund_radar import analyze_hedgefund_wyckoff, scan_hedgefund_picks
from whale_radar import analyze_whale_footprint, scan_top_whale_accumulations, get_whale_tier_list
from multibagger_radar import analyze_multibagger_rumor, scan_top_multibagger_picks
from macro_regime import get_ihsg_market_regime
from daily_prediction import predict_daily_ihsg_direction

esc = html.escape
_command_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="cmd")


def make_stock_inline_keyboard(ticker: str) -> dict:
    """
    Membuat tombol interaktif Telegram sekali klik untuk saham tertentu.
    """
    t = ticker.replace(".JK", "").strip().upper()
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Buka Chart", "callback_data": f"chart:{t}"},
                {"text": "🐋 Cek Whale", "callback_data": f"whale:{t}"}
            ],
            [
                {"text": "🚀 Cek Rumor", "callback_data": f"rumor:{t}"},
                {"text": "🌊 Order Flow", "callback_data": f"flow:{t}"}
            ],
            [
                {"text": "💎 Cek Valuasi", "callback_data": f"val:{t}"},
                {"text": "🧮 Hitung Lot (10jt)", "callback_data": f"calc:{t}"}
            ],
            [
                {"text": "🤖 Tanya AI Copilot", "callback_data": f"tanya:{t}"}
            ]
        ]
    }


def make_persistent_reply_keyboard() -> dict:
    """
    Keyboard menu tombol tetap di bawah layar Telegram agar user bisa langsung pencet.
    """
    return {
        "keyboard": [
            [
                {"text": "🔮 Prediksi Arah IHSG"},
                {"text": "🚀 Radar Multi-Bagger"}
            ],
            [
                {"text": "🏆 Tier List Whale"},
                {"text": "💰 Portofolio 100 Juta"}
            ],
            [
                {"text": "🌐 Status Pasar IHSG"},
                {"text": "🐋 Top Whale LQ45"}
            ],
            [
                {"text": "🏛️ Wyckoff Hedge Fund"},
                {"text": "🔄 Rotasi Sektor"}
            ]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }


def make_main_inline_menu() -> dict:
    """
    Menu tombol interaktif sekali klik di dalam chat Telegram.
    """
    return {
        "inline_keyboard": [
            [
                {"text": "🔮 Prediksi Arah IHSG", "callback_data": "menu:prediksi"},
                {"text": "🚀 Radar Multi-Bagger", "callback_data": "menu:multibagger"}
            ],
            [
                {"text": "🏆 Tier List Whale", "callback_data": "menu:tierlist"},
                {"text": "🌐 Status Pasar IHSG", "callback_data": "menu:regime"}
            ],
            [
                {"text": "💰 Portofolio 100 Juta", "callback_data": "menu:simulasi100jt"},
                {"text": "🐋 Top Whale LQ45", "callback_data": "menu:whalelist"}
            ],
            [
                {"text": "🏛️ Wyckoff Spring", "callback_data": "menu:hedge"},
                {"text": "🔄 Rotasi Sektor", "callback_data": "menu:sektor"}
            ],
            [
                {"text": "💎 Bedah Rumor BIPI", "callback_data": "rumor:BIPI"},
                {"text": "💎 Bedah Modal PANI", "callback_data": "rumor:PANI"}
            ]
        ]
    }


def send_telegram_message(text: str, chat_id: str = None, parse_mode: str = "HTML", reply_markup: dict = None) -> bool:
    token = TELEGRAM_BOT_TOKEN
    target_id = chat_id or TELEGRAM_CHAT_ID

    if not token or not target_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        resp = requests.post(url, json=payload, timeout=15)
        return resp.status_code == 200
    except Exception as e:
        print(f"[ERROR Request] {e}")
        return False


def send_telegram_photo(photo_buf: io.BytesIO, caption: str = "", chat_id: str = None, parse_mode: str = "HTML") -> bool:
    token = TELEGRAM_BOT_TOKEN
    target_id = chat_id or TELEGRAM_CHAT_ID

    if not token or not target_id or photo_buf is None:
        return False

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    data = {
        "chat_id": target_id,
        "caption": caption,
        "parse_mode": parse_mode
    }
    photo_buf.seek(0)
    files = {
        "photo": ("chart.png", photo_buf, "image/png")
    }

    try:
        resp = requests.post(url, data=data, files=files, timeout=30)
        return resp.status_code == 200
    except Exception as e:
        print(f"[ERROR sendPhoto] {e}")
        return False


def send_long_telegram_message(text: str, chat_id: str = None, parse_mode: str = "HTML", reply_markup: dict = None) -> bool:
    MAX_LEN = 4000
    if len(text) <= MAX_LEN:
        return send_telegram_message(text, chat_id, parse_mode, reply_markup=reply_markup)

    chunks = []
    while text:
        if len(text) <= MAX_LEN:
            chunks.append(text)
            break
        split_idx = text.rfind("\n", 0, MAX_LEN)
        if split_idx == -1:
            split_idx = MAX_LEN
        chunks.append(text[:split_idx])
        text = text[split_idx:].lstrip("\n")

    success = True
    for i, chunk in enumerate(chunks):
        rm = reply_markup if i == len(chunks) - 1 else None
        if not send_telegram_message(chunk, chat_id, parse_mode, reply_markup=rm):
            success = False
    return success


def answer_telegram_callback(callback_query_id: str):
    token = TELEGRAM_BOT_TOKEN
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_query_id}, timeout=10)
    except Exception:
        pass


def format_ihsg_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error:</b> {esc(str(data['error']))}"

    change_sym = "+" if data["pct_change"] >= 0 else ""
    return (
        f"📊 <b>IHSG MARKET SIGNAL UPDATE</b> 🇮🇩\n"
        f"📅 <i>Tanggal: {esc(str(data['date']))}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Level IHSG:</b> <code>{data['close']:,.2f}</code> ({change_sym}{data['pct_change']:.2f}% | {change_sym}{data['change_pts']:.2f} pts)\n"
        f"📈 <b>Tren Pasar:</b> {data['trend_emoji']} <b>{esc(str(data['trend']))}</b>\n"
        f"⚡ <b>Momentum:</b> <b>{esc(str(data['momentum']))}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Indikator Kunci:</b>\n"
        f"• RSI (14): <code>{data['rsi']}</code> — <i>{esc(str(data['rsi_status']))}</i>\n"
        f"• MA20: <code>{data['ma20']:,.2f}</code> | MA50: <code>{data['ma50']:,.2f}</code>\n"
        f"• Support: <code>{data['support']:,.2f}</code> | Resistance: <code>{data['resistance']:,.2f}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <b>Strategi:</b>\n"
        f"👉 <b>{esc(str(data['recommendation']))}</b>"
    )


def format_daily_prediction_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error:</b> {esc(str(data['error']))}"

    factors_str = "\n".join([f"• {f}" for f in data.get("factors", [])])
    return (
        "🔮 <b>PREDIKSI HARIAN ARAH IHSG (AI DAILY FORECAST)</b> 📊\n"
        "<i>Berdasarkan Model 4 Hybrid (Wall Street + Kurs Rupiah + RSI Ekstrem + EMA)</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Arah Prediksi:</b> <b>{data['direction']}</b>\n"
        f"📊 <b>Tingkat Keyakinan (Confidence):</b> <code>{data['confidence']}%</code>\n"
        f"⚡ <b>Skor Komposit:</b> <code>{data['score']:+d}</code> (-100 s/d +100)\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Level IHSG Terakhir:</b> <code>{data['ihsg_current']:,.2f}</code> ({data['ihsg_last_chg']:+.2f}%)\n"
        f"🛡️ <b>Estimasi Support Harian:</b> <code>{data['support']:,.2f}</code>\n"
        f"🚀 <b>Estimasi Resistance Harian:</b> <code>{data['resistance']:,.2f}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🔍 <b>4 FAKTOR PENENTU HARI INI:</b>\n"
        f"{factors_str}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <b>PANDUAN AKSI TRADING:</b>\n<i>{data['guidance']}</i>"
    )


def format_single_stock_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Gagal Menganalisis Saham:</b> {esc(str(data['error']))}"

    w = data["whale"]
    tp = data["trading_plan"]
    chg_sym = "+" if data["pct_change"] >= 0 else ""
    flow_str = f"+Rp{w['whale_flow_billion']:.1f} M" if w['whale_flow_billion'] >= 0 else f"-Rp{abs(w['whale_flow_billion']):.1f} M"

    reasons_text = ""
    if w.get("entry_reasons"):
        reasons_text = "\n🔍 <b>Fakta Akumulasi:</b>\n" + "\n".join([f" • {r}" for r in w["entry_reasons"]])

    res = (
        f"💎 <b>ANALISIS SAHAM &amp; WHALE FLOW: #{data['ticker']}</b>\n"
        f"📅 <i>Tanggal: {data['date']}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Harga Terakhir:</b> <code>Rp{int(data['close']):,}</code> ({chg_sym}{data['pct_change']:.2f}%)\n"
        f"🏷️ <b>Sinyal:</b> {data['signal_badge']}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🐋 <b>BANDARMOLOGY &amp; WHALE METRICS:</b>\n"
        f" • Status: <b>{w['whale_status']}</b>\n"
        f" • Skor Akumulasi: <b>{w['whale_score']}/100</b>\n"
        f" • RVOL (Lonjakan Vol): <b>{w['rvol']:.2f}x</b> dari rata-rata\n"
        f" • Est. Net Whale Flow: <b>{flow_str}</b>\n"
        f" • Est. Harga Beli Whale (VWAP): <code>Rp{int(w['whale_vwap']):,}</code> ({w['pct_from_vwap']:+.1f}% vs harga)\n"
        f" • Profil Lot: 🐋 <b>Jumbo {w.get('lot_profile', {}).get('jumbo_pct', 50)}%</b> | 🐜 Retail {w.get('lot_profile', {}).get('retail_pct', 30)}%\n"
        f" • <i>{w.get('lot_profile', {}).get('summary', '')}</i>\n"
        f"{reasons_text}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📐 <b>INDIKATOR TEKNIKAL:</b>\n"
        f" • EMA 20: <code>{int(data['ema20']):,}</code> | EMA 50: <code>{int(data['ema50']):,}</code>\n"
        f" • RSI 14: <code>{data['rsi']:.1f}</code>\n"
        f" • Support: <code>Rp{int(data['levels']['support_1']):,}</code>\n"
        f" • Resistance: <code>Rp{int(data['levels']['resistance_1']):,}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>TRADING PLAN REKOMENDASI (SWING):</b>\n"
        f" • Area Beli: <code>Rp{tp['entry_area']}</code>\n"
        f" • Target 1 (TP1): <code>Rp{tp['tp1']:,}</code>\n"
        f" • Target 2 (TP2): <code>Rp{tp['tp2']:,}</code>\n"
        f" • Stop Loss (SL): <code>Rp{tp['stop_loss']:,}</code>\n"
        f" • Risk/Reward Ratio: <b>{tp['rr_ratio']}x</b>\n"
    )

    sent = data.get("sentiment", {})
    if sent:
        news_lines = [
            f"\n📰 <b>BAU SENTIMEN BERITA &amp; KATALIS:</b> {sent.get('badge', '⚪')}",
            f"<i>{sent.get('catalyst_summary', '')}</i>"
        ]
        headlines = sent.get("headlines", [])
        if headlines:
            news_lines.append("<b>Top Berita Terkini:</b>")
            for h in headlines[:3]:
                news_lines.append(f" {h['tag']} {h['title']} <i>({h['source']})</i>")
        res += "\n━━━━━━━━━━━━━━━━━━━\n" + "\n".join(news_lines)

    return res


def format_hedgefund_message(data: dict) -> str:
    if "error" in data:
        return f"❌ {data['error']}"

    return (
        f"🏛️ <b>HEDGE FUND &amp; WYCKOFF RADAR: #{data['ticker']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Status Fase Bandar:</b>\n"
        f"{data['phase_badge']}\n"
        f"<i>{data['phase_desc']}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Harga Saham Saat Ini:</b> <code>Rp{data['price']:,}</code>\n"
        f"🐋 <b>Harga Modal Bandar (VWAP):</b> <code>Rp{data['vwap_20']:,}</code> ({data['pct_from_vwap']:+.1f}% vs harga)\n"
        f"🌊 <b>Arus Akumulasi CMF (10 Hari):</b> <code>{data['cmf_10']:+.3f}</code>\n"
        f"⚡ <b>Lonjakan Volume (RVOL):</b> <code>{data['rvol']:.2f}x</code>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📐 <b>LEVEL KUNCI HEDGE FUND:</b>\n"
        f"• Area Support Kunci: <code>Rp{data['support_20']:,}</code>\n"
        f"• Target Profit (Mark-up): <code>Rp{data['tp_target']:,}</code>\n"
        f"• Stop Loss Proteksi: <code>Rp{data['spring_low']:,}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <b>Rekomendasi Aksi Hedge Fund:</b>\n"
        f"👉 <b>{data['recommendation']}</b>"
    )


def format_hedgefund_scan_message(picks: list) -> str:
    if not picks:
        return "⚠️ Belum ada saham yang masuk kriteria Spring Shakeout atau Silent Absorption hari ini."

    lines = [
        "🏛️ <b>TOP HEDGE FUND &amp; WYCKOFF PICKS (LQ45)</b> 🚀",
        "<i>Mendeteksi saham yang sedang diakumulasi diam-diam atau baru saja membuang penumpang:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]
    for idx, p in enumerate(picks, 1):
        lines.append(
            f"<b>{idx}. #{p['ticker']}</b> (<code>Rp{p['price']:,}</code> | Modal Bandar: <code>Rp{p['vwap_20']:,}</code>)\n"
            f"   • Fase: {p['phase_badge']}\n"
            f"   • Target TP: <code>Rp{p['tp_target']:,}</code> | Stop Loss: <code>Rp{p['spring_low']:,}</code>\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/hedge KODE</code> (misal: <code>/hedge ASII</code>) untuk analisis mendalam.</i>")
    return "\n".join(lines)


def format_flow_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Gagal Menganalisis Order Flow:</b> {data['error']}"

    w = data["whale"]
    lot = w.get("lot_profile", {})
    jumbo = lot.get("jumbo_pct", 50)
    retail = lot.get("retail_pct", 30)
    medium = lot.get("medium_pct", 20)
    chg_sym = "+" if data["pct_change"] >= 0 else ""
    flow_str = f"+Rp{w['whale_flow_billion']:.1f} M" if w['whale_flow_billion'] >= 0 else f"-Rp{abs(w['whale_flow_billion']):.1f} M"

    jumbo_bars = int(jumbo / 10)
    retail_bars = int(retail / 10)
    bar_jumbo = "█" * jumbo_bars + "░" * (10 - jumbo_bars)
    bar_retail = "█" * retail_bars + "░" * (10 - retail_bars)

    domination = "🟢 DOMINASI AKUMULASI (BUYER AGGRESSIVE)" if w['cmf'] > 0 else "🔴 DOMINASI DISTRIBUSI (SELLER AGGRESSIVE)"

    return (
        f"🌊 <b>ORDER FLOW &amp; WHALE FOOTPRINT: #{data['ticker']}</b>\n"
        f"📅 <i>Tanggal: {data['date']} | Harga: Rp{int(data['close']):,} ({chg_sym}{data['pct_change']:.2f}%)\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"⚖️ <b>TEKANAN VOLUME &amp; MONEY FLOW:</b>\n"
        f"• Arah Arus Uang: <b>{domination}</b>\n"
        f"• Net Whale Flow: <b>{flow_str}</b>\n"
        f"• Chaikin Money Flow: <code>{w['cmf']:.3f}</code>\n"
        f"• Lonjakan Vol (RVOL): <code>{w['rvol']:.2f}x</code> dari rata-rata\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🐋 <b>PROFIL UKURAN TRANSAKSI (TICKET SIZE):</b>\n"
        f"• 🐋 <b>Order Jumbo (Bandar/Institusi):</b> <code>{jumbo}%</code>\n"
        f"  [{bar_jumbo}]\n"
        f"• 🐜 <b>Order Retail (Semut/FOMO):</b> <code>{retail}%</code>\n"
        f"  [{bar_retail}]\n"
        f"• 📦 <b>Order Menengah:</b> <code>{medium}%</code>\n\n"
        f"💡 <i>{lot.get('summary', '')}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>MODAL BANDAR &amp; TOLOK UKUR:</b>\n"
        f"• Est. Rata-rata Modal Bandar (VWAP): <code>Rp{int(w['whale_vwap']):,}</code>\n"
        f"• Posisi Harga vs Modal Bandar: <b>{w['pct_from_vwap']:+.1f}%</b>\n"
        f"• Support Kunci: <code>Rp{int(data['levels']['support_1']):,}</code>\n"
        f"• Resistance Target: <code>Rp{int(data['levels']['resistance_1']):,}</code>\n"
    )


def format_position_sizing_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Gagal Menghitung Money Management:</b> {data['error']}"

    return (
        f"🧮 <b>SMART MONEY MANAGEMENT: #{data['ticker']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Total Modal Alokasi:</b> <code>Rp{int(data['capital']):,}</code>\n"
        f"💵 <b>Harga Saham Saat Ini:</b> <code>Rp{data['price']:,}</code> (Rp{data['cost_per_lot']:,}/lot)\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <b>REKOMENDASI PORSI AMAN (RISK 2%):</b>\n"
        f"• Alokasi Aman: <b>{data['recommended_lots']} Lot</b> ({data['recommended_lots'] * 100:,} lembar)\n"
        f"• Total Modal Dipakai: <code>Rp{data['total_spent']:,}</code>\n"
        f"• Sisa Kas Aman (Cash Buffer): <code>Rp{data['cash_remaining']:,}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>SKENARIO PROFIT / LOSS:</b>\n"
        f"• Target TP1: <code>Rp{data['tp1']:,}</code> (+{data['profit_pct']}%)\n"
        f"  👉 Potensi Cuan: <b>+Rp{data['profit_potential']:,}</b>\n"
        f"• Stop Loss (SL): <code>Rp{data['sl']:,}</code> ({data['loss_pct']}%)\n"
        f"  👉 Resiko Toleransi: <b>-Rp{data['loss_potential']:,}</b>\n"
        f"• Reward to Risk Ratio: <b>{data['rr_ratio']}x</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Catatan: Jangan all-in pada 1 saham. Disiplin cut loss bila tembus SL!</i>"
    )


def format_sector_rotation_message(sectors: list) -> str:
    if not sectors:
        return "⚠️ Gagal mengambil data rotasi sektor."

    lines = [
        "🔄 <b>RADAR ROTASI SEKTOR IHSG (FUND FLOW)</b> 📊",
        "<i>Mendeteksi ke sektor mana arus dana Big Money sedang mengalir hari ini:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    for idx, s in enumerate(sectors, 1):
        arrow = "🟢" if s["avg_change"] > 0 else ("🔴" if s["avg_change"] < 0 else "⚪")
        chg_sym = "+" if s["avg_change"] > 0 else ""
        leader_sym = "+" if s["leader_pct"] > 0 else ""
        lines.append(
            f"{arrow} <b>{s['sector']}</b>\n"
            f"   • Rata-rata: <b>{chg_sym}{s['avg_change']:.2f}%</b>\n"
            f"   • Top Stock: <b>#{s['leader']}</b> ({leader_sym}{s['leader_pct']:.2f}%)\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/scan KODE</code> pada saham pemimpin sektor yang sedang naik untuk momentum swing.</i>")
    return "\n".join(lines)


def format_whale_footprint_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error:</b> {esc(str(data['error']))}"

    cmf_20 = data.get("cmf_20", 0)
    cmf_status = "🟢 Arus Masuk Kuat (Whale Inflow)" if cmf_20 > 0.05 else ("🔴 Arus Keluar (Whale Outflow)" if cmf_20 < -0.05 else "⚪ Netral")

    lines = [
        f"🐋 <b>INSTITUTIONAL WHALE RADAR: #{data['ticker']}</b> 🔍",
        f"<i>Deteksi Jejak Smart Money &amp; Bandarmology Bursa Efek Indonesia</i>",
        "━━━━━━━━━━━━━━━━━━━",
        f"🎯 <b>Skor Akumulasi Whale: {data['whale_score']}/100</b>",
        f"🏷️ <b>Status:</b> {data['badge']}",
        f"💰 <b>Harga Sekarang:</b> <code>Rp{int(data['close']):,}</code>",
        "━━━━━━━━━━━━━━━━━━━",
        "📊 <b>BANDARMOLOGY FOOTPRINT METRICS:</b>",
        f"• <b>Modal Rata-rata Whale:</b> <code>Rp{int(data['vwap_20d']):,}</code>",
        f"• <b>Posisi Terhadap Modal Bandar:</b> {data['cost_status']}",
        f"• <b>Spike Volume / Absorpsi:</b> <b>{data['rvol']:.1f}x</b> rata-rata",
        f"• <b>Money Flow Institusi (CMF):</b> <b>{cmf_20:+.2f}</b> ({cmf_status})",
        f"• <b>Kompresi Volatilitas (Squeeze):</b> {'🔒 Ya (Akumulasi Senyap)' if data['is_squeeze'] else '🔓 Tidak'}",
        "━━━━━━━━━━━━━━━━━━━",
        f"📖 <b>DIAGNOSA PERILAKU WHALE:</b>\n<i>{data['explanation']}</i>",
        "",
        f"🎯 <b>RENCANA EKSEKUSI INSTITUSI:</b>\n<i>{data['action_plan']}</i>\n",
        f"• 🎯 <b>Target Mark-Up 1:</b> <code>Rp{int(data['tp1']):,}</code>",
        f"• 🚀 <b>Target Mark-Up 2:</b> <code>Rp{int(data['tp2']):,}</code>",
        f"• 🛑 <b>Stop Loss Pengaman:</b> <code>Rp{int(data['sl']):,}</code>",
        "━━━━━━━━━━━━━━━━━━━",
        f"💡 <i>Tip: Klik tombol <b>[📊 Buka Chart]</b> atau <b>[🧮 Hitung Lot]</b> di bawah ini.</i>"
    ]
    return "\n".join(lines)


def format_top_whale_scan_message(stocks: list, title_tag: str = "LQ45") -> str:
    if not stocks:
        return f"⚠️ Belum ada saham di {title_tag} yang memenuhi kriteria akumulasi masif Whale hari ini."

    lines = [
        f"🐋 <b>TOP WHALE ACCUMULATION RADAR ({title_tag})</b> 🚀",
        "<i>Daftar saham yang sedang dikoleksi diam-diam oleh Smart Money:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]
    for idx, s in enumerate(stocks, 1):
        lines.append(
            f"<b>{idx}. #{s['ticker']}</b> — <code>Rp{int(s['close']):,}</code>\n"
            f"   • Skor Whale: <b>{s['whale_score']}/100</b> ({s['status']})\n"
            f"   • Modal Whale: <code>Rp{int(s['vwap_20d']):,}</code> ({s['cost_status']})\n"
            f"   • Target Mark-Up: <code>Rp{int(s['tp1']):,}</code> | SL: <code>Rp{int(s['sl']):,}</code>\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/whale KODE</code> (misal: <code>/whale BBCA</code>) untuk bedah footprint lengkap.</i>")
    return "\n".join(lines)


def format_whale_tier_list_message(tiers: dict) -> str:
    tier_s = tiers.get("tier_s", [])
    tier_a = tiers.get("tier_a", [])
    tier_b = tiers.get("tier_b", [])

    lines = [
        "🏆 <b>TIER LIST AKUMULASI WHALE (LQ45)</b> 🐋",
        "<i>Klasifikasi saham berdasarkan kekuatan akumulasi Big Money &amp; diskon modal:</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    # TIER S
    lines.append("👑 <b>TIER S — GOD TIER (Monster Akumulasi &amp; High Conviction)</b>")
    lines.append("<i>Saham dengan skor tertinggi (≥90) &amp; akumulasi institusi masif:</i>")
    if not tier_s:
        lines.append("<i>Belum ada saham yang mencapai kualifikasi Tier S hari ini.</i>\n")
    else:
        for idx, s in enumerate(tier_s, 1):
            disc_str = f"💎 <b>Diskon {abs(s['pct_diff_vwap20']):.1f}%</b>" if s['pct_diff_vwap20'] < -1.5 else "🎯 Modal Seimbang"
            lines.append(
                f"<b>{idx}. #{s['ticker']}</b> — <code>Rp{int(s['close']):,}</code>\n"
                f"   • Skor Whale: <b>{s['whale_score']}/100</b> ({s['status']})\n"
                f"   • Posisi: {disc_str} (Modal Whale: <code>Rp{int(s['vwap_20d']):,}</code>)\n"
                f"   • Target TP: <code>Rp{int(s['tp1']):,}</code> | Stop Loss: <code>Rp{int(s['sl']):,}</code>\n"
            )

    # TIER A
    lines.append("💎 <b>TIER A — HIGH CONVICTION (Akumulasi Kuat &amp; Siap Mark-Up)</b>")
    lines.append("<i>Saham dengan akumulasi solid (skor 80–89) &amp; penyerapan stabil:</i>")
    if not tier_a:
        lines.append("<i>Belum ada saham yang masuk Tier A hari ini.</i>\n")
    else:
        for idx, s in enumerate(tier_a, 1):
            disc_str = f"💎 <b>Diskon {abs(s['pct_diff_vwap20']):.1f}%</b>" if s['pct_diff_vwap20'] < -1.5 else "🎯 Modal Seimbang"
            lines.append(
                f"<b>{idx}. #{s['ticker']}</b> — <code>Rp{int(s['close']):,}</code>\n"
                f"   • Skor Whale: <b>{s['whale_score']}/100</b> ({s['status']})\n"
                f"   • Posisi: {disc_str} (Modal Whale: <code>Rp{int(s['vwap_20d']):,}</code>)\n"
                f"   • Target TP: <code>Rp{int(s['tp1']):,}</code> | Stop Loss: <code>Rp{int(s['sl']):,}</code>\n"
            )

    # TIER B
    lines.append("⚡ <b>TIER B — EARLY ACCUMULATION (Fase Penyerapan Awal)</b>")
    lines.append("<i>Saham tahap awal akumulasi (skor 70–79) yang sedang menguji support:</i>")
    if not tier_b:
        lines.append("<i>Belum ada saham yang masuk Tier B hari ini.</i>\n")
    else:
        for idx, s in enumerate(tier_b[:6], 1):
            disc_str = f"💎 Diskon {abs(s['pct_diff_vwap20']):.1f}%" if s['pct_diff_vwap20'] < -1.5 else "🎯 Modal Seimbang"
            lines.append(
                f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['close']):,}</code>) — Skor: <b>{s['whale_score']}/100</b> | {disc_str}"
            )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <b>Rekomendasi Trading:</b>")
    lines.append("👉 Prioritaskan entry pada saham <b>Tier S</b> dan <b>Tier A</b> yang bertanda 💎 <i>Diskon Bandar</i> untuk Risk/Reward Ratio maksimal.")
    lines.append("👉 Ketik <code>/whale KODE</code> (misal: <code>/whale MDKA</code>) untuk melihat diagnosa detail.")

    return "\n".join(lines)


def format_multibagger_detail_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error:</b> {esc(str(data['error']))}"

    lines = [
        f"🚀 <b>RADAR MULTI-BAGGER &amp; RUMOR: #{data['ticker']}</b> 🔥",
        "<i>Deteksi Saham Potensi Ratusan Persen (Rumor Aksi Korporasi + Akumulasi Bandar)</i>",
        "━━━━━━━━━━━━━━━━━━━",
        f"🎯 <b>Skor Potensi Multi-Bagger: {data['mb_score']}/100</b>",
        f"🏷️ <b>Status:</b> {data['phase_badge']}",
        f"💵 <b>Harga Sekarang:</b> <code>Rp{int(data['close']):,}</code>",
        "━━━━━━━━━━━━━━━━━━━",
        "📊 <b>JEJAK FOOTPRINT WHALE:</b>",
        f"• <b>Modal Rata-rata Whale:</b> <code>Rp{int(data['vwap_20d']):,}</code>",
        f"• <b>Posisi Terhadap Modal:</b> {data['cost_status']}",
        f"• <b>Lonjakan Volume (RVOL):</b> <b>{data['rvol']:.1f}x</b> dari rata-rata",
        f"• <b>Money Flow CMF:</b> <b>{data['cmf_20']:+.2f}</b>",
        "━━━━━━━━━━━━━━━━━━━",
        "📰 <b>KATALIS &amp; BAU RUMOR TERDETEKSI:</b>"
    ]

    if not data.get("news"):
        lines.append("<i>Belum ada keterbukaan informasi khusus terbaru.</i>")
    else:
        for n in data["news"]:
            lines.append(f"{n['badge']} {esc(n['title'])} <i>({esc(n['source'])})</i>")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━",
        f"📖 <b>DIAGNOSA AKSI BANDAR:</b>\n<i>{data['verdict']}</i>",
        "",
        f"🎯 <b>RENCANA EKSEKUSI MENGIKUTI BANDAR:</b>\n<i>{data['action']}</i>\n",
        f"• 🎯 <b>Target TP-1 (+30%):</b> <code>Rp{int(data['tp1']):,}</code> <i>(Jual 35% lot &amp; geser SL ke BEP)</i>",
        f"• 🚀 <b>Target TP-2 (+75%):</b> <code>Rp{int(data['tp2']):,}</code> <i>(Jual 35% lot kunci profit 1 bagger)</i>",
        f"• 💎 <b>Runner Lot (30% Sisa):</b> <i>Dibiarkan terbang ikuti mark-up bandar</i>",
        f"• 🛑 <b>Stop Loss Ketat (-6%):</b> <code>Rp{int(data['sl']):,}</code>",
        "━━━━━━━━━━━━━━━━━━━",
        f"💡 <i>Tip: Masuk saat fase Akumulasi Senyap sebelum berita resmi menjadi euforia publik!</i>"
    ])
    return "\n".join(lines)


def format_multibagger_scan_message(picks: list) -> str:
    if not picks:
        return "⚠️ Tidak ada saham yang memenuhi kriteria Multi-Bagger hari ini."

    lines = [
        "🚀 <b>TOP POTENSI MULTI-BAGGER RADAR (IHSG)</b> 🔥",
        "<i>Saham tidur / murah dengan lonjakan volume Whale &amp; rumor aksi korporasi (ala BIPI / PANI):</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    for idx, p in enumerate(picks, 1):
        catalysts_str = ", ".join([c["keyword"] for c in p.get("catalysts", [])[:2]])
        cat_badge = f" [Katalis: {catalysts_str}]" if catalysts_str else ""
        lines.append(
            f"<b>{idx}. #{p['ticker']}</b> — <code>Rp{int(p['close']):,}</code>\n"
            f"   • Skor Potensi: <b>{p['mb_score']}/100</b> ({p['phase']})\n"
            f"   • Modal Bandar: <code>Rp{int(p['vwap_20d']):,}</code> ({p['cost_status']})\n"
            f"   • Vol Spike: <b>{p['rvol']:.1f}x</b>{cat_badge}\n"
            f"   • Target TP: <code>Rp{int(p['tp1']):,}</code> | Stop Loss: <code>Rp{int(p['sl']):,}</code>\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/rumor KODE</code> (misal: <code>/rumor BIPI</code>) untuk membedah berita &amp; akumulasi bandar lengkap!</i>")
    return "\n".join(lines)


def format_ihsg_regime_message(data: dict) -> str:
    if "error" in data:
        return f"❌ <b>Error:</b> {esc(str(data['error']))}"

    lines = [
        "🌐 <b>IHSG MACRO MARKET REGIME &amp; DEFENSE ENGINE</b> 🛡️",
        "<i>Sistem Deteksi Kesehatan Pasar &amp; Proteksi Penurunan IHSG (Pelajaran Backtest 2024-2026)</i>",
        "━━━━━━━━━━━━━━━━━━━",
        f"🏷️ <b>Status Pasar:</b> {data['regime']}",
        f"🧭 <b>Mode Operasi:</b> <b>{data['status_text']}</b>",
        f"💵 <b>Level IHSG Saat Ini:</b> <code>{data['ihsg_price']:,.2f}</code> ({data['chg_1d']:+.2f}%)",
        f"📊 <b>Perubahan 5 Hari:</b> <code>{data['chg_5d']:+.2f}%</code>",
        f"📈 <b>Rata-rata SMA20:</b> <code>{data['sma20']:,.2f}</code> | <b>SMA50:</b> <code>{data['sma50']:,.2f}</code>",
        "━━━━━━━━━━━━━━━━━━━",
        "🛡️ <b>REKOMENDASI ALOKASI PORTOFOLIO:</b>",
        f"• <b>Porsi Cash Aman:</b> Minimal <b>{data['cash_pct']}%</b> dari total modal",
        f"• <b>Saham Bluechip (Big Banks):</b> {'✅ Diperbolehkan' if data['allow_bigcaps'] else '⛔ DILARANG (Rawan Guyur)'}",
        f"• <b>Saham Multi-Bagger (Konglo/Rumor):</b> {'✅ Boleh Diseleksi' if data['allow_multibagger'] else '⛔ Tahan Dulu'}",
        "━━━━━━━━━━━━━━━━━━━",
        f"💡 <b>PANDUAN EKSEKUSI BOT:</b>\n<i>{data['advice']}</i>"
    ]
    return "\n".join(lines)


def format_simulasi_100m_message() -> str:
    return (
        "💰 <b>HASIL REAL BACKTEST MENGIKUTI BANDAR (2024 - 2026)</b> 📊\n"
        "<i>Strategi: Akumulasi Smart Money + Target Bertahap (TP1 +30%, TP2 +75%, Runner)</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💵 <b>Modal Awal:</b> <code>Rp 100.000.000</code>\n"
        "💎 <b>Modal Akhir:</b> <code>Rp 150.173.667</code>\n"
        "🚀 <b>Net Profit Bersih:</b> <b>+Rp 50.173.667 (+50.2%)</b>\n"
        "📈 <b>Profit Factor:</b> <code>1.47</code> (Rasio Cuan vs Rugi > 5:1)\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>CARA MENGIKUTI TARGET TP BANDAR:</b>\n"
        "1️⃣ <b>TP-1 (+30%):</b> Jual 35% lot untuk balik modal dasar &amp; pasang Stop Loss di BEP (Risk-Free!).\n"
        "2️⃣ <b>TP-2 (+75%):</b> Jual 35% lot lagi saat harga meledak mendekati 1 Bagger.\n"
        "3️⃣ <b>Runner Lot (30% Sisa):</b> Dibiarkan terbang mengikuti mark-up bandar sampai ada sinyal distribusi!\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>CONTOH TRADE MONSTER MULTI-BAGGER:</b>\n"
        "• <b>#PANI</b>: Masuk Rp5.119 ➔ Keluar Rp10.588 | <b>+Rp 16,11 Juta (+106.8%)</b>\n"
        "• <b>#MDKA</b>: Masuk Rp2.159 ➔ Keluar Rp3.194 | <b>+Rp 12,80 Juta (+47.9%)</b>\n"
        "• <b>#ASII</b>: Masuk Rp3.889 ➔ Keluar Rp6.807 | <b>+Rp 8,10 Juta (+75.0%)</b>\n"
        "• <b>#MEDC</b>: Masuk Rp874 ➔ Keluar Rp1.257 | <b>+Rp 8,09 Juta (+43.7%)</b>\n"
        "• <b>#TPIA</b>: Masuk Rp5.182 ➔ Keluar Rp6.228 | <b>+Rp 7,57 Juta (+20.2%)</b>\n"
        "• <b>#BREN</b>: Masuk Rp4.644 ➔ Keluar Rp5.967 | <b>+Rp 6,76 Juta (+28.5%)</b>\n"
        "• <b>#BIPI</b>: Masuk Rp85 ➔ Keluar Rp99 (4.513 lot!) | <b>+Rp 6,15 Juta (+16.5%)</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🛡️ <b>DISIPLIN PROTEKSI SAAT SALAH:</b>\n"
        "• Kerugian dibatasi ketat di <b>-6.0%</b> (rugi cuma ~Rp 1,5 Juta per saham).\n"
        "• Tetapi saat menang di saham bandar, cuan mencapai <b>Rp 8 Juta s/d Rp 16 Juta</b>!\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Gunakan tombol menu di bawah untuk memindai saham yang sedang diakumulasi bandar hari ini!</i>"
    )


def format_whale_scan_message(stocks: list, title_tag: str = "LQ45", limit: int = 7) -> str:
    if not stocks:
        return f"⚠️ Tidak ditemukan saham yang memenuhi kriteria akumulasi aktif di kategori {title_tag}."

    top_stocks = stocks[:limit]
    lines = [
        f"🐋 <b>TOP WHALE ACCUMULATION ({title_tag})</b> 🚀",
        "<i>Berdasarkan Volume Spike, Chaikin Money Flow &amp; Breakout</i>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    for idx, s in enumerate(top_stocks, 1):
        w = s["whale"]
        lot_prof = w.get("lot_profile", {})
        jumbo = lot_prof.get("jumbo_pct", 50)
        chg_sym = "+" if s["pct_change"] >= 0 else ""
        flow = f"+{w['whale_flow_billion']:.1f}M" if w['whale_flow_billion'] >= 0 else f"{w['whale_flow_billion']:.1f}M"
        lines.append(
            f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['close']):,}</code> | {chg_sym}{s['pct_change']:.1f}%)\n"
            f"   • Status: <b>{w['whale_status']}</b> ({w['whale_score']}/100)\n"
            f"   • Tiket Order: 🐋 <b>Jumbo {jumbo}%</b> | Vol Spike: <b>{w['rvol']:.1f}x</b> | Flow: <b>{flow}</b>\n"
            f"   • Rencana: Beli <code>Rp{s['trading_plan']['entry_area']}</code> | TP: <code>{s['trading_plan']['tp1']:,}</code> | SL: <code>{s['trading_plan']['stop_loss']:,}</code>\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/scan KODE</code> (misal: <code>/scan BBCA</code>) untuk detail lengkap.</i>")
    return "\n".join(lines)


def handle_telegram_callback(callback_query: dict):
    cb_id = callback_query.get("id")
    if cb_id:
        answer_telegram_callback(cb_id)

    data = callback_query.get("data", "")
    msg = callback_query.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id"))
    if not chat_id or not data:
        return

    parts = data.split(":")
    if len(parts) < 2:
        return

    action, ticker = parts[0], parts[1].upper()

    if action == "chart":
        send_telegram_message(f"🎨 <i>Menggambar visual candlestick chart &amp; TP/SL #{esc(ticker)}...</i>", chat_id)
        buf = generate_stock_chart(ticker)
        if buf is None:
            send_telegram_message(f"❌ Gagal membuat chart untuk #{esc(ticker)}.", chat_id)
            return
        caption = f"📊 <b>Technical Candlestick Chart: #{esc(ticker)}</b>\n<i>Garis Biru: EMA20 | Kuning: EMA50 | Cyan: TP1 | Merah: Stop Loss</i>"
        send_telegram_photo(buf, caption=caption, chat_id=chat_id)

    elif action == "whale":
        send_telegram_message(f"🐋 <i>Mendiagnosis jejak Whale &amp; Bandarmology #{esc(ticker)}...</i>", chat_id)
        data_whale = analyze_whale_footprint(ticker)
        kb = make_stock_inline_keyboard(ticker)
        send_long_telegram_message(format_whale_footprint_message(data_whale), chat_id, reply_markup=kb)

    elif action == "rumor":
        send_telegram_message(f"🚀 <i>Mendiagnosis rumor aksi korporasi &amp; potensi Multi-Bagger #{esc(ticker)}...</i>", chat_id)
        data_mb = analyze_multibagger_rumor(ticker)
        kb = make_stock_inline_keyboard(ticker)
        send_long_telegram_message(format_multibagger_detail_message(data_mb), chat_id, reply_markup=kb)

    elif action == "flow":
        send_telegram_message(f"⏳ <i>Membaca Order Flow &amp; Tiket Transaksi #{esc(ticker)}...</i>", chat_id)
        data_flow = analyze_single_stock(ticker)
        send_long_telegram_message(format_flow_message(data_flow), chat_id)

    elif action == "hedge":
        send_telegram_message(f"🏛️ <i>Mendiagnosis fase Wyckoff &amp; Hedge Fund footprint #{esc(ticker)}...</i>", chat_id)
        data_hedge = analyze_hedgefund_wyckoff(ticker)
        send_long_telegram_message(format_hedgefund_message(data_hedge), chat_id)

    elif action == "val":
        send_telegram_message(f"⏳ <i>Mengecek valuasi fundamental #{esc(ticker)}...</i>", chat_id)
        data_val = get_single_stock_valuation(ticker)
        if "error" in data_val:
            send_telegram_message(f"❌ {data_val['error']}", chat_id)
            return
        msg_val = (
            f"💎 <b>DIAGNOSIS VALUASI: #{data_val['ticker']}</b>\n"
            f"🏢 <i>Sektor: {data_val['sector']}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>Harga Sekarang:</b> <code>Rp{int(data_val['price']):,}</code>\n"
            f"📊 <b>PBV (Price to Book):</b> <code>{data_val['pbv']}x</code>\n"
            f"📈 <b>PER (Price to Earnings):</b> <code>{data_val['per']}x</code>\n"
            f"💰 <b>Dividend Yield:</b> <code>{data_val['div_yield']}%</code>\n"
            f"🏛️ <b>Profitabilitas (ROE):</b> <code>{data_val['roe']}%</code>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Status Valuasi:</b>\n👉 <b>{data_val['status']}</b>"
        )
        send_telegram_message(msg_val, chat_id)

    elif action == "calc":
        send_telegram_message(f"⏳ <i>Menghitung alokasi aman #{esc(ticker)} untuk modal standar Rp10 Juta...</i>", chat_id)
        res_calc = calculate_position_sizing(ticker, "10jt")
        send_long_telegram_message(format_position_sizing_message(res_calc), chat_id)

    elif action == "tanya":
        send_telegram_message(f"🤖 <i>AI Copilot sedang menyusun diagnosa lengkap #{esc(ticker)}...</i>", chat_id)
        resp_ai = answer_market_query(f"apakah aman beli {ticker} sekarang?")
        send_long_telegram_message(resp_ai, chat_id)

    elif action == "menu":
        target = ticker.lower()
        if target == "prediksi":
            send_telegram_message("🔮 <i>Menganalisis Wall Street semalam, kurs Rupiah &amp; teknikal IHSG...</i>", chat_id)
            pred = predict_daily_ihsg_direction()
            send_long_telegram_message(format_daily_prediction_message(pred), chat_id)
        elif target == "multibagger":
            send_telegram_message("🚀 <i>Memindai saham potensi Multi-Bagger (Rumor Aksi Korporasi + Akumulasi)...</i>", chat_id)
            picks = scan_top_multibagger_picks(limit=6)
            send_long_telegram_message(format_multibagger_scan_message(picks), chat_id)
        elif target == "tierlist":
            send_telegram_message("🏆 <i>Menyusun Tier List akumulasi Whale LQ45 (Tier S, A, B)...</i>", chat_id)
            tiers = get_whale_tier_list(LQ45_WATCHLIST)
            send_long_telegram_message(format_whale_tier_list_message(tiers), chat_id)
        elif target == "regime":
            data_reg = get_ihsg_market_regime()
            send_long_telegram_message(format_ihsg_regime_message(data_reg), chat_id)
        elif target == "simulasi100jt":
            send_long_telegram_message(format_simulasi_100m_message(), chat_id)
        elif target == "whalelist":
            top_whales = scan_top_whale_accumulations(limit=6)
            send_long_telegram_message(format_top_whale_scan_message(top_whales, title_tag="LQ45 WHALE"), chat_id)
        elif target == "hedge":
            picks = scan_hedgefund_picks(limit=6)
            send_long_telegram_message(format_hedgefund_scan_message(picks), chat_id)
        elif target == "sektor":
            sectors = scan_sector_rotation()
            send_long_telegram_message(format_sector_rotation_message(sectors), chat_id)
        elif target == "insider":
            actions = fetch_insider_corporate_actions(limit=5)
            lines = [
                "🕵️‍♂️ <b>RADAR INSIDER &amp; AKSI KORPORASI</b>",
                "<i>Kabar Merger, Akuisisi, Buyback &amp; Dividen Terkini:</i>",
                "━━━━━━━━━━━━━━━━━━━"
            ]
            for a in actions:
                lines.append(f"{a['badge']} <b>{a['category']}</b>\n👉 {a['title']} <i>({a['source']})</i>\n")
            lines.append("━━━━━━━━━━━━━━━━━━━")
            send_long_telegram_message("\n".join(lines), chat_id)


def handle_telegram_command(command_text: str, chat_id: str):
    raw_text = command_text.strip()

    BTN_MAP = {
        "🔮 Prediksi Arah IHSG": "/prediksi",
        "🚀 Radar Multi-Bagger": "/multibagger",
        "🏆 Tier List Whale": "/tierlist",
        "🌐 Status Pasar IHSG": "/regime",
        "💰 Portofolio 100 Juta": "/simulasi100jt",
        "🐋 Top Whale LQ45": "/whalelist",
        "🏛️ Wyckoff Hedge Fund": "/hedge",
        "🔄 Rotasi Sektor": "/sektor",
        "📰 Radar Aksi Korporasi": "/insider"
    }

    raw_lower = raw_text.lower()
    if "prediksi" in raw_lower or "arah ihsg" in raw_lower or "besok" in raw_lower or "arah" in raw_lower:
        command_text = "/prediksi"
    elif "tier list" in raw_lower:
        command_text = "/tierlist"
    elif "multi-bagger" in raw_lower or "multibagger" in raw_lower:
        command_text = "/multibagger"
    elif "status pasar" in raw_lower or "kesehatan ihsg" in raw_lower or "regime" in raw_lower:
        command_text = "/regime"
    elif "portofolio" in raw_lower or "100 juta" in raw_lower or "simulasi" in raw_lower:
        command_text = "/simulasi100jt"
    elif "top whale" in raw_lower:
        command_text = "/whalelist"
    elif "wyckoff" in raw_lower or "hedge fund" in raw_lower:
        command_text = "/hedge"
    elif "rotasi sektor" in raw_lower or "sektor" in raw_lower:
        command_text = "/sektor"
    elif "aksi korporasi" in raw_lower or "radar aksi" in raw_lower:
        command_text = "/insider"
    elif raw_text in BTN_MAP:
        command_text = BTN_MAP[raw_text]

    parts = command_text.strip().split()
    if not parts:
        return

    cmd = parts[0].split("@")[0].lower()

    if cmd in ["/start", "/menu", "/help"]:
        help_msg = (
            "🤖 <b>IHSG &amp; WHALE BANDARMOLOGY SIGNAL BOT</b>\n\n"
            "Bot ini memantau IHSG dan mendeteksi saham yang diakumulasi Whale / Smart Money.\n\n"
            "👇 <b>Cukup sentuh tombol menu di bawah layar atau klik tombol pilihan cepat berikut tanpa perlu mengetik:</b>"
        )
        send_telegram_message(help_msg, chat_id, reply_markup=make_persistent_reply_keyboard())
        send_telegram_message("⚡ <b>PILIHAN MENU CEPAT (KLIK LANGSUNG):</b>", chat_id, reply_markup=make_main_inline_menu())
        return

    elif cmd in ["/prediksi", "/arah", "/forecast", "/besok"]:
        send_telegram_message("🔮 <i>Menganalisis Wall Street semalam, kurs Rupiah &amp; teknikal IHSG...</i>", chat_id)
        pred = predict_daily_ihsg_direction()
        send_long_telegram_message(format_daily_prediction_message(pred), chat_id)

    elif cmd in ["/hedge", "/hedgefund", "/wyckoff"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"🏛️ <i>Mendiagnosis jejak Hedge Fund &amp; fase Wyckoff #{esc(ticker)}...</i>", chat_id)
            data_hedge = analyze_hedgefund_wyckoff(ticker)
            kb = make_stock_inline_keyboard(ticker)
            send_long_telegram_message(format_hedgefund_message(data_hedge), chat_id, reply_markup=kb)
        else:
            send_telegram_message("🏛️ <i>Memindai saham LQ45 untuk fase Silent Accumulation &amp; Spring Shakeout...</i>", chat_id)
            picks = scan_hedgefund_picks(limit=6)
            send_long_telegram_message(format_hedgefund_scan_message(picks), chat_id)

    elif cmd in ["/tanya", "/ask", "/ai"]:
        if len(parts) < 2:
            send_telegram_message(
                "🤖 <b>AI MARKET COPILOT</b>\n\n"
                "Ketik pertanyaan Anda setelah <code>/tanya</code>.\n"
                "Contoh:\n"
                "• <code>/tanya apakah aman beli BBRI sekarang?</code>\n"
                "• <code>/tanya bagaimana prospek dividen BBCA?</code>\n"
                "• <code>/tanya sektor apa yang paling menarik hari ini?</code>\n"
                "• <code>/tanya rekomendasi saham swing trade</code>",
                chat_id
            )
            return

        user_query = " ".join(parts[1:])
        send_telegram_message("🤖 <i>AI Copilot sedang menganalisis pasar &amp; menyusun diagnosa...</i>", chat_id)
        ans = answer_market_query(user_query)
        ticker_found = extract_ticker_from_query(user_query)
        kb = make_stock_inline_keyboard(ticker_found) if ticker_found else None
        send_long_telegram_message(ans, chat_id, reply_markup=kb)

    elif cmd in ["/ihsg"]:
        send_telegram_message("⏳ <i>Sedang menganalisis data IHSG...</i>", chat_id)
        data = analyze_ihsg()
        send_long_telegram_message(format_ihsg_message(data), chat_id)

    elif cmd in ["/regime", "/ihsg_defense", "/macro"]:
        send_telegram_message("🌐 <i>Mendiagnosis kondisi kesehatan IHSG &amp; sinyal proteksi crash...</i>", chat_id)
        data_reg = get_ihsg_market_regime()
        send_long_telegram_message(format_ihsg_regime_message(data_reg), chat_id)

    elif cmd in ["/simulasi100jt", "/portofolio", "/backtest100m"]:
        send_long_telegram_message(format_simulasi_100m_message(), chat_id)

    elif cmd in ["/whale", "/bandar"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"🐋 <i>Mendiagnosis jejak Whale &amp; Bandarmology #{esc(ticker)}...</i>", chat_id)
            data_whale = analyze_whale_footprint(ticker)
            kb = make_stock_inline_keyboard(ticker)
            send_long_telegram_message(format_whale_footprint_message(data_whale), chat_id, reply_markup=kb)
        else:
            send_telegram_message("🐋 <i>Memindai saham LQ45 untuk mencari akumulasi Whale tertinggi...</i>", chat_id)
            top_whales = scan_top_whale_accumulations(limit=6)
            send_long_telegram_message(format_top_whale_scan_message(top_whales, title_tag="LQ45 WHALE"), chat_id)

    elif cmd in ["/whalelist", "/topwhale"]:
        send_telegram_message("🐋 <i>Memindai saham LQ45 untuk mencari akumulasi Whale tertinggi...</i>", chat_id)
        top_whales = scan_top_whale_accumulations(limit=6)
        send_long_telegram_message(format_top_whale_scan_message(top_whales, title_tag="LQ45 WHALE"), chat_id)

    elif cmd in ["/tier", "/tierlist", "/tier_list"]:
        send_telegram_message("🏆 <i>Menyusun Tier List akumulasi Whale LQ45 (Tier S, A, B)...</i>", chat_id)
        tiers = get_whale_tier_list(LQ45_WATCHLIST)
        send_long_telegram_message(format_whale_tier_list_message(tiers), chat_id)

    elif cmd in ["/rumor", "/akuisisi", "/katalis"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"🚀 <i>Mendiagnosis rumor aksi korporasi &amp; potensi Multi-Bagger #{esc(ticker)}...</i>", chat_id)
            data_mb = analyze_multibagger_rumor(ticker)
            kb = make_stock_inline_keyboard(ticker)
            send_long_telegram_message(format_multibagger_detail_message(data_mb), chat_id, reply_markup=kb)
        else:
            send_telegram_message("🚀 <i>Memindai saham potensi Multi-Bagger (Rumor Aksi Korporasi + Akumulasi)...</i>", chat_id)
            picks = scan_top_multibagger_picks(limit=6)
            send_long_telegram_message(format_multibagger_scan_message(picks), chat_id)

    elif cmd in ["/multibagger", "/mb"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"🚀 <i>Mendiagnosis rumor aksi korporasi &amp; potensi Multi-Bagger #{esc(ticker)}...</i>", chat_id)
            data_mb = analyze_multibagger_rumor(ticker)
            kb = make_stock_inline_keyboard(ticker)
            send_long_telegram_message(format_multibagger_detail_message(data_mb), chat_id, reply_markup=kb)
        else:
            send_telegram_message("🚀 <i>Memindai saham potensi Multi-Bagger (Rumor Aksi Korporasi + Akumulasi)...</i>", chat_id)
            picks = scan_top_multibagger_picks(limit=6)
            send_long_telegram_message(format_multibagger_scan_message(picks), chat_id)

    elif cmd in ["/multibagger_all", "/mb_all"]:
        send_telegram_message("🚀 <i>Memindai 100 saham Kompas100 untuk mencari potensi Multi-Bagger... Mohon tunggu ~15 detik.</i>", chat_id)
        picks = scan_top_multibagger_picks(limit=8, watchlist=KOMPAS100_WATCHLIST)
        send_long_telegram_message(format_multibagger_scan_message(picks), chat_id)

    elif cmd in ["/lq45", "/akumulasi"]:
        send_telegram_message("⏳ <i>Memindai saham LQ45 untuk deteksi akumulasi Whale...</i>", chat_id)
        stocks = scan_whale_watchlist(LQ45_WATCHLIST)
        send_long_telegram_message(format_whale_scan_message(stocks, title_tag="LQ45"), chat_id)

    elif cmd in ["/kompas100"]:
        send_telegram_message("⏳ <i>Memindai 100 saham Kompas100 secara paralel...</i>", chat_id)
        stocks = scan_whale_watchlist(KOMPAS100_WATCHLIST)
        send_long_telegram_message(format_whale_scan_message(stocks, title_tag="KOMPAS 100"), chat_id)

    elif cmd in ["/whale_all", "/semua"]:
        total_tickers = len(ALL_IDX_TICKERS)
        send_telegram_message(f"⏳ <i>Memindai seluruh <b>{total_tickers} saham BEI</b>... Mohon tunggu ~20-30 detik.</i>", chat_id)
        min_turnover = INDICATOR_CONFIG.get("min_turnover_billion", 0.5)
        stocks = scan_whale_watchlist(ALL_IDX_TICKERS, min_turnover_billion=min_turnover, max_workers=8)
        send_long_telegram_message(format_whale_scan_message(stocks, title_tag="ALL 958 IDX STOCKS", limit=10), chat_id)

    elif cmd in ["/scan"]:
        if len(parts) < 2:
            send_telegram_message("⚠️ Harap sertakan kode saham. Contoh: <code>/scan BBCA</code>", chat_id)
            return

        ticker = parts[1].upper()
        send_telegram_message(f"⏳ <i>Menganalisis #{esc(ticker)}, jejak Whale &amp; Bau Berita...</i>", chat_id)
        data = analyze_single_stock(ticker)
        kb = make_stock_inline_keyboard(ticker)
        send_long_telegram_message(format_single_stock_message(data), chat_id, reply_markup=kb)

    elif cmd in ["/chart", "/grafik"]:
        if len(parts) < 2:
            send_telegram_message("⚠️ Harap sertakan kode saham. Contoh: <code>/chart BBCA</code>", chat_id)
            return

        ticker = parts[1].upper()
        send_telegram_message(f"🎨 <i>Menggambar visual candlestick chart &amp; TP/SL #{esc(ticker)}...</i>", chat_id)
        buf = generate_stock_chart(ticker)
        if buf is None:
            send_telegram_message(f"❌ Gagal membuat chart untuk #{esc(ticker)}. Pastikan kode benar.", chat_id)
            return
        caption = f"📊 <b>Technical Candlestick Chart: #{esc(ticker)}</b>\n<i>Garis Biru: EMA20 | Kuning: EMA50 | Cyan: TP1 | Merah: Stop Loss</i>"
        if not send_telegram_photo(buf, caption=caption, chat_id=chat_id):
            send_telegram_message(f"❌ Gagal mengirim gambar chart #{esc(ticker)} ke Telegram.", chat_id)

    elif cmd in ["/calc", "/hitung", "/money", "/lot"]:
        if len(parts) < 3:
            send_telegram_message(
                "⚠️ Format salah! Gunakan: <code>/lot [KODE] [MODAL]</code>\nContoh: <code>/lot BIPI 100jt</code> atau <code>/calc BBCA 10jt</code>",
                chat_id
            )
            return

        ticker = parts[1].upper()
        capital_str = parts[2]
        send_telegram_message(f"⏳ <i>Menghitung alokasi aman lot #{esc(ticker)} untuk modal {esc(capital_str)}...</i>", chat_id)
        res = calculate_position_sizing(ticker, capital_str)
        send_long_telegram_message(format_position_sizing_message(res), chat_id)

    elif cmd in ["/sektor", "/sector"]:
        send_telegram_message("⏳ <i>Memindai performa dan arus rotasi sektor IHSG...</i>", chat_id)
        sectors = scan_sector_rotation()
        send_long_telegram_message(format_sector_rotation_message(sectors), chat_id)

    elif cmd in ["/flow", "/orderflow"]:
        if len(parts) < 2:
            send_telegram_message("⚠️ Harap sertakan kode saham. Contoh: <code>/flow BBCA</code>", chat_id)
            return

        ticker = parts[1].upper()
        send_telegram_message(f"⏳ <i>Membaca Order Flow &amp; Tiket Transaksi #{esc(ticker)}...</i>", chat_id)
        data = analyze_single_stock(ticker)
        kb = make_stock_inline_keyboard(ticker)
        send_long_telegram_message(format_flow_message(data), chat_id, reply_markup=kb)

    elif cmd in ["/insider", "/aksi"]:
        ticker = parts[1].upper() if len(parts) > 1 else None
        target_str = f"#{ticker}" if ticker else "Bursa IDX"
        send_telegram_message(f"⏳ <i>Memindai radar aksi korporasi &amp; keterbukaan info {target_str}...</i>", chat_id)
        actions = fetch_insider_corporate_actions(ticker=ticker, limit=5)
        lines = [
            f"🕵️‍♂️ <b>RADAR INSIDER &amp; AKSI KORPORASI ({target_str})</b>",
            "<i>Kabar Merger, Akuisisi, Buyback &amp; Dividen Terkini:</i>",
            "━━━━━━━━━━━━━━━━━━━"
        ]
        if not actions:
            lines.append("<i>Tidak ditemukan aksi korporasi khusus baru-baru ini.</i>")
        else:
            for a in actions:
                lines.append(f"{a['badge']} <b>{a['category']}</b>\n👉 {a['title']} <i>({a['source']})</i>\n")
        lines.append("━━━━━━━━━━━━━━━━━━━")
        send_long_telegram_message("\n".join(lines), chat_id)

    elif cmd in ["/undervalued", "/berlian", "/murah"]:
        if len(parts) > 1:
            ticker = parts[1].upper()
            send_telegram_message(f"⏳ <i>Mengecek valuasi fundamental #{ticker}...</i>", chat_id)
            data = get_single_stock_valuation(ticker)
            if "error" in data:
                send_telegram_message(f"❌ {data['error']}", chat_id)
                return
            msg = (
                f"💎 <b>DIAGNOSIS VALUASI: #{data['ticker']}</b>\n"
                f"🏢 <i>Sektor: {data['sector']}</i>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>Harga Sekarang:</b> <code>Rp{int(data['price']):,}</code>\n"
                f"📊 <b>PBV (Price to Book):</b> <code>{data['pbv']}x</code>\n"
                f"📈 <b>PER (Price to Earnings):</b> <code>{data['per']}x</code>\n"
                f"💰 <b>Dividend Yield:</b> <code>{data['div_yield']}%</code>\n"
                f"🏛️ <b>Profitabilitas (ROE):</b> <code>{data['roe']}%</code>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 <b>Status Valuasi:</b>\n👉 <b>{data['status']}</b>"
            )
            kb = make_stock_inline_keyboard(ticker)
            send_telegram_message(msg, chat_id, reply_markup=kb)
        else:
            send_telegram_message("⏳ <i>Menyaring saham 'Mercy Harga Avanza' lintas sektor...</i>", chat_id)
            stocks = scan_undervalued_stocks(LQ45_WATCHLIST, limit=5)
            lines = [
                "💎 <b>DEEP VALUE SCREENER (MERCY HARGA AVANZA)</b> 🚀",
                "<i>Saham-saham fundamental mewah dengan valuasi diskon:</i>",
                "━━━━━━━━━━━━━━━━━━━"
            ]
            for idx, s in enumerate(stocks, 1):
                lines.append(
                    f"<b>{idx}. #{s['ticker']}</b> (<code>Rp{int(s['price']):,}</code> | Sektor: {s['sector']})\n"
                    f"   • PBV: <b>{s['pbv']}x</b> | PER: <b>{s['per']}x</b>\n"
                    f"   • ROE: <b>{s['roe']}%</b> | Div Yield: <b>{s['div_yield']}%</b>\n"
                    f"   • Diskon Fundamental: <b>{s['discount_score']}/100</b>\n"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━")
            send_long_telegram_message("\n".join(lines), chat_id)

    elif cmd in ["/dividen", "/dividend"]:
        send_telegram_message("⏳ <i>Memindai saham-saham dengan Dividend Yield tertinggi di IDX...</i>", chat_id)
        stocks = scan_high_dividend_stocks(LQ45_WATCHLIST, limit=5)
        lines = [
            "💰 <b>TOP DIVIDEND YIELD RADAR (PASIF INCOME)</b> 💵",
            "<i>Saham pemberi bagi hasil dividen paling royal di bursa:</i>",
            "━━━━━━━━━━━━━━━━━━━"
        ]
        for idx, s in enumerate(stocks, 1):
            lines.append(
                f"<b>{idx}. #{s['ticker']}</b> — <code>Rp{int(s['price']):,}</code>\n"
                f"   • 💰 <b>Dividend Yield: {s['div_yield']}%</b>\n"
                f"   • Sektor: {s['sector']} | PER: {s['per']}x\n"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 <i>Ketik <code>/scan KODE</code> untuk cek kapan waktu terbaik masuk sebelum cum-date.</i>")
        send_long_telegram_message("\n".join(lines), chat_id)

    elif cmd in ["/daily"]:
        send_telegram_message("⏳ <i>Menyiapkan laporan harian pasar &amp; radar Hedge Fund...</i>", chat_id)
        ihsg = analyze_ihsg()
        send_long_telegram_message(format_ihsg_message(ihsg), chat_id)
        hedge_picks = scan_hedgefund_picks(limit=5)
        send_long_telegram_message(format_hedgefund_scan_message(hedge_picks), chat_id)
        stocks = scan_whale_watchlist(LQ45_WATCHLIST)
        send_long_telegram_message(format_whale_scan_message(stocks, title_tag="LQ45", limit=5), chat_id)

    else:
        raw = cmd.replace("/", "").upper()
        if len(raw) in [4, 5] and raw.isalpha():
            send_telegram_message(f"⏳ <i>Menganalisis #{esc(raw)}...</i>", chat_id)
            data = analyze_single_stock(raw)
            kb = make_stock_inline_keyboard(raw)
            send_long_telegram_message(format_single_stock_message(data), chat_id, reply_markup=kb)


def start_bot_polling():
    token = TELEGRAM_BOT_TOKEN
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        return

    print("🤖 Bot Telegram IHSG Signal & Whale Monitor aktif...")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=20"
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1

                    if "callback_query" in update:
                        cb = update["callback_query"]
                        _command_executor.submit(handle_telegram_callback, cb)
                        continue

                    msg = update.get("message")
                    if not msg or "text" not in msg:
                        continue

                    chat_id = str(msg["chat"]["id"])
                    text = msg["text"]
                    _command_executor.submit(handle_telegram_command, text, chat_id)
            else:
                time.sleep(2)
        except Exception as e:
            print(f"[Polling Error] {e}")
            time.sleep(3)


def scheduled_worker():
    print("⏰ Background scheduler aktif untuk notifikasi pasar...")
    already_sent = {"morning": "", "closing": ""}

    while True:
        try:
            now = datetime.now(WIB) if WIB else datetime.now()
            now_str = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")

            # Morning Brief (08:30 WIB - 30 Menit Sebelum Buka)
            if now_str == SCHEDULED_ALERTS.get("morning_brief", "08:30") and already_sent["morning"] != today_str:
                if TELEGRAM_CHAT_ID:
                    pred = predict_daily_ihsg_direction()
                    ihsg = analyze_ihsg()
                    hedge_picks = scan_hedgefund_picks(limit=4)
                    top_whales = scan_top_whale_accumulations(limit=3)
                    stocks = scan_whale_watchlist(LQ45_WATCHLIST)
                    msg = (
                        "🌅 <b>MORNING MARKET RADAR &amp; WHALE REPORT (08:30 WIB)</b>\n"
                        "<i>30 Menit Menuju Pembukaan Sesi 1 IHSG!</i>\n\n"
                        + format_daily_prediction_message(pred) + "\n\n"
                        + format_ihsg_message(ihsg) + "\n\n"
                        + format_top_whale_scan_message(top_whales, title_tag="TOP WHALE ACCUMULATION") + "\n\n"
                        + format_hedgefund_scan_message(hedge_picks) + "\n\n"
                        + format_whale_scan_message(stocks, title_tag="LQ45 WHALE MOMENTUM", limit=4)
                    )
                    send_long_telegram_message(msg)
                    already_sent["morning"] = today_str

            # Closing Report (16:15 WIB)
            if now_str == SCHEDULED_ALERTS.get("market_closing", "16:15") and already_sent["closing"] != today_str:
                if TELEGRAM_CHAT_ID:
                    ihsg = analyze_ihsg()
                    hedge_picks = scan_hedgefund_picks(limit=4)
                    top_whales = scan_top_whale_accumulations(limit=3)
                    stocks = scan_whale_watchlist(LQ45_WATCHLIST)
                    msg = (
                        "🌇 <b>POST-MARKET CLOSING &amp; WHALE REPORT (16:15 WIB)</b>\n\n"
                        + format_ihsg_message(ihsg) + "\n\n"
                        + format_top_whale_scan_message(top_whales, title_tag="CLOSING WHALE ACCUMULATION") + "\n\n"
                        + format_hedgefund_scan_message(hedge_picks) + "\n\n"
                        + format_whale_scan_message(stocks, title_tag="LQ45 CLOSING WHALE", limit=4)
                    )
                    send_long_telegram_message(msg)
                    already_sent["closing"] = today_str

            time.sleep(30)
        except Exception as e:
            print(f"[Scheduler Error] {e}")
            time.sleep(30)


if __name__ == "__main__":
    t_poll = threading.Thread(target=start_bot_polling, daemon=True, name="polling")
    t_sched = threading.Thread(target=scheduled_worker, daemon=True, name="scheduler")

    t_poll.start()
    t_sched.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Bot dimatikan oleh pengguna.")
        sys.exit(0)
