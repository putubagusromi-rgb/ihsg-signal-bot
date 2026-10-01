import sys
import argparse
from tabulate import tabulate

from config import (
    LQ45_WATCHLIST,
    KOMPAS100_WATCHLIST,
    ALL_IDX_TICKERS,
    INDICATOR_CONFIG
)
from signal_engine import analyze_ihsg, analyze_single_stock, scan_whale_watchlist


def print_ihsg_cli():
    print("\n" + "="*60)
    print("📊 ANALISIS PASAR & SINYAL IHSG (^JKSE) - YAHOO FINANCE")
    print("="*60)
    data = analyze_ihsg()
    if "error" in data:
        print(f"Error: {data['error']}")
        return

    table = [
        ["Tanggal Data", data["date"]],
        ["Level Penutupan", f"{data['close']:,.2f}"],
        ["Perubahan", f"{data['pct_change']:+.2f}% ({data['change_pts']:+.2f} pts)"],
        ["Tren Pasar", f"{data['trend_emoji']} {data['trend']}"],
        ["RSI (14)", f"{data['rsi']:.1f} ({data['rsi_desc']})"],
        ["MACD", data["macd_desc"]],
        ["Chaikin Money Flow (CMF)", f"{data['cmf']:.3f}"],
        ["Skor Akumulasi Pasar", f"{data['whale_score']}/100"],
        ["Support 1 / 2", f"{data['levels']['support_1']:,.0f} / {data['levels']['support_2']:,.0f}"],
        ["Resistance 1 / 2", f"{data['levels']['resistance_1']:,.0f} / {data['levels']['resistance_2']:,.0f}"],
        ["REKOMENDASI AKSI", f">>> {data['action']} <<<"],
        ["Catatan Strategi", data["action_note"]]
    ]
    print(tabulate(table, tablefmt="fancy_grid"))
    print()


def print_single_stock_cli(symbol: str):
    print(f"\n" + "="*60)
    print(f"🔍 ANALISIS SAHAM & WHALE ACCUMULATION: #{symbol.upper()}")
    print("="*60)
    data = analyze_single_stock(symbol)
    if "error" in data:
        print(f"Error: {data['error']}")
        return

    w = data["whale"]
    tp = data["trading_plan"]
    chg = data["pct_change"]

    flow_str = f"Rp {w['whale_flow_billion']:+.1f} Miliar"

    table = [
        ["Kode Saham", f"#{data['ticker']}"],
        ["Harga Terakhir", f"Rp {int(data['close']):,} ({chg:+.2f}%)"],
        ["Status Sinyal", f"{data['signal_badge']} ({data['signal']})"],
        ["Whale Accumulation Status", f"{w['whale_status']} ({w['whale_score']}/100)"],
        ["Volume vs 20-MA (RVOL)", f"{w['rvol']:.2f}x rata-rata"],
        ["Estimasi Net Flow Whale", flow_str],
        ["Est. Harga Masuk Whale (VWAP)", f"Rp {int(w['whale_vwap']):,} ({w['pct_from_vwap']:+.1f}% vs harga saat ini)"],
        ["EMA 20 / EMA 50", f"Rp {int(data['ema20']):,} / Rp {int(data['ema50']):,}"],
        ["RSI (14)", f"{data['rsi']:.1f}"],
        ["Support / Resistance", f"Rp {int(data['levels']['support_1']):,} / Rp {int(data['levels']['resistance_1']):,}"],
        ["Trading Plan: Area Beli", f"Rp {tp['entry_area']}"],
        ["Trading Plan: Target 1 & 2", f"Rp {tp['tp1']:,} / Rp {tp['tp2']:,}"],
        ["Trading Plan: Stop Loss (SL)", f"Rp {tp['stop_loss']:,}"],
        ["Risk / Reward Ratio", f"{tp['rr_ratio']}x"]
    ]
    print(tabulate(table, tablefmt="fancy_grid"))

    if w["entry_reasons"]:
        print("\n🔍 Fakta & Alasan Akumulasi:")
        for r in w["entry_reasons"]:
            print(f" • {r}")
    print()


def print_whale_watchlist_cli(universe: str = "lq45", top_n: int = 15):
    if universe.lower() in ["all", "semua", "958"]:
        tickers = ALL_IDX_TICKERS
        title = f"SELURUH {len(tickers)} SAHAM BEI (Filter Transaksi >= Rp500 Jt)"
        min_turnover = INDICATOR_CONFIG.get("min_turnover_billion", 0.5)
        workers = 25
    elif universe.lower() in ["100", "kompas100", "kompas"]:
        tickers = KOMPAS100_WATCHLIST
        title = f"KOMPAS 100 ({len(tickers)} Saham)"
        min_turnover = 0.0
        workers = 15
    else:
        tickers = LQ45_WATCHLIST
        title = f"LQ45 ({len(tickers)} Saham Terlikuid)"
        min_turnover = 0.0
        workers = 15

    print("\n" + "="*75)
    print(f"🐋 SCREENING WHALE ACCUMULATION: {title}")
    print("="*75)

    stocks = scan_whale_watchlist(tickers, min_turnover_billion=min_turnover, max_workers=workers)
    if not stocks:
        print("Tidak ada saham yang memenuhi kriteria.")
        return

    headers = ["No", "Ticker", "Harga", "Chg %", "Whale Status", "Score", "RVOL", "Est. Flow", "Target 1", "Stop Loss"]
    rows = []
    for idx, s in enumerate(stocks[:top_n], 1):
        w = s["whale"]
        tp = s["trading_plan"]
        flow = f"{w['whale_flow_billion']:+.1f}M"
        rows.append([
            idx,
            s["ticker"],
            f"Rp{int(s['close']):,}",
            f"{s['pct_change']:+.1f}%",
            w["whale_status"],
            f"{w['whale_score']}/100",
            f"{w['rvol']:.1f}x",
            flow,
            f"Rp{tp['tp1']:,}",
            f"Rp{tp['stop_loss']:,}"
        ])

    print(tabulate(rows, headers=headers, tablefmt="fancy_grid"))
    print(f"\nMenampilkan Top {min(top_n, len(stocks))} dari total {len(stocks)} saham aktif.")
    print("Tip: Jalankan `py cli.py --scan KODE` untuk detail saham individual.\n")


def main():
    parser = argparse.ArgumentParser(description="IHSG & Whale Signal CLI")
    parser.add_argument("--ihsg", action="store_true", help="Analisis kondisi indeks IHSG")
    parser.add_argument("--whale", action="store_true", help="Screening saham yang diakumulasi Whale")
    parser.add_argument("--universe", type=str, default="lq45", choices=["lq45", "100", "all"], help="Pilihan cakupan saham: lq45, 100, atau all (958 saham)")
    parser.add_argument("--scan", type=str, help="Analisis detail saham tertentu (contoh: --scan BBCA)")
    parser.add_argument("--daily", action="store_true", help="Laporan harian komplit (IHSG + Whale)")

    args = parser.parse_args()

    if args.ihsg:
        print_ihsg_cli()
    elif args.whale:
        print_whale_watchlist_cli(universe=args.universe)
    elif args.scan:
        print_single_stock_cli(args.scan)
    elif args.daily:
        print_ihsg_cli()
        print_whale_watchlist_cli(universe=args.universe, top_n=10)
    else:
        print_ihsg_cli()
        print("Gunakan perintah berikut:")
        print("  py cli.py --ihsg                  -> Sinyal pasar IHSG")
        print("  py cli.py --whale                 -> Screening LQ45 (45 saham)")
        print("  py cli.py --whale --universe 100  -> Screening Kompas100 (100 saham)")
        print("  py cli.py --whale --universe all  -> Screening SELURUH 958 saham BEI")
        print("  py cli.py --scan BBCA             -> Analisis mendalam saham BBCA")
        print("  py cli.py --daily                 -> Laporan harian lengkap")


if __name__ == "__main__":
    main()
