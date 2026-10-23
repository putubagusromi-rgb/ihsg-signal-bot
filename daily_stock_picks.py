import os
import json
import io
from datetime import datetime
from typing import List, Dict, Any

try:
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
except Exception:
    WIB = None

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

from signal_engine import fetch_stock_data, calculate_support_resistance
from ara_hunter import scan_ara_hunter_picks
from hedgefund_radar import scan_hedgefund_picks
from whale_radar import scan_top_whale_accumulations

PICKS_HISTORY_FILE = os.path.join(os.path.dirname(__file__), "daily_picks_history.json")


def _get_today_str() -> str:
    now = datetime.now(WIB) if WIB else datetime.now()
    return now.strftime("%Y-%m-%d")


def load_picks_history() -> dict:
    if os.path.exists(PICKS_HISTORY_FILE):
        try:
            with open(PICKS_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_picks_history(data: dict):
    try:
        with open(PICKS_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Error save_picks_history] {e}")


def get_daily_top3_picks(force_refresh: bool = False) -> List[Dict[str, Any]]:
    today_str = _get_today_str()
    history = load_picks_history()

    if not force_refresh and today_str in history and history[today_str].get("picks"):
        return history[today_str]["picks"]

    candidates = []
    seen_tickers = set()

    # 1. Cek Radar ARA Hunter
    try:
        ara_list = scan_ara_hunter_picks(limit=3)
        for a in ara_list:
            sym = a["ticker"]
            if sym not in seen_tickers:
                seen_tickers.add(sym)
                close_p = a["close"]
                sup = a.get("support", int(close_p * 0.96))
                tgt = a.get("target_ara", int(close_p * 1.08))
                candidates.append({
                    "ticker": sym,
                    "last_price": close_p,
                    "support": sup,
                    "target": tgt,
                    "score": a.get("ara_score", 85) + 15,
                    "source": "ARA Hunter",
                    "reason": "Ledakan Volume & Akumulasi Penutupan"
                })
    except Exception as e:
        print(f"[DailyPicks ARA Error] {e}")

    # 2. Cek Radar Wyckoff Hedge Fund
    try:
        hedge_list = scan_hedgefund_picks(limit=4)
        for h in hedge_list:
            sym = h["ticker"]
            if sym not in seen_tickers:
                seen_tickers.add(sym)
                close_p = h["price"]
                sup = h.get("spring_low", int(close_p * 0.95))
                tgt = h.get("tp_target", int(close_p * 1.08))
                candidates.append({
                    "ticker": sym,
                    "last_price": close_p,
                    "support": sup,
                    "target": tgt,
                    "score": h.get("hedge_score", 75) + 10,
                    "source": "Hedge Fund Wyckoff",
                    "reason": "Akumulasi Senyap & Dekat Modal Bandar"
                })
    except Exception as e:
        print(f"[DailyPicks Hedge Error] {e}")

    # 3. Cek Top Whale Accumulation
    try:
        whale_list = scan_top_whale_accumulations(limit=4)
        for w in whale_list:
            sym = w["ticker"]
            if sym not in seen_tickers:
                seen_tickers.add(sym)
                close_p = w["close"]
                sup = w.get("sup_20", int(close_p * 0.95))
                tgt = w.get("tp1", int(close_p * 1.07))
                candidates.append({
                    "ticker": sym,
                    "last_price": close_p,
                    "support": sup,
                    "target": tgt,
                    "score": w.get("whale_score", 70),
                    "source": "Whale Accumulation",
                    "reason": f"Net Inflow Masif ({w.get('status', 'Akumulasi')})"
                })
    except Exception as e:
        print(f"[DailyPicks Whale Error] {e}")

    # 4. Fallback jika bursa sepi
    if len(candidates) < 3:
        for sym in ["BBCA", "BBRI", "BMRI", "ASII", "TLKM"]:
            if sym not in seen_tickers:
                df = fetch_stock_data(sym, period="3mo", interval="1d")
                if df is not None and len(df) > 10:
                    c = int(df["Close"].iloc[-1])
                    levels = calculate_support_resistance(df)
                    sup = int(levels["support_1"])
                    tgt = int(levels["resistance_1"])
                    if tgt <= c:
                        tgt = int(c * 1.05)
                    if sup >= c:
                        sup = int(c * 0.96)
                    candidates.append({
                        "ticker": sym,
                        "last_price": c,
                        "support": sup,
                        "target": tgt,
                        "score": 60,
                        "source": "Blue Chip Leader",
                        "reason": "Konsolidasi di Area Support Kuat"
                    })
                    seen_tickers.add(sym)
            if len(candidates) >= 3:
                break

    candidates.sort(key=lambda x: x["score"], reverse=True)
    top3 = candidates[:3]

    for p in top3:
        p["last_price"] = int(p["last_price"])
        p["support"] = int(p["support"])
        p["target"] = int(p["target"])
        if p["last_price"] > 0:
            p["gain_potential_pct"] = round(((p["target"] - p["last_price"]) / p["last_price"]) * 100, 1)
        else:
            p["gain_potential_pct"] = 0.0

    history[today_str] = {
        "date": today_str,
        "created_at": datetime.now().isoformat(),
        "picks": top3
    }
    save_picks_history(history)
    return top3


def generate_stock_pick_image(picks: List[Dict[str, Any]], date_str: str = None) -> bytes:
    if not date_str:
        now = datetime.now(WIB) if WIB else datetime.now()
        date_str = now.strftime("%b %d, %Y")

    fig = plt.figure(figsize=(7.5, 9.6), dpi=220)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    ax.set_facecolor("#FFFFFF")
    bg_box = patches.Rectangle((0, 0), 1, 1, facecolor="#F8FAFD", edgecolor="none", zorder=0)
    ax.add_patch(bg_box)

    top_bar = patches.Rectangle((0, 0.985), 1, 0.015, facecolor="#6366F1", edgecolor="none", zorder=1)
    ax.add_patch(top_bar)

    # Logo mark
    circle_outer = patches.Circle((0.14, 0.88), 0.055, facecolor="#EEF2FF", edgecolor="#6366F1", linewidth=2.5, zorder=2)
    ax.add_patch(circle_outer)
    circle_inner = patches.Circle((0.14, 0.88), 0.035, facecolor="#6366F1", edgecolor="none", zorder=3)
    ax.add_patch(circle_inner)
    ax.text(0.14, 0.88, "RWY", fontsize=11, fontweight="bold", color="#FFFFFF", ha="center", va="center", zorder=4)
    ax.text(0.14, 0.81, "Cuan Cuy!", fontsize=12, fontweight="bold", color="#4F46E5", ha="center", va="center", zorder=4)

    # Title
    ax.text(0.48, 0.89, "Daily", fontsize=28, fontweight="bold", color="#0F172A", ha="center", va="center", zorder=3)
    ax.text(0.48, 0.83, "Stock Pick", fontsize=28, fontweight="bold", color="#0F172A", ha="center", va="center", zorder=3)

    # Date
    ax.text(0.88, 0.89, date_str, fontsize=13, fontweight="bold", color="#334155", ha="right", va="center", zorder=3)
    ax.text(0.88, 0.84, "08:30 WIB", fontsize=11, color="#64748B", ha="right", va="center", zorder=3)

    # Decorative dots
    for i in range(3):
        for j in range(3):
            d = patches.Circle((0.08 + i * 0.018, 0.69 + j * 0.018), 0.004, facecolor="#38BDF8", alpha=0.8, zorder=2)
            ax.add_patch(d)

    # Decorative rings on right
    ring1 = patches.Circle((0.92, 0.52), 0.03, facecolor="none", edgecolor="#F97316", linewidth=4, zorder=1)
    ax.add_patch(ring1)
    dot_purp = patches.Circle((0.91, 0.62), 0.012, facecolor="#8B5CF6", zorder=1)
    ax.add_patch(dot_purp)

    # Stock Items
    y_positions = [0.66, 0.47, 0.28]
    for idx, (p, y) in enumerate(zip(picks[:3], y_positions)):
        ax.text(0.20, y + 0.035, f"#{p['ticker']}", fontsize=28, fontweight="bold", color="#0F172A", va="center", zorder=3)
        ax.text(0.20, y - 0.035, f"Last Price {p['last_price']:,}", fontsize=13, color="#475569", va="center", zorder=3)

        ax.text(0.50, y + 0.035, "Support :", fontsize=15, fontweight="bold", color="#1E293B", va="center", zorder=3)
        ax.text(0.67, y + 0.035, f"{p['support']:,}", fontsize=18, fontweight="bold", color="#DC2626", va="center", zorder=3)

        gain_str = f" (+{p['gain_potential_pct']}%)" if p.get('gain_potential_pct') else ""
        ax.text(0.50, y - 0.035, "Target   :", fontsize=15, fontweight="bold", color="#1E293B", va="center", zorder=3)
        ax.text(0.67, y - 0.035, f"{p['target']:,}{gain_str}", fontsize=17, fontweight="bold", color="#16A34A", va="center", zorder=3)

        div_line = patches.Rectangle((0.18, y - 0.08), 0.68, 0.003, facecolor="#4338CA", zorder=2)
        ax.add_patch(div_line)

    # Footer
    ax.text(0.08, 0.13, "Analyst : RWY Capital AI Sniper System", fontsize=11, fontweight="bold", color="#1E293B", zorder=3)
    disclaimer = (
        "Disclaimer :\n"
        "Seluruh informasi di atas merupakan hasil analisa algoritma kuantitatif & jejak modal Whale.\n"
        "Bukan ajakan beli, jual, dan / atau investasi. Keputusan transaksi merupakan tanggung jawab sendiri."
    )
    ax.text(0.08, 0.065, disclaimer, fontsize=8.5, color="#64748B", style="italic", va="center", zorder=3)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def evaluate_daily_result(target_date: str = None) -> Dict[str, Any]:
    history = load_picks_history()
    target_date = target_date or _get_today_str()

    if target_date not in history or not history[target_date].get("picks"):
        picks = get_daily_top3_picks()
    else:
        picks = history[target_date]["picks"]

    results = []
    hit_target_count = 0
    total_max_gain = 0.0

    for p in picks:
        sym = p["ticker"]
        base_price = p["last_price"]
        target = p["target"]
        support = p["support"]

        df = fetch_stock_data(sym, period="5d", interval="1d")
        if df is not None and len(df) > 0:
            latest = df.iloc[-1]
            high = int(latest["High"])
            low = int(latest["Low"])
            close = int(latest["Close"])
        else:
            high = base_price
            low = base_price
            close = base_price

        max_gain = round(((high - base_price) / base_price) * 100, 2)
        close_gain = round(((close - base_price) / base_price) * 100, 2)
        total_max_gain += max_gain

        hit_target = high >= target
        if hit_target:
            hit_target_count += 1
            status = "TARGET HIT"
            badge = "[HIT]"
        elif close_gain > 0:
            status = "PROFIT"
            badge = "[CUAN]"
        elif low <= support:
            status = "HIT SUPPORT"
            badge = "[SL]"
        else:
            status = "HOLD"
            badge = "[HOLD]"

        results.append({
            "ticker": sym,
            "entry_price": base_price,
            "support": support,
            "target": target,
            "high_today": high,
            "close_today": close,
            "max_gain_pct": max_gain,
            "close_gain_pct": close_gain,
            "hit_target": hit_target,
            "status": status,
            "badge": badge
        })

    n = len(results) if results else 1
    win_rate = round((hit_target_count / n) * 100, 1)
    avg_max_gain = round(total_max_gain / n, 2)

    eval_summary = {
        "date": target_date,
        "results": results,
        "hit_target_count": hit_target_count,
        "total_picks": len(results),
        "win_rate": win_rate,
        "avg_max_gain": avg_max_gain
    }

    if target_date in history:
        history[target_date]["evaluation"] = eval_summary
        save_picks_history(history)

    return eval_summary


def generate_daily_result_image(eval_data: Dict[str, Any]) -> bytes:
    date_str = eval_data.get("date", _get_today_str())
    results = eval_data.get("results", [])
    win_rate = eval_data.get("win_rate", 0.0)
    avg_gain = eval_data.get("avg_max_gain", 0.0)

    fig = plt.figure(figsize=(7.5, 9.6), dpi=220)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    ax.set_facecolor("#FFFFFF")
    bg_box = patches.Rectangle((0, 0), 1, 1, facecolor="#F8FAFD", edgecolor="none", zorder=0)
    ax.add_patch(bg_box)

    top_bar = patches.Rectangle((0, 0.985), 1, 0.015, facecolor="#10B981", edgecolor="none", zorder=1)
    ax.add_patch(top_bar)

    # Logo
    circle_outer = patches.Circle((0.14, 0.88), 0.055, facecolor="#ECFDF5", edgecolor="#10B981", linewidth=2.5, zorder=2)
    ax.add_patch(circle_outer)
    circle_inner = patches.Circle((0.14, 0.88), 0.035, facecolor="#10B981", edgecolor="none", zorder=3)
    ax.add_patch(circle_inner)
    ax.text(0.14, 0.88, "RWY", fontsize=11, fontweight="bold", color="#FFFFFF", ha="center", va="center", zorder=4)
    ax.text(0.14, 0.81, "Cuan Cuy!", fontsize=12, fontweight="bold", color="#059669", ha="center", va="center", zorder=4)

    # Title
    ax.text(0.48, 0.89, "Daily", fontsize=28, fontweight="bold", color="#0F172A", ha="center", va="center", zorder=3)
    ax.text(0.48, 0.83, "Result Hari Ini", fontsize=25, fontweight="bold", color="#059669", ha="center", va="center", zorder=3)

    ax.text(0.88, 0.89, date_str, fontsize=13, fontweight="bold", color="#334155", ha="right", va="center", zorder=3)
    ax.text(0.88, 0.84, "Penutupan Pasar", fontsize=11, color="#64748B", ha="right", va="center", zorder=3)

    # Stats banner
    banner = patches.FancyBboxPatch((0.12, 0.72), 0.76, 0.065,
                                    boxstyle="round,pad=0.015,rounding_size=0.02",
                                    facecolor="#0F172A", edgecolor="none", zorder=2)
    ax.add_patch(banner)
    ax.text(0.32, 0.752, f"Target Win Rate: {win_rate:.0f}%", fontsize=12, fontweight="bold", color="#F8FAFC", ha="center", va="center", zorder=3)
    ax.text(0.68, 0.752, f"Rata-rata Max Cuan: +{avg_gain:.1f}%", fontsize=12, fontweight="bold", color="#34D399", ha="center", va="center", zorder=3)

    # Stock Result Rows
    y_positions = [0.58, 0.41, 0.24]
    for idx, (r, y) in enumerate(zip(results[:3], y_positions)):
        is_hit = r["hit_target"]

        ax.text(0.18, y + 0.035, f"#{r['ticker']}", fontsize=26, fontweight="bold", color="#0F172A", va="center", zorder=3)
        ax.text(0.18, y - 0.035, f"Entry {r['entry_price']:,} | Target {r['target']:,}", fontsize=11.5, color="#64748B", va="center", zorder=3)

        gain_str = f"+{r['max_gain_pct']}%" if r['max_gain_pct'] >= 0 else f"{r['max_gain_pct']}%"
        status_text = "TARGET HIT!" if is_hit else ("PROFIT" if r['close_gain_pct'] > 0 else "KONSOLIDASI")
        status_col = "#059669" if is_hit else ("#0284C7" if r['close_gain_pct'] > 0 else "#64748B")

        # Badge pill
        pill = patches.FancyBboxPatch((0.50, y + 0.015), 0.38, 0.045,
                                      boxstyle="round,pad=0.01,rounding_size=0.02",
                                      facecolor="#ECFDF5" if is_hit else "#F1F5F9",
                                      edgecolor=status_col, linewidth=1.5, zorder=2)
        ax.add_patch(pill)
        ax.text(0.69, y + 0.037, f"{status_text}  ({gain_str})", fontsize=12.5, fontweight="bold", color=status_col, ha="center", va="center", zorder=3)

        ax.text(0.50, y - 0.035, "High Hari Ini :", fontsize=12.5, fontweight="bold", color="#334155", va="center", zorder=3)
        ax.text(0.70, y - 0.035, f"{r['high_today']:,}", fontsize=14, fontweight="bold", color="#0F172A", va="center", zorder=3)

        div_line = patches.Rectangle((0.18, y - 0.07), 0.68, 0.003, facecolor="#059669" if is_hit else "#CBD5E1", zorder=2)
        ax.add_patch(div_line)

    # Footer
    ax.text(0.08, 0.12, "Analyst : RWY Capital Automated Engine", fontsize=11, fontweight="bold", color="#1E293B", zorder=3)
    disclaimer = (
        "Disclaimer :\n"
        "Hasil evaluasi harian tercatat langsung dari harga pasar bursa (Sesi 1 & 2).\n"
        "Gunakan trailing stop untuk mengunci profit saat target telah tercapai."
    )
    ax.text(0.08, 0.065, disclaimer, fontsize=8.5, color="#64748B", style="italic", va="center", zorder=3)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def format_daily_stock_pick_caption(picks: List[Dict[str, Any]], date_str: str = None) -> str:
    if not date_str:
        now = datetime.now(WIB) if WIB else datetime.now()
        date_str = now.strftime("%d %B %Y")

    lines = [
        "📋 <b>DAILY STOCK PICK HARI INI (08:30 WIB)</b> 🎯",
        f"📅 <i>Tanggal: {date_str} (30 Menit Menuju Buka Sesi 1)</i>",
        "━━━━━━━━━━━━━━━━━━━",
        "Berikut 3 saham terbaik hasil screening algoritma AI & Whale Accumulation:",
        ""
    ]

    for idx, p in enumerate(picks[:3], 1):
        gain_str = f"+{p['gain_potential_pct']}%" if p.get('gain_potential_pct') else ""
        lines.append(
            f"<b>{idx}. #{p['ticker']}</b> (<code>Rp {p['last_price']:,}</code>)\n"
            f"   • 🛡️ <b>Support:</b> <code>Rp {p['support']:,}</code>\n"
            f"   • 🎯 <b>Target :</b> <code>Rp {p['target']:,}</code> (<b>{gain_str}</b>)\n"
            f"   • 💡 <i>Katalis: {p['reason']}</i>\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/scan KODE</code> (misal: <code>/scan {0}</code>) untuk melihat trading plan & chart.</i>".format(picks[0]['ticker'] if picks else 'BBCA'))
    return "\n".join(lines)


def format_daily_result_caption(eval_data: Dict[str, Any], date_str: str = None) -> str:
    if not date_str:
        date_str = eval_data.get("date", _get_today_str())

    results = eval_data.get("results", [])
    win_rate = eval_data.get("win_rate", 0.0)
    avg_gain = eval_data.get("avg_max_gain", 0.0)

    lines = [
        "🌇 <b>DAILY RESULT &amp; EVALUASI STOCK PICK HARI INI (16:15 WIB)</b> 📊",
        f"📅 <i>Tanggal: {date_str} (Penutupan Bursa)</i>",
        "━━━━━━━━━━━━━━━━━━━",
        f"🏆 <b>Target Win Rate:</b> <b>{win_rate:.0f}%</b> ({eval_data.get('hit_target_count', 0)}/{len(results)} Capai Target TP)",
        f"🚀 <b>Rata-rata Maks Gain:</b> <b>+{avg_gain:.2f}%</b>",
        "━━━━━━━━━━━━━━━━━━━",
        "<b>Rincian Hasil 3 Saham Pilihan Pagi Ini:</b>",
        ""
    ]

    for idx, r in enumerate(results[:3], 1):
        status_tag = "🎯 <b>TARGET HIT!</b>" if r['hit_target'] else ("🟢 <b>PROFIT</b>" if r['close_gain_pct'] > 0 else "🟡 <b>KONSOLIDASI</b>")
        chg_sym = "+" if r['max_gain_pct'] >= 0 else ""
        lines.append(
            f"<b>{idx}. #{r['ticker']}</b> — {status_tag}\n"
            f"   • Modal: <code>Rp {r['entry_price']:,}</code> | Target: <code>Rp {r['target']:,}</code>\n"
            f"   • Tertinggi Hari Ini: <code>Rp {r['high_today']:,}</code> (<b>{chg_sym}{r['max_gain_pct']:.2f}%</b>)\n"
            f"   • Penutupan: <code>Rp {r['close_today']:,}</code> ({'+' if r['close_gain_pct'] >= 0 else ''}{r['close_gain_pct']:.2f}%)\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Ketik <code>/prediksi</code> untuk melihat proyeksi arah IHSG esok hari.</i>")
    return "\n".join(lines)
