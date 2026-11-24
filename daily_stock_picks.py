import os
import json
import io
from datetime import datetime, timedelta
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

import yfinance as yf
from signal_engine import fetch_stock_data, calculate_support_resistance, clean_ticker
from ara_hunter import scan_ara_hunter_picks
from hedgefund_radar import scan_hedgefund_picks
from whale_radar import scan_top_whale_accumulations

def get_target_trading_day() -> dict:
    now = datetime.now(WIB) if WIB else datetime.now()
    wd = now.weekday()
    hour = now.hour
    is_weekend = wd in (5, 6)

    if wd == 5:
        target_dt = now + timedelta(days=2)
        target_label = "Buka Bursa Senin"
        is_prep = True
    elif wd == 6:
        target_dt = now + timedelta(days=1)
        target_label = "Buka Bursa Senin"
        is_prep = True
    elif wd == 4 and hour >= 16:
        target_dt = now + timedelta(days=3)
        target_label = "Buka Bursa Senin"
        is_prep = True
    elif wd in (0, 1, 2, 3) and hour >= 16:
        target_dt = now + timedelta(days=1)
        next_day = ["Selasa", "Rabu", "Kamis", "Jumat"][wd]
        target_label = f"Buka Bursa {next_day}"
        is_prep = True
    else:
        day_names = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"]
        day_name = day_names[wd] if wd < 5 else "Senin"
        target_dt = now
        target_label = f"Hari Ini ({day_name})"
        is_prep = False

    DAY_MAP_ID = {0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis", 4: "Jumat", 5: "Sabtu", 6: "Minggu"}
    MONTH_MAP_ID = {1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus", 9: "September", 10: "Oktober", 11: "November", 12: "Desember"}
    MONTH_MAP_EN = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

    t_day_name = DAY_MAP_ID[target_dt.weekday()]
    t_month_name = MONTH_MAP_ID[target_dt.month]
    t_month_en = MONTH_MAP_EN[target_dt.month]

    formatted_id = f"{t_day_name}, {target_dt.day} {t_month_name} {target_dt.year}"
    formatted_en = f"{target_dt.day} {t_month_en} {target_dt.year}"

    return {
        "target_date_str": target_dt.strftime("%Y-%m-%d"),
        "formatted_id": formatted_id,
        "formatted_en": formatted_en,
        "is_weekend": is_weekend,
        "is_prep": is_prep,
        "target_label": target_label,
        "target_day_name": t_day_name
    }

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

    market_warning = None

    # 1. Cek IHSG Crash Shield & Early Warning Circuit Breaker (Hanya Warning, Non-Blocking)
    try:
        from ihsg_crash_shield import detect_ihsg_crash_shield
        shield = detect_ihsg_crash_shield()
        if shield.get("active"):
            print(f"[DailyStockPicks] IHSG CRASH SHIELD WARNING: {shield.get('reasons')}")
            market_warning = {
                "active": True,
                "type": "CRASH_SHIELD",
                "severity": shield.get("severity", "RISK-OFF"),
                "reasons": shield.get("reasons", ["Koreksi pasar sistemik terdeteksi"]),
                "advice": "Pasar berisiko tinggi. Utamakan strategi Buy The Low di harga bawah & disiplin Stop Loss 5.5%!",
                "shield_data": shield
            }
    except Exception as e:
        print(f"[CrashShield Check Error] {e}")

    # 1B. Cek Kompas Arah Tren Pasar IHSG (Market Direction Compass)
    try:
        from rwy_alpha_scanner import get_market_compass
        compass = get_market_compass()
        if compass.get("status") == "BEARISH" and not market_warning:
            print(f"[DailyStockPicks] PASAR DOWNTREND WARNING: {compass.get('advice')}")
            market_warning = {
                "active": True,
                "type": "BEARISH_TREND",
                "severity": "BEARISH DOWNTREND",
                "reasons": [
                    "IHSG terkonfirmasi Downtrend (di bawah level SMA20 & SMA50)",
                    f"Tekanan jual pasar: {compass.get('advice', '')}"
                ],
                "advice": compass.get("advice", "Utamakan Buy The Low & disiplin Stop Loss 5.5%!"),
                "ihsg_price": compass.get("close", 0),
                "ihsg_chg1d": compass.get("chg_1d", 0),
                "ihsg_chg5d": compass.get("chg_5d", 0)
            }
    except Exception as e:
        print(f"[MarketCompass Check Error] {e}")

    if not force_refresh and today_str in history and history[today_str].get("picks"):
        picks = history[today_str]["picks"]
        for p in picks:
            c = int(p.get("last_price", 1000))
            sup = int(p.get("support", int(c * 0.96)))
            tgt = int(p.get("target", int(c * 1.08)))
            if sup < c and (c - sup) / c <= 0.06:
                sl = int(sup * 0.985)
            else:
                sl = int(c * 0.952)
            p["stop_loss"] = p.get("stop_loss", sl)
            risk_pct = round(((c - p["stop_loss"]) / c) * 100, 1) if c > 0 else 4.8
            gain_pct = round(((tgt - c) / c) * 100, 1) if c > 0 else 7.5
            p["risk_pct"] = risk_pct if risk_pct > 0 else 4.8
            p["gain_potential_pct"] = gain_pct
            p["risk_reward"] = round(gain_pct / risk_pct, 1) if risk_pct > 0 else 2.0
        return picks

    candidates = []
    seen_tickers = set()

    # 0. Prioritas Utama: RWY Alpha Scanner (Buy The Low, Broker Flow BSJP, Wyckoff Spring Rebound)
    try:
        from rwy_alpha_scanner import run_rwy_alpha_scanner
        scan_res = run_rwy_alpha_scanner()
        for rc in scan_res.get("candidates", []):
            sym = rc["ticker"]
            if sym not in seen_tickers:
                seen_tickers.add(sym)
                close_p = rc["close"]
                sup_p = int(close_p * 0.955)
                tgt_p = rc["tp1"]
                # Berikan pembobotan lebih tinggi untuk BUY THE LOW saat kondisi pasar berisiko
                bonus_score = 45 if ("BUY THE LOW" in rc.get("category", "") or "SPRING" in rc.get("category", "")) else 35
                candidates.append({
                    "ticker": sym,
                    "last_price": close_p,
                    "support": sup_p,
                    "target": tgt_p,
                    "score": rc["score"] + bonus_score,
                    "source": rc["category"],
                    "is_rwy_alpha": True,
                    "rwy_tag": rc.get("tag", "CALON BAGGER"),
                    "rvol": rc.get("rvol", 1.8),
                    "cmf": rc.get("cmf", 0.15),
                    "price_pos_pct": rc.get("price_pos_pct", 40.0),
                    "reason": f"RWY Alpha Scanner: {rc['tag']} ({rc['narrative']})"
                })
    except Exception as e:
        print(f"[DailyPicks RWY Scanner Error] {e}")

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
        p["support"] = int(p.get("support", int(p["last_price"] * 0.96)))
        p["target"] = int(p.get("target", int(p["last_price"] * 1.07)))
        c = p["last_price"]
        # Strict Stop Loss 5.5% (Disiplin Mandat Robot RWY V2)
        sl = int(round(c * 0.945))
        p["stop_loss"] = sl
        p["risk_pct"] = 5.5
        tgt = p["target"]
        gain_pct = round(((tgt - c) / c) * 100, 1) if c > 0 else 7.0
        p["gain_potential_pct"] = gain_pct
        p["risk_reward"] = round(gain_pct / 5.5, 1)

    history[today_str] = {
        "date": today_str,
        "created_at": datetime.now().isoformat(),
        "picks": top3,
        "market_warning": market_warning
    }
    save_picks_history(history)
    return top3


def generate_crash_defense_image(shield: Dict[str, Any], date_str: str = None) -> bytes:
    """Kartu Grafis Khusus Pertahanan Modal saat IHSG Crash Shield Aktif"""
    t_info = get_target_trading_day()
    if not date_str:
        date_str = f"{t_info['target_day_name']}, {t_info['formatted_en']}"

    fig = plt.figure(figsize=(7.5, 9.6), dpi=220)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    ax.set_facecolor("#FFFFFF")
    bg_box = patches.Rectangle((0, 0), 1, 1, facecolor="#FEF2F2", edgecolor="none", zorder=0)
    ax.add_patch(bg_box)

    top_bar = patches.Rectangle((0, 0.985), 1, 0.015, facecolor="#DC2626", edgecolor="none", zorder=1)
    ax.add_patch(top_bar)

    # Logo mark (Red Shield Theme)
    circle_outer = patches.Circle((0.14, 0.88), 0.055, facecolor="#FEE2E2", edgecolor="#DC2626", linewidth=2.5, zorder=2)
    ax.add_patch(circle_outer)
    circle_inner = patches.Circle((0.14, 0.88), 0.035, facecolor="#DC2626", edgecolor="none", zorder=3)
    ax.add_patch(circle_inner)
    ax.text(0.14, 0.88, "RWY", fontsize=11, fontweight="bold", color="#FFFFFF", ha="center", va="center", zorder=4)
    ax.text(0.14, 0.81, "SHIELD", fontsize=11, fontweight="bold", color="#B91C1C", ha="center", va="center", zorder=4)

    # Title
    ax.text(0.48, 0.89, "IHSG CRASH SHIELD", fontsize=23, fontweight="bold", color="#991B1B", ha="center", va="center", zorder=3)
    ax.text(0.48, 0.83, "CIRCUIT BREAKER AKTIF", fontsize=17, fontweight="bold", color="#DC2626", ha="center", va="center", zorder=3)

    # Date
    ax.text(0.88, 0.89, date_str, fontsize=11, fontweight="bold", color="#7F1D1D", ha="right", va="center", zorder=3)
    ax.text(0.88, 0.84, "STATUS: RISK-OFF", fontsize=10, fontweight="bold", color="#DC2626", ha="right", va="center", zorder=3)

    # Big Alert Box
    alert_box = patches.FancyBboxPatch((0.08, 0.65), 0.84, 0.12,
                                       boxstyle="round,pad=0.015,rounding_size=0.02",
                                       facecolor="#FEE2E2", edgecolor="#EF4444", linewidth=2.0, zorder=2)
    ax.add_patch(alert_box)
    ax.text(0.50, 0.725, "[!] PEMBELIAN DIBEKUKAN: CASH IS KING! [!]", fontsize=14.5, fontweight="bold", color="#991B1B", ha="center", va="center", zorder=3)
    ax.text(0.50, 0.680, "Pasar terdeteksi dalam risiko koreksi tajam / outflow sistemik. DILARANG menangkap pisau jatuh!", fontsize=9.0, color="#7F1D1D", ha="center", va="center", zorder=3)

    # Market Indicators Box
    card_box = patches.FancyBboxPatch((0.08, 0.35), 0.84, 0.27,
                                      boxstyle="round,pad=0.015,rounding_size=0.02",
                                      facecolor="#FFFFFF", edgecolor="#FECACA", linewidth=1.5, zorder=2)
    ax.add_patch(card_box)
    ax.text(0.12, 0.585, "[!] INDIKATOR BAHAYA SISTEMIK TERDETEKSI:", fontsize=12, fontweight="bold", color="#991B1B", va="center", zorder=3)

    reasons = shield.get("reasons", ["Koreksi tajam indeks global & tekanan kurs valas"])
    if not reasons:
        reasons = ["Tekanan koreksi pasar sistemik (IHSG di bawah level rata-rata pergerakan)"]
    for idx, r in enumerate(reasons[:4]):
        y_r = 0.535 - (idx * 0.045)
        ax.text(0.12, y_r, f"- {r[:65]}...", fontsize=9.2, fontweight="bold", color="#334155", va="center", zorder=3)

    # Guidelines Box
    guide_box = patches.FancyBboxPatch((0.08, 0.12), 0.84, 0.19,
                                       boxstyle="round,pad=0.015,rounding_size=0.02",
                                       facecolor="#FFFFFF", edgecolor="#E2E8F0", linewidth=1.2, zorder=2)
    ax.add_patch(guide_box)
    ax.text(0.12, 0.275, "[*] PROTOKOL PERLINDUNGAN MODAL:", fontsize=11.5, fontweight="bold", color="#1E293B", va="center", zorder=3)
    ax.text(0.12, 0.235, "1. 100% Simpan Dana Tunai (Cash): Jangan masuk ke saham apa pun.", fontsize=9, color="#475569", va="center", zorder=3)
    ax.text(0.12, 0.195, "2. Ketatkan Trailing Stop: Jika ada saham berjalan, amankan profit.", fontsize=9, color="#475569", va="center", zorder=3)
    ax.text(0.12, 0.155, "3. Bot akan otomatis aktif kembali saat badai kepanikan mereda.", fontsize=9, color="#475569", va="center", zorder=3)

    # Footer
    ax.text(0.08, 0.05, "Analyst : RWY Capital AI Defense System | Menjaga modal trading adalah prioritas nomor 1.", fontsize=8.2, color="#94A3B8", style="italic", va="center", zorder=3)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def generate_stock_pick_image(picks: List[Dict[str, Any]], date_str: str = None) -> bytes:
    if not picks:
        from ihsg_crash_shield import detect_ihsg_crash_shield
        shield = detect_ihsg_crash_shield()
        return generate_crash_defense_image(shield, date_str)
    t_info = get_target_trading_day()
    if not date_str:
        date_str = f"{t_info['target_day_name']}, {t_info['formatted_en']}"

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
    if t_info["is_prep"]:
        ax.text(0.48, 0.89, "Watchlist", fontsize=27, fontweight="bold", color="#0F172A", ha="center", va="center", zorder=3)
        ax.text(0.48, 0.83, f"Buka Bursa {t_info['target_day_name']}", fontsize=21, fontweight="bold", color="#4F46E5", ha="center", va="center", zorder=3)
    else:
        ax.text(0.48, 0.89, "Daily", fontsize=28, fontweight="bold", color="#0F172A", ha="center", va="center", zorder=3)
        ax.text(0.48, 0.83, "Stock Pick", fontsize=28, fontweight="bold", color="#0F172A", ha="center", va="center", zorder=3)

    # Date
    ax.text(0.88, 0.89, date_str, fontsize=12, fontweight="bold", color="#334155", ha="right", va="center", zorder=3)
    time_label = "Buka Sesi 1" if t_info["is_prep"] else "08:30 WIB"
    ax.text(0.88, 0.84, time_label, fontsize=10.5, color="#64748B", ha="right", va="center", zorder=3)

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
        # Left: Ticker, Entry, Risk:Reward
        ax.text(0.18, y + 0.038, f"#{p['ticker']}", fontsize=25, fontweight="bold", color="#0F172A", va="center", zorder=3)
        if p.get("is_rwy_alpha"):
            raw_tag = p.get('rwy_tag', 'CALON BAGGER')
            if "BUY THE LOW" in raw_tag:
                badge_lbl = "[*] BUY THE LOW"
            elif "BROKER FLOW" in raw_tag:
                badge_lbl = "[*] BROKER FLOW"
            elif "SPRING" in raw_tag:
                badge_lbl = "[*] SPRING REBOUND"
            elif "BREAKOUT" in raw_tag:
                badge_lbl = "[*] BREAKOUT"
            else:
                badge_lbl = "[*] CALON BAGGER"
            pill = patches.FancyBboxPatch((0.34, y + 0.024), 0.23, 0.028,
                                          boxstyle="round,pad=0.005,rounding_size=0.01",
                                          facecolor="#FEF3C7", edgecolor="#D97706", linewidth=1.2, zorder=2)
            ax.add_patch(pill)
            ax.text(0.455, y + 0.038, badge_lbl, fontsize=7.5, fontweight="bold", color="#B45309", ha="center", va="center", zorder=3)
        ax.text(0.18, y - 0.002, f"Entry: Rp {p['last_price']:,}", fontsize=12, fontweight="bold", color="#475569", va="center", zorder=3)
        rr_val = p.get('risk_reward', 2.0)
        ax.text(0.18, y - 0.040, f"R : R = 1 : {rr_val}", fontsize=12, fontweight="bold", color="#4F46E5", va="center", zorder=3)

        # Right: Target TP, Stop Loss, Support
        gain_str = f" (+{p.get('gain_potential_pct', 7.0)}%)"
        risk_str = f" (-{p.get('risk_pct', 5.5)}%)"
        sl_val = p.get('stop_loss', int(p['last_price'] * 0.95))

        ax.text(0.48, y + 0.038, "Target TP  :", fontsize=13, fontweight="bold", color="#1E293B", va="center", zorder=3)
        ax.text(0.67, y + 0.038, f"{p['target']:,}{gain_str}", fontsize=14.5, fontweight="bold", color="#16A34A", va="center", zorder=3)

        ax.text(0.48, y - 0.002, "Stop Loss  :", fontsize=13, fontweight="bold", color="#1E293B", va="center", zorder=3)
        ax.text(0.67, y - 0.002, f"{sl_val:,}{risk_str}", fontsize=14.5, fontweight="bold", color="#DC2626", va="center", zorder=3)

        ax.text(0.48, y - 0.040, "Support    :", fontsize=11.5, color="#64748B", va="center", zorder=3)
        ax.text(0.67, y - 0.040, f"{p['support']:,}", fontsize=12, fontweight="bold", color="#64748B", va="center", zorder=3)

        div_line = patches.Rectangle((0.15, y - 0.075), 0.72, 0.0025, facecolor="#E2E8F0", zorder=2)
        ax.add_patch(div_line)

    # Footer Warning & Disclaimer
    warn_box = patches.FancyBboxPatch((0.08, 0.075), 0.84, 0.085,
                                      boxstyle="round,pad=0.01,rounding_size=0.015",
                                      facecolor="#FEF2F2", edgecolor="#EF4444", linewidth=1.5, zorder=2)
    ax.add_patch(warn_box)
    ax.text(0.50, 0.130, "⚠️ DISCLAIMER : BUKAN FINANCIAL ADVICE (DYOR)", fontsize=10.5, fontweight="bold", color="#B91C1C", ha="center", va="center", zorder=3)
    ax.text(0.50, 0.095, "Wajib Disiplin Pasang Stop Loss & Hitung Risk : Reward Ratio sebelum entry! Batasi risiko 1-2% modal.", fontsize=8.2, fontweight="bold", color="#7F1D1D", ha="center", va="center", zorder=3)

    ax.text(0.08, 0.038, "Analyst : RWY Capital AI Sniper System | Keputusan investasi merupakan tanggung jawab pribadi masing-masing.", fontsize=7.8, color="#64748B", style="italic", va="center", zorder=3)

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

    if not picks:
        return {
            "date": target_date,
            "results": [],
            "hit_target_count": 0,
            "win_rate": 0.0,
            "avg_max_gain": 0.0,
            "shield_active": True,
            "note": "IHSG Crash Shield Aktif — Tidak ada posisi beli yang dibuka (100% Cash Defense)."
        }

    results = []
    hit_target_count = 0
    total_max_gain = 0.0

    for p in picks:
        sym = p["ticker"]
        base_price = p["last_price"]
        target = p["target"]
        support = p["support"]

        # Fetch harga langsung via yfinance
        _ticker_jk = clean_ticker(sym)
        try:
            _tk = yf.Ticker(_ticker_jk)
            _df = _tk.history(period="5d", interval="1d")
            if _df is not None and not _df.empty:
                if _df.index.tz is not None:
                    _df.index = _df.index.tz_convert(WIB)
                _target_rows = _df[_df.index.strftime('%Y-%m-%d') == target_date]
                if not _target_rows.empty:
                    _row = _target_rows.iloc[-1]
                    _idx = _df.index.get_loc(_row.name)
                    # Modal wajib dari penutupan hari kemarin jika base_price sama dengan harga close hari ini
                    _prev_close = int(_df.iloc[_idx - 1]["Close"]) if _idx > 0 else int(_row["Open"])
                    if base_price == int(_row["Close"]) or base_price <= 0:
                        base_price = _prev_close
                    high = int(_row["High"])
                    low = int(_row["Low"])
                    close = int(_row["Close"])
                else:
                    _row = _df.iloc[-1]
                    high = int(_row["High"])
                    low = int(_row["Low"])
                    close = int(_row["Close"])
            else:
                high = base_price
                low = base_price
                close = base_price
        except Exception as _e:
            print(f"[Result Fetch Error] {sym}: {_e}")
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
    return eval_summary


def generate_daily_result_image(eval_data: Dict[str, Any]) -> bytes:
    date_str = eval_data.get("date", _get_today_str())
    results = eval_data.get("results", [])
    win_rate = eval_data.get("win_rate", 0.0)

    fig = plt.figure(figsize=(7.5, 9.6), dpi=220)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    ax.set_facecolor("#FFFFFF")
    bg_box = patches.Rectangle((0, 0), 1, 1, facecolor="#F8FAFD", edgecolor="none", zorder=0)
    ax.add_patch(bg_box)

    top_bar = patches.Rectangle((0, 0.985), 1, 0.015, facecolor="#059669", edgecolor="none", zorder=1)
    ax.add_patch(top_bar)

    # Logo mark
    circle_outer = patches.Circle((0.14, 0.88), 0.055, facecolor="#ECFDF5", edgecolor="#059669", linewidth=2.5, zorder=2)
    ax.add_patch(circle_outer)
    circle_inner = patches.Circle((0.14, 0.88), 0.035, facecolor="#059669", edgecolor="none", zorder=3)
    ax.add_patch(circle_inner)
    ax.text(0.14, 0.88, "RWY", fontsize=11, fontweight="bold", color="#FFFFFF", ha="center", va="center", zorder=4)
    ax.text(0.14, 0.81, "Result", fontsize=12, fontweight="bold", color="#059669", ha="center", va="center", zorder=4)

    # Title
    ax.text(0.48, 0.89, "Daily", fontsize=28, fontweight="bold", color="#0F172A", ha="center", va="center", zorder=3)
    ax.text(0.48, 0.83, "Result Hari Ini", fontsize=26, fontweight="bold", color="#059669", ha="center", va="center", zorder=3)

    # Date
    ax.text(0.88, 0.89, date_str, fontsize=13, fontweight="bold", color="#334155", ha="right", va="center", zorder=3)
    ax.text(0.88, 0.84, "Penutupan Bursa", fontsize=11, color="#64748B", ha="right", va="center", zorder=3)

    # Win rate badge banner
    badge_bg = patches.FancyBboxPatch((0.15, 0.74), 0.70, 0.055, boxstyle="round,pad=0.01,rounding_size=0.02", facecolor="#ECFDF5", edgecolor="#10B981", linewidth=1.5, zorder=2)
    ax.add_patch(badge_bg)
    ax.text(0.50, 0.767, f"TARGET WIN RATE: {win_rate:.0f}%  ({eval_data.get('hit_target_count', 0)}/3 Capai TP)", fontsize=13, fontweight="bold", color="#065F46", ha="center", va="center", zorder=3)

    # Items
    y_positions = [0.62, 0.45, 0.28]
    for idx, (r, y) in enumerate(zip(results[:3], y_positions)):
        ax.text(0.20, y + 0.035, f"#{r['ticker']}", fontsize=28, fontweight="bold", color="#0F172A", va="center", zorder=3)
        ax.text(0.20, y - 0.010, f"Entry: {r['entry_price']:,}", fontsize=12, color="#475569", va="center", zorder=3)
        ax.text(0.20, y - 0.035, f"Target: {r['target']:,}", fontsize=12, color="#059669", fontweight="bold", va="center", zorder=3)

        is_hit = r['hit_target']
        status_text = "TARGET HIT!" if is_hit else ("PROFIT" if r['close_gain_pct'] > 0 else "KONSOLIDASI")
        gain_str = f"+{r['max_gain_pct']:.1f}%" if r['max_gain_pct'] >= 0 else f"{r['max_gain_pct']:.1f}%"
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


def format_daily_stock_pick_caption(picks: List[Dict[str, Any]], date_str: str = None, market_warning: Dict[str, Any] = None) -> str:
    if not picks:
        from ihsg_crash_shield import detect_ihsg_crash_shield, format_crash_shield_warning
        shield = detect_ihsg_crash_shield()
        return format_crash_shield_warning(shield)

    # Ambil market_warning dari cache jika tidak dipass
    if market_warning is None:
        try:
            today_str = _get_today_str()
            history = load_picks_history()
            market_warning = history.get(today_str, {}).get("market_warning")
            if not market_warning:
                from ihsg_crash_shield import detect_ihsg_crash_shield
                sh = detect_ihsg_crash_shield()
                if sh.get("active"):
                    market_warning = {
                        "active": True,
                        "type": "CRASH_SHIELD",
                        "severity": sh.get("severity", "RISK-OFF"),
                        "reasons": sh.get("reasons", ["Koreksi pasar tajam"]),
                        "advice": "Utamakan Buy The Low & disiplin Stop Loss 5.5%!"
                    }
                else:
                    from rwy_alpha_scanner import get_market_compass
                    cmp = get_market_compass()
                    if cmp.get("status") == "BEARISH":
                        market_warning = {
                            "active": True,
                            "type": "BEARISH_TREND",
                            "severity": "BEARISH DOWNTREND",
                            "reasons": [
                                "IHSG di bawah level SMA20 & SMA50",
                                cmp.get("advice", "Tekanan jual pasar")
                            ],
                            "advice": cmp.get("advice", "Utamakan Buy The Low & pasang SL 5.5%!")
                        }
        except Exception:
            market_warning = None

    t_info = get_target_trading_day()
    if not date_str:
        date_str = t_info["formatted_id"]

    lines = []

    # 1. WARNING BANNER JIKA ADA RISIKO PASAR (NON-BLOCKING)
    if market_warning and market_warning.get("active"):
        reasons_list = market_warning.get("reasons", [])
        reasons_str = " | ".join(reasons_list[:2]) if reasons_list else "Tekanan pasar makro"
        lines.extend([
            "⚠️ <b>PERINGATAN RISIKO PASAR (BEARISH / VOLATILITAS TINGGI)</b> ⚠️",
            f"🛡️ <b>Status Makro:</b> <code>{market_warning.get('severity', 'RISK-OFF')}</code>",
            f"📉 <b>Indikasi:</b> <i>{reasons_str}</i>",
            "🎯 <b>STRATEGI ROBOT: BUY THE LOW (SMART MONEY ABSORPTION)</b>",
            "✨ <i>Risiko pasar di-warn saja (sinyal belanja tetap jalan!). Robot memprioritaskan saham-saham di harga bawah (area diskon/support) yang terdeteksi sedang diserap dan diakumulasi oleh Bandar / Smart Money!</i>",
            "━━━━━━━━━━━━━━━━━━━",
            ""
        ])

    if t_info["is_prep"]:
        lines.extend([
            f"📋 <b>DAILY STOCK PICK — PERSIAPAN BUKA BURSA HARI {t_info['target_day_name'].upper()}</b> 🎯",
            f"📅 <b>Target Trading:</b> <code>{t_info['formatted_id']} (Buka Sesi 1 09:00 WIB)</code>",
            f"🏖️ <i>Catatan: Bursa saat ini sedang libur akhir pekan. 3 saham di bawah ini adalah rekomendasi watchlist terkuat untuk eksekusi saat bursa dibuka kembali hari {t_info['target_day_name']} pagi!</i>",
            "━━━━━━━━━━━━━━━━━━━",
            f"<b>Rekomendasi 3 Saham Pilihan untuk Hari {t_info['target_day_name']}:</b>",
            ""
        ])
    else:
        lines.extend([
            "📋 <b>DAILY STOCK PICK HARI INI (08:30 WIB)</b> 🎯",
            f"📅 <i>Tanggal: {date_str} (30 Menit Menuju Buka Sesi 1)</i>",
            "━━━━━━━━━━━━━━━━━━━",
            "Berikut 3 saham terbaik hasil screening algoritma AI & Whale Accumulation:",
            ""
        ])

    has_alpha_bagger = any(p.get("is_rwy_alpha") for p in picks[:3])
    if has_alpha_bagger:
        lines.append(
            "🔥 <b>[TEMUAN EMAS RWY ALPHA SCANNER TERDETEKSI!]</b> 💎\n"
            "✨ <i>RWY Alpha Scanner menemukan kandidat saham berpotensi <b>BUY THE LOW & MULTI-BAGGER RUNNER</b> hari ini! "
            "Saham di bawah ini menunjukkan lonjakan akumulasi bandar masif dan penyerapan volume di area diskon/support!</i>\n"
        )

    for idx, p in enumerate(picks[:3], 1):
        gain_str = f"+{p.get('gain_potential_pct', 0)}%"
        risk_str = f"-{p.get('risk_pct', 5.5)}%"
        rr_str = f"1 : {p.get('risk_reward', 2.0)}"
        sl_val = p.get('stop_loss', int(p['last_price'] * 0.945))

        if p.get("is_rwy_alpha"):
            tag_text = p.get('rwy_tag', '🚀 CALON BAGGER')
            rwy_badge = f" [{tag_text}]"
            banner_line = f"💎 <b>[TEMUAN EMAS RWY ALPHA SCANNER: {tag_text}!]</b> 🚀\n"
        else:
            rwy_badge = ""
            banner_line = ""

        lines.append(
            f"{banner_line}<b>{idx}. #{p['ticker']}</b> — <code>Entry: Rp {p['last_price']:,}</code>{rwy_badge}\n"
            f"   • 🎯 <b>Target TP   :</b> <code>Rp {p['target']:,}</code> (<b>{gain_str}</b>)\n"
            f"   • ⛔ <b>Stop Loss   :</b> <code>Rp {sl_val:,}</code> (<b>{risk_str}</b>) <i>[Wajib Pasang!]</i>\n"
            f"   • ⚖️ <b>Risk:Reward :</b> <b>{rr_str}</b>\n"
            f"   • 🛡️ <b>Support     :</b> <code>Rp {p['support']:,}</code>\n"
            f"   • 💡 <i>Katalis     : {p['reason']}</i>\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append(
        "🧗‍♂️ <b>ATURAN TANGGA PROTEKSI CUAN (ROBOT RWY V2):</b>\n"
        "1. <b>Level 1 (+3.5% Profit):</b> Geser SL ke modal + fee (<b>+0.8% net</b>). Saham hijau <b>DILARANG</b> berbalik merah!\n"
        "2. <b>Level 2 (+7.5% Profit):</b> Kunci SL di <b>+4.0%</b> untuk mengamankan cuan.\n"
        "3. <b>Level 3 (+15.0% Profit):</b> Kunci SL di <b>+10.0%</b>.\n"
        "4. <b>Uncapped Runner:</b> Jika saham ditarik kencang (+28% s/d +50%+), ikuti dengan trailing stop lebar agar multi-bagger tertangkap utuh!"
    )
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append(
        "💡 <b>PERBEDAAN FITUR RESMI:</b>\n"
        "• <code>/pick</code> : 3 Saham Portofolio Resmi Terkurasi (Trading Plan Komplit).\n"
        "• <code>/scan</code> : Radar Pemindai Multi-Saham Seluruh Pasar Real-Time."
    )
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append(
        "⚠️ <b>DISCLAIMER &amp; MANAJEMEN RISIKO:</b>\n"
        "• <b>DYOR:</b> Analisis kuantitatif algoritma, bukan ajakan jual/beli.\n"
        "• <b>DISIPLIN SL:</b> Selalu pasang Stop Loss ketat 5.5% saat entry!"
    )
    return "\n".join(lines)


def format_daily_result_caption(eval_data: Dict[str, Any], date_str: str = None) -> str:
    if eval_data.get("shield_active"):
        return (
            "🌇 <b>DAILY RESULT EVALUASI SORE (16:15 WIB)</b> 🛡️\n"
            f"📅 <i>Tanggal: {date_str or eval_data.get('date', _get_today_str())}</i>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🛡️ <b>STATUS: IHSG CRASH SHIELD ACTIVE (CASH IS KING)</b>\n"
            "✅ <b>Hasil Proteksi Modal:</b> 100% Dana Tunai Aman!\n"
            "💡 <i>Bot tidak membuka posisi belanja hari ini demi melindungi modal dari risiko sistemik pasar. Portofolio terselamatkan dari potensi penurunan bursa!</i>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Ketik <code>/prediksi</code> untuk melihat proyeksi arah IHSG esok hari.</i>"
        )

    now = datetime.now(WIB) if WIB else datetime.now()
    is_weekend = now.weekday() in (5, 6)

    results = eval_data.get("results", [])
    win_rate = eval_data.get("win_rate", 0.0)
    avg_gain = eval_data.get("avg_max_gain", 0.0)

    if is_weekend:
        lines = [
            "🌇 <b>DAILY RESULT EVALUASI PENUTUPAN TERAKHIR (JUMAT)</b> 📊",
            "📅 <i>Sesi Evaluasi: Penutupan Bursa Terakhir (Jumat Sesi 2)</i>",
            "🏖️ <i>Catatan: Bursa libur akhir pekan. Data di bawah mengevaluasi hasil kinerja sesi bursa terakhir.</i>",
            "━━━━━━━━━━━━━━━━━━━",
            f"🏆 <b>Target Win Rate:</b> <b>{win_rate:.0f}%</b> ({eval_data.get('hit_target_count', 0)}/{len(results)} Capai Target TP)",
            f"🚀 <b>Rata-rata Maks Gain:</b> <b>+{avg_gain:.2f}%</b>",
            "━━━━━━━━━━━━━━━━━━━",
            "<b>Rincian Hasil Kinerja Saham:</b>",
            ""
        ]
    else:
        lines = [
            "🌇 <b>DAILY RESULT &amp; EVALUASI STOCK PICK HARI INI (16:15 WIB)</b> 📊",
            f"📅 <i>Tanggal: {date_str or eval_data.get('date', _get_today_str())} (Penutupan Bursa)</i>",
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
