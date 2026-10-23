"""
Personal Portfolio Tracker & Dynamic TP/SL Guard:
Menyimpan dan mengawal posisi portofolio pribadi user secara real-time,
menghitung PnL (Cuan/Rugi), memantau jarak ke TP1 (+30%), TP2 (+75%), SL (-6%),
serta memberikan panduan trailing stop otomatis.
"""

import os
import json
from typing import Dict, Any, List
import yfinance as yf
from datetime import datetime

PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "user_portfolios.json")


def _load_portfolios() -> dict:
    if not os.path.exists(PORTFOLIO_FILE):
        return {}
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_portfolios(data: dict):
    try:
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR Save Portfolio] {e}")


def add_stock_to_portfolio(chat_id: str, ticker: str, buy_price: float, lots: int = 10) -> Dict[str, Any]:
    t = ticker.replace(".JK", "").strip().upper()
    data = _load_portfolios()
    cid = str(chat_id)

    if cid not in data:
        data[cid] = {}

    data[cid][t] = {
        "ticker": t,
        "buy_price": float(buy_price),
        "lots": int(lots),
        "date_added": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    _save_portfolios(data)

    return {
        "success": True,
        "ticker": t,
        "buy_price": buy_price,
        "lots": lots,
        "total_invested": buy_price * lots * 100,
        "tp1": buy_price * 1.30,
        "tp2": buy_price * 1.75,
        "sl": buy_price * 0.94
    }


def remove_stock_from_portfolio(chat_id: str, ticker: str) -> bool:
    t = ticker.replace(".JK", "").strip().upper()
    data = _load_portfolios()
    cid = str(chat_id)

    if cid in data and t in data[cid]:
        del data[cid][t]
        _save_portfolios(data)
        return True
    return False


def get_user_portfolio_list(chat_id: str) -> List[Dict[str, Any]]:
    data = _load_portfolios()
    cid = str(chat_id)
    return list(data.get(cid, {}).values())


def evaluate_user_portfolio(chat_id: str) -> Dict[str, Any]:
    holdings = get_user_portfolio_list(chat_id)
    if not holdings:
        return {"items": [], "total_invested": 0, "current_value": 0, "net_pnl_rp": 0, "net_pnl_pct": 0}

    tickers = [f"{h['ticker']}.JK" for h in holdings]
    try:
        raw = yf.download(tickers, period="5d", interval="1d", progress=False, group_by="ticker")
    except Exception:
        raw = pd.DataFrame()

    evaluated_items = []
    total_invested = 0.0
    total_current_val = 0.0

    for h in holdings:
        t = h["ticker"]
        yf_t = f"{t}.JK"
        buy_p = h["buy_price"]
        lots = h["lots"]

        curr_p = buy_p
        chg_1d = 0.0

        if not raw.empty:
            try:
                if len(tickers) == 1:
                    c_series = raw["Close"].dropna()
                else:
                    c_series = raw[yf_t]["Close"].dropna()
                if len(c_series) >= 1:
                    curr_p = float(c_series.iloc[-1])
                if len(c_series) >= 2:
                    prev_p = float(c_series.iloc[-2])
                    chg_1d = ((curr_p - prev_p) / prev_p) * 100
            except Exception:
                curr_p = buy_p

        invested = buy_p * lots * 100
        cur_val = curr_p * lots * 100
        pnl_rp = cur_val - invested
        pnl_pct = ((curr_p - buy_p) / buy_p) * 100

        total_invested += invested
        total_current_val += cur_val

        tp1_p = buy_p * 1.30
        tp2_p = buy_p * 1.75
        sl_p = buy_p * 0.94

        if pnl_pct >= 75.0:
            badge = "🚀 SUPER CUAN 1-BAGGER"
            advice = "Kunci profit TP2 (Jual 35% lagi & pasang trailing stop ketat di +50%)"
        elif pnl_pct >= 30.0:
            badge = "🎯 TARGET TP1 TERCAPAI (+30%)"
            advice = "Jual 35% lot untuk kunci modal & geser Stop Loss ke BEP (Risk-Free!)"
        elif pnl_pct >= 10.0:
            badge = "🟢 ON-TRACK MARK-UP"
            advice = "Tahan santai mengikuti bandar. Pasang trailing stop di +5%."
        elif pnl_pct >= 0.0:
            badge = "📈 FLOATING PROFIT"
            advice = "Posisi aman menghijau. Tunggu mark-up menuju TP1."
        elif pnl_pct > -4.5:
            badge = "🟡 MINOR PULLBACK"
            advice = "Koreksi wajar. Amati support modal beli."
        elif pnl_pct > -6.0:
            badge = "⚠️ WASPADA DEKAT SL"
            advice = "Harga mendekati batas toleransi -6%. Siapkan cut loss jika tembus SL!"
        else:
            badge = "🛑 HIT STOP LOSS (-6%)"
            advice = "Disiplin proteksi modal! Cut loss sesuai aturan demi selamatkan sisa kas."

        evaluated_items.append({
            "ticker": t,
            "buy_price": buy_p,
            "lots": lots,
            "current_price": curr_p,
            "chg_1d": chg_1d,
            "invested": invested,
            "current_val": cur_val,
            "pnl_rp": pnl_rp,
            "pnl_pct": pnl_pct,
            "tp1": tp1_p,
            "tp2": tp2_p,
            "sl": sl_p,
            "badge": badge,
            "advice": advice
        })

    net_pnl_rp = total_current_val - total_invested
    net_pnl_pct = ((total_current_val - total_invested) / total_invested * 100) if total_invested > 0 else 0.0

    return {
        "items": evaluated_items,
        "total_invested": total_invested,
        "current_value": total_current_val,
        "net_pnl_rp": net_pnl_rp,
        "net_pnl_pct": net_pnl_pct
    }


def format_portfolio_message(evaluation: Dict[str, Any]) -> str:
    items = evaluation.get("items", [])
    if not items:
        return (
            "💼 <b>PORTOFOLIO PANTAUAN PRIBADI</b>\n\n"
            "Anda belum mendaftarkan saham untuk dipantau.\n\n"
            "💡 <b>Cara Menambahkan Saham ke Pantauan:</b>\n"
            "Ketik format: <code>/pantau KODE HARGA_BELI LOT</code>\n\n"
            "<b>Contoh:</b>\n"
            "• <code>/pantau BBCA 9800 20</code> (20 lot di harga 9.800)\n"
            "• <code>/pantau PANI 5200 50</code> (50 lot di harga 5.200)\n"
            "• <code>/pantau ASII 4850 15</code>\n\n"
            "<i>Robot akan otomatis mengawal posisi TP1 (+30%), TP2 (+75%), dan batas Stop Loss (-6%) Anda!</i>"
        )

    net_rp = evaluation["net_pnl_rp"]
    net_pct = evaluation["net_pnl_pct"]
    pnl_sign = "+" if net_rp >= 0 else ""
    pnl_emoji = "🟢" if net_rp >= 0 else "🔴"

    lines = [
        "💼 <b>DASHBOARD PORTOFOLIO PANTAUAN PRIBADI</b> 📊",
        "<i>Pengawalan Otomatis Smart Money: TP1 (+30%), TP2 (+75%), SL (-6%)</i>",
        "━━━━━━━━━━━━━━━━━━━",
        f"💰 <b>Total Modal Terpasang:</b> <code>Rp{int(evaluation['total_invested']):,}</code>",
        f"💎 <b>Nilai Portofolio Kini:</b> <code>Rp{int(evaluation['current_value']):,}</code>",
        f"{pnl_emoji} <b>Total PnL Bersih:</b> <b>{pnl_sign}Rp{int(net_rp):,} ({pnl_sign}{net_pct:.2f}%)</b>",
        "━━━━━━━━━━━━━━━━━━━"
    ]

    for idx, it in enumerate(items, 1):
        item_sign = "+" if it["pnl_rp"] >= 0 else ""
        item_chg_sign = "+" if it["chg_1d"] >= 0 else ""
        lines.append(
            f"<b>{idx}. #{it['ticker']}</b> ({it['lots']} Lot | Modal: <code>Rp{int(it['buy_price']):,}</code>)\n"
            f"   • Harga Sekarang: <code>Rp{int(it['current_price']):,}</code> ({item_chg_sign}{it['chg_1d']:.1f}%)\n"
            f"   • PnL Saham: <b>{item_sign}Rp{int(it['pnl_rp']):,} ({item_sign}{it['pnl_pct']:.2f}%)</b>\n"
            f"   • Status: <b>{it['badge']}</b>\n"
            f"   • Target TP1 (+30%): <code>Rp{int(it['tp1']):,}</code> | SL (-6%): <code>Rp{int(it['sl']):,}</code>\n"
            f"   👉 <i>Panduan: {it['advice']}</i>\n"
        )

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━",
        "💡 <i>Ketik <code>/hapuspantau KODE</code> (misal: <code>/hapuspantau BBCA</code>) untuk menghapus saham dari pantauan.</i>"
    ])

    return "\n".join(lines)


def format_portfolio_daily_brief(chat_id: str) -> str:
    eval_data = evaluate_user_portfolio(chat_id)
    items = eval_data.get("items", [])
    if not items:
        return ""

    net_rp = eval_data["net_pnl_rp"]
    net_pct = eval_data["net_pnl_pct"]
    pnl_sign = "+" if net_rp >= 0 else ""
    pnl_emoji = "🟢" if net_rp >= 0 else "🔴"

    lines = [
        "💼 <b>UPDATE PORTOFOLIO PANTAUAN ANDA:</b>",
        f"• Status Akun: {pnl_emoji} <b>{pnl_sign}Rp{int(net_rp):,} ({pnl_sign}{net_pct:.2f}%)</b> dari {len(items)} saham aktif"
    ]

    alerts = []
    for it in items:
        if it["pnl_pct"] >= 30.0:
            alerts.append(f"🎉 <b>#{it['ticker']}</b> menyentuh target cuan (+{it['pnl_pct']:.1f}%)! Amankan profit TP1.")
        elif it["pnl_pct"] <= -4.5:
            alerts.append(f"⚠️ <b>#{it['ticker']}</b> tertekan ({it['pnl_pct']:.1f}%), waspadai batas cut loss!")

    if alerts:
        lines.append("⚡ <b>SINYAL AKSI PENTING HARI INI:</b>")
        for a in alerts:
            lines.append(f"👉 {a}")
    else:
        lines.append("✅ Semua posisi saham bergerak aman dalam koridor trading plan.")

    lines.append("💡 <i>Ketik <code>/watchlist</code> untuk melihat rincian lengkap portofolio Anda.</i>")
    return "\n".join(lines)
