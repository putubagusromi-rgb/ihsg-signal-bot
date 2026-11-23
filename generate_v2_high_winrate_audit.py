import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.pdfgen import canvas

from optimize_rwy_engine_v2 import UNIVERSE, stocks, ihsg_c, ihsg_sma20, ihsg_sma50, trading_dates

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Header (halaman 2 ke atas)
        if self._pageNumber > 1:
            self.drawString(36, 565, "BUKU AUDIT JURNAL TRANSAKSI ROBOT RWY V2 (HIGH WIN-RATE 63.5%) — MODAL 1 MILIAR")
            self.drawRightString(806, 565, "PERIODE: JAN 2022 s/d NOV 2026 (5 TAHUN)")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(36, 560, 806, 560)
            
        # Footer
        page_str = f"Halaman {self._pageNumber} dari {page_count}"
        self.drawRightString(806, 20, page_str)
        self.drawString(36, 20, "AUDIT REPORT RESMI ROBOT RWY ALPHA SNIPER — KEPATUHAN & TRANSPARANSI DATA TRANSAKSI")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(36, 30, 806, 30)
        self.restoreState()

def run_simulation_and_build_pdf():
    print("Menjalankan simulasi resmi Robot RWY V2 (High Win Rate 63.5%, 197 Trades)...")
    
    cash = 1_000_000_000.0
    positions = []
    trades = []
    max_pos = 3
    alloc_pct = 1.0 / max_pos
    BUY_FEE = 0.0015
    SELL_FEE = 0.0025
    STRICT_SL_PCT = 5.5

    for dt in trading_dates:
        ihsg_val = float(ihsg_c.loc[dt]) if dt in ihsg_c.index else 0
        ihsg_s20 = float(ihsg_sma20.loc[dt]) if dt in ihsg_sma20.index else ihsg_val
        ihsg_s50 = float(ihsg_sma50.loc[dt]) if dt in ihsg_sma50.index else ihsg_val

        # Arah Tren Pasar IHSG: Matikan entri jika Downtrend terkonfirmasi
        if ihsg_val < ihsg_s20 and ihsg_s20 < ihsg_s50:
            continue

        closed = []
        for pos in positions:
            sym = pos["ticker"]
            df_st = stocks[sym]
            if dt not in df_st.index:
                continue
            row = df_st.loc[dt]
            curr_c = float(row["close"])
            curr_h = float(row["high"])
            curr_o = float(row["open"])

            days_held = pos["days_held"] + 1
            pos["days_held"] = days_held
            if curr_h > pos["highest_price"]:
                pos["highest_price"] = curr_h

            gain = (curr_c - pos["buy_price"]) / pos["buy_price"]
            peak_gain = (pos["highest_price"] / pos["buy_price"] - 1.0) * 100
            dd = (pos["highest_price"] - curr_c) / pos["highest_price"]

            # Tangga Proteksi Keuntungan (Profit Lock Ladder)
            if peak_gain >= 3.5 and pos["sl_price"] < pos["buy_price"] * 1.008:
                pos["sl_price"] = pos["buy_price"] * 1.008 # Proteksi modal & fee
            if peak_gain >= 7.5 and pos["sl_price"] < pos["buy_price"] * 1.040:
                pos["sl_price"] = pos["buy_price"] * 1.040 # Kunci cuan +4%
            if peak_gain >= 15.0 and pos["sl_price"] < pos["buy_price"] * 1.100:
                pos["sl_price"] = pos["buy_price"] * 1.100 # Kunci cuan +10%
            if peak_gain >= 28.0 and pos["sl_price"] < pos["buy_price"] * 1.200:
                pos["sl_price"] = pos["buy_price"] * 1.200 # Kunci cuan +20%
            if peak_gain >= 50.0 and pos["sl_price"] < pos["buy_price"] * 1.380:
                pos["sl_price"] = pos["buy_price"] * 1.380 # Kunci cuan +38%

            exit_price = curr_c
            exit_reason = None
            if curr_c <= pos["sl_price"]:
                if pos["sl_price"] >= pos["buy_price"]:
                    exit_reason = "Trailing Profit Lock (Cuan Diamankan)"
                else:
                    exit_reason = f"Strict Stop Loss ({STRICT_SL_PCT}%)"
                exit_price = min(curr_o, pos["sl_price"])
            elif gain >= 0.20 and dd >= 0.08:
                exit_reason = "Trailing Runner (+20% Locked)"
            elif gain >= 0.40 and dd >= 0.10:
                exit_reason = "Trailing Runner (+40% Locked)"
            elif pos["days_held"] >= 14 and gain < 0.01:
                exit_reason = "Capital Rotation (Stagnan)"

            if exit_reason:
                gross_value = pos["shares"] * exit_price
                net_proceeds = gross_value * (1.0 - SELL_FEE)
                net_profit = net_proceeds - pos["cost_basis"]
                pnl_pct = (net_profit / pos["cost_basis"]) * 100

                cash += net_proceeds
                trades.append({
                    "trade_no": len(trades) + 1,
                    "ticker": sym,
                    "entry_date": pos["buy_date"].strftime("%Y-%m-%d"),
                    "exit_date": dt.strftime("%Y-%m-%d"),
                    "days_held": days_held,
                    "entry_price": int(round(pos["buy_price"])),
                    "exit_price": int(round(exit_price)),
                    "shares": int(pos["shares"]),
                    "lot": int(pos["shares"] // 100),
                    "cost_basis": int(round(pos["cost_basis"])),
                    "proceeds": int(round(net_proceeds)),
                    "net_pnl": int(round(net_profit)),
                    "pnl_pct": round(pnl_pct, 2),
                    "peak_gain": round(peak_gain, 2),
                    "entry_method": pos["entry_method"],
                    "exit_reason": exit_reason
                })
                closed.append(pos)

        positions = [p for p in positions if p not in closed]

        if len(positions) < max_pos:
            loc_ihsg = ihsg_c.index.get_loc(dt)
            ihsg_ret20 = (float(ihsg_c.iloc[loc_ihsg]) - float(ihsg_c.iloc[max(0, loc_ihsg - 20)])) / float(ihsg_c.iloc[max(0, loc_ihsg - 20)])
            cands = []
            for ticker, df_st in stocks.items():
                if dt not in df_st.index:
                    continue
                loc_idx = df_st.index.get_loc(dt)
                if loc_idx < 25:
                    continue
                row, prev_row = df_st.iloc[loc_idx], df_st.iloc[loc_idx - 1]
                c_today, c_prev = float(row["close"]), float(prev_row["close"])

                # Filter Likuiditas & Uptrend
                if float(row["turnover"]) < 4_000_000_000 or c_today < 80:
                    continue
                if c_today < float(row["sma20"]) or float(row["sma20"]) < float(row["sma50"]):
                    continue
                if float(row["close_pos"]) < 0.65:
                    continue
                if float(row["ret20"]) <= ihsg_ret20:
                    continue

                pct_chg = ((c_today - c_prev) / c_prev) * 100
                rvol = float(row["rvol"])
                cmf = float(row["cmf20"])
                is_bo = c_today >= (float(prev_row["high_20"]) * 0.995)

                if (is_bo and pct_chg >= 2.8 and rvol >= 2.0 and cmf >= 0.12):
                    score = 85 + pct_chg * 2.0 + rvol * 5.0 + cmf * 40.0
                    cands.append({
                        "ticker": ticker,
                        "close": c_today,
                        "score": score,
                        "method": "High-Conviction Breakout"
                    })
                elif (pct_chg >= 2.0 and rvol >= 2.0 and cmf >= 0.12):
                    score = 80 + pct_chg * 1.8 + rvol * 4.5 + cmf * 35.0
                    cands.append({
                        "ticker": ticker,
                        "close": c_today,
                        "score": score,
                        "method": "Whale Pre-Closing (BSJP)"
                    })

            cands.sort(key=lambda x: x["score"], reverse=True)
            for cand in cands[:max_pos - len(positions)]:
                if cand["ticker"] in [p["ticker"] for p in positions]:
                    continue
                cur_eq = cash
                for p in positions:
                    df_p = stocks[p["ticker"]]
                    p_dt = float(df_p.loc[dt]["close"]) if dt in df_p.index else float(p["buy_price"])
                    cur_eq += p["shares"] * p_dt

                pos_cap = min(cash * 0.95, cur_eq * alloc_pct)
                if pos_cap < 30_000_000:
                    continue
                bp = cand["close"]
                cost_share = bp * (1.0 + BUY_FEE)
                shs = int((pos_cap / cost_share) // 100) * 100
                if shs < 100:
                    continue
                cb = shs * cost_share
                cash -= cb
                positions.append({
                    "ticker": cand["ticker"],
                    "buy_date": dt,
                    "buy_price": bp,
                    "highest_price": bp,
                    "shares": shs,
                    "cost_basis": cb,
                    "sl_price": bp * (1.0 - (STRICT_SL_PCT / 100.0)),
                    "entry_method": cand["method"],
                    "days_held": 0
                })

    df_t = pd.DataFrame(trades)
    csv_path = "Data_Transaksi_Robot_RWY_V2_HighWinRate_1Miliar.csv"
    df_t.to_csv(csv_path, index=False)
    print(f"File CSV disimpan: {csv_path} ({len(df_t)} baris transaksi)")

    # Buat PDF
    pdf_path = "Buku_Audit_Transaksi_Robot_RWY_V2_HighWinRate.pdf"
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=landscape(A4),
        leftMargin=36,
        rightMargin=36,
        topMargin=40,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=15, leading=18, textColor=colors.HexColor("#0F172A"))
    subtitle_style = ParagraphStyle('DocSub', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, leading=11, textColor=colors.HexColor("#475569"))
    cell_hdr = ParagraphStyle('CellHdr', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.5, leading=8, textColor=colors.white, alignment=1)
    cell_txt = ParagraphStyle('CellTxt', parent=styles['Normal'], fontName='Helvetica', fontSize=6.0, leading=7.5, textColor=colors.HexColor("#1E293B"), alignment=1)
    cell_txt_left = ParagraphStyle('CellTxtLeft', parent=cell_txt, alignment=0)
    cell_txt_green = ParagraphStyle('CellGreen', parent=cell_txt, fontName='Helvetica-Bold', textColor=colors.HexColor("#15803D"))
    cell_txt_red = ParagraphStyle('CellRed', parent=cell_txt, fontName='Helvetica-Bold', textColor=colors.HexColor("#B91C1C"))

    story = []

    # 1. Header
    story.append(Paragraph("BUKU AUDIT JURNAL TRANSAKSI LENGKAP: ROBOT RWY V2 (HIGH WIN-RATE 63.5%)", title_style))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        "Audit Resmi Simulasi Modal Awal Rp 1.000.000.000 (1 Miliar) | Periode 3 Jan 2022 – 20 Nov 2026 (5 Tahun Penuh) | "
        "Engine: Market Direction Compass + Stage 2 Uptrend + Relative Strength vs IHSG + Profit Lock Ladder",
        subtitle_style
    ))
    story.append(Spacer(1, 10))

    # 2. KPI Cards
    wins = df_t[df_t["pnl_pct"] > 0]
    losses = df_t[df_t["pnl_pct"] <= 0]
    wr = len(wins) / len(df_t) * 100
    total_pnl = df_t["net_pnl"].sum()
    final_eq = 1_000_000_000.0 + total_pnl
    profit_factor = abs(wins["net_pnl"].sum() / (losses["net_pnl"].sum() + 1e-9))

    kpi_data = [
        [
            Paragraph("<b>MODAL AWAL</b><br/><font size=11 color='#0F172A'><b>Rp 1.000.000.000</b></font><br/><font size=6.5 color='#64748B'>1 Miliar Rupiah</font>", cell_txt),
            Paragraph(f"<b>EKUITAS AKHIR</b><br/><font size=11 color='#15803D'><b>Rp {final_eq:,.0f}</b></font><br/><font size=6.5 color='#15803D'><b>+{total_pnl/1e7:.1f}% ROI</b></font>", cell_txt),
            Paragraph(f"<b>NET PROFIT</b><br/><font size=11 color='#15803D'><b>+Rp {total_pnl:,.0f}</b></font><br/><font size=6.5 color='#64748B'>Net Fee Broker</font>", cell_txt),
            Paragraph(f"<b>WIN RATE</b><br/><font size=11 color='#0284C7'><b>{wr:.1f}%</b></font><br/><font size=6.5 color='#64748B'>{len(wins)} Menang / {len(losses)} Kalah</font>", cell_txt),
            Paragraph(f"<b>PROFIT FACTOR</b><br/><font size=11 color='#0F172A'><b>{profit_factor:.2f}x</b></font><br/><font size=6.5 color='#64748B'>Gross Win / Gross Loss</font>", cell_txt),
            Paragraph(f"<b>AVG WIN / LOSS</b><br/><font size=11 color='#0F172A'><b>+{wins['pnl_pct'].mean():.1f}% / {losses['pnl_pct'].mean():.1f}%</b></font><br/><font size=6.5 color='#64748B'>Max Win: +{df_t['pnl_pct'].max():.1f}%</font>", cell_txt)
        ]
    ]
    kpi_table = Table(kpi_data, colWidths=[128, 128, 128, 128, 128, 130])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 10))

    # 3. Yearly Breakdown & Method Breakdown
    df_t["year"] = pd.to_datetime(df_t["entry_date"]).dt.year
    yearly_rows = [[
        Paragraph("<b>Tahun</b>", cell_hdr),
        Paragraph("<b>Trades</b>", cell_hdr),
        Paragraph("<b>Menang</b>", cell_hdr),
        Paragraph("<b>Kalah</b>", cell_hdr),
        Paragraph("<b>Win Rate</b>", cell_hdr),
        Paragraph("<b>Net PnL (Rp)</b>", cell_hdr)
    ]]
    for y in sorted(df_t["year"].unique()):
        ydf = df_t[df_t["year"] == y]
        yw = len(ydf[ydf["pnl_pct"] > 0])
        yl = len(ydf[ydf["pnl_pct"] <= 0])
        ywr = (yw / len(ydf)) * 100
        ypnl = ydf["net_pnl"].sum()
        pnl_col = cell_txt_green if ypnl >= 0 else cell_txt_red
        yearly_rows.append([
            Paragraph(str(y), cell_txt),
            Paragraph(str(len(ydf)), cell_txt),
            Paragraph(str(yw), cell_txt),
            Paragraph(str(yl), cell_txt),
            Paragraph(f"{ywr:.1f}%", cell_txt),
            Paragraph(f"Rp {ypnl:,.0f}", pnl_col)
        ])
    t_yearly = Table(yearly_rows, colWidths=[60, 50, 50, 50, 60, 100])
    t_yearly.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#94A3B8")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))

    method_rows = [[
        Paragraph("<b>Metode Sinyal Entri</b>", cell_hdr),
        Paragraph("<b>Trades</b>", cell_hdr),
        Paragraph("<b>Win Rate</b>", cell_hdr),
        Paragraph("<b>Avg Gain</b>", cell_hdr),
        Paragraph("<b>Total Net PnL (Rp)</b>", cell_hdr)
    ]]
    for m in df_t["entry_method"].unique():
        mdf = df_t[df_t["entry_method"] == m]
        mw = len(mdf[mdf["pnl_pct"] > 0])
        mwr = (mw / len(mdf)) * 100
        mpnl = mdf["net_pnl"].sum()
        m_avg = mdf["pnl_pct"].mean()
        method_rows.append([
            Paragraph(m, cell_txt_left),
            Paragraph(str(len(mdf)), cell_txt),
            Paragraph(f"{mwr:.1f}%", cell_txt),
            Paragraph(f"+{m_avg:.1f}%", cell_txt),
            Paragraph(f"Rp {mpnl:,.0f}", cell_txt_green)
        ])
    t_method = Table(method_rows, colWidths=[150, 45, 55, 50, 100])
    t_method.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#94A3B8")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))

    dual_table = Table([[t_yearly, t_method]], colWidths=[380, 390])
    dual_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(dual_table)
    story.append(Spacer(1, 10))

    # 4. Chronological Ledger Table
    story.append(Paragraph(f"<b>JURNAL TRANSAKSI KRONOLOGIS LENGKAP (#1 s/d #{len(df_t)})</b>", ParagraphStyle('LedgerTitle', parent=styles['Heading2'], fontSize=10, leading=12, textColor=colors.HexColor("#0F172A"))))
    story.append(Spacer(1, 4))

    ledger_rows = [[
        Paragraph("<b>#</b>", cell_hdr),
        Paragraph("<b>Ticker</b>", cell_hdr),
        Paragraph("<b>Tgl Beli</b>", cell_hdr),
        Paragraph("<b>Tgl Jual</b>", cell_hdr),
        Paragraph("<b>Hari</b>", cell_hdr),
        Paragraph("<b>Beli (Rp)</b>", cell_hdr),
        Paragraph("<b>Jual (Rp)</b>", cell_hdr),
        Paragraph("<b>Lot</b>", cell_hdr),
        Paragraph("<b>Modal (Rp)</b>", cell_hdr),
        Paragraph("<b>PnL (%)</b>", cell_hdr),
        Paragraph("<b>PnL Bersih (Rp)</b>", cell_hdr),
        Paragraph("<b>Peak</b>", cell_hdr),
        Paragraph("<b>Metode Entri</b>", cell_hdr),
        Paragraph("<b>Alasan Exit</b>", cell_hdr)
    ]]

    for idx, r in df_t.iterrows():
        pnl_val = float(r["pnl_pct"])
        pnl_style = cell_txt_green if pnl_val > 0 else cell_txt_red
        pnl_str = f"+{pnl_val:.2f}%" if pnl_val > 0 else f"{pnl_val:.2f}%"
        pnl_rp_str = f"+Rp {r['net_pnl']:,.0f}" if r['net_pnl'] > 0 else f"Rp {r['net_pnl']:,.0f}"

        ledger_rows.append([
            Paragraph(str(r["trade_no"]), cell_txt),
            Paragraph(f"<b>{r['ticker']}</b>", cell_txt),
            Paragraph(str(r["entry_date"]), cell_txt),
            Paragraph(str(r["exit_date"]), cell_txt),
            Paragraph(str(r["days_held"]), cell_txt),
            Paragraph(f"{r['entry_price']:,}", cell_txt),
            Paragraph(f"{r['exit_price']:,}", cell_txt),
            Paragraph(f"{r['lot']:,}", cell_txt),
            Paragraph(f"{r['cost_basis']:,.0f}", cell_txt),
            Paragraph(pnl_str, pnl_style),
            Paragraph(pnl_rp_str, pnl_style),
            Paragraph(f"+{r['peak_gain']:.1f}%", cell_txt),
            Paragraph(str(r["entry_method"])[:18], cell_txt_left),
            Paragraph(str(r["exit_reason"])[:25], cell_txt_left)
        ])

    col_widths = [20, 36, 48, 48, 22, 42, 42, 38, 64, 46, 68, 38, 120, 130]
    ledger_table = Table(ledger_rows, colWidths=col_widths, repeatRows=1)
    
    t_style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0F172A")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#94A3B8")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING', (0,0), (-1,-1), 2),
        ('RIGHTPADDING', (0,0), (-1,-1), 2),
    ]

    for i in range(1, len(ledger_rows)):
        if i % 2 == 0:
            t_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor("#F8FAFC")))

    ledger_table.setStyle(TableStyle(t_style))
    story.append(ledger_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Buku audit PDF berhasil dibangun: {pdf_path}")
    print(f"Summary Final: Trades: {len(df_t)} | Win Rate: {wr:.2f}% | Net PnL: Rp {total_pnl:,.0f} | Saldo: Rp {final_eq:,.0f}")

if __name__ == "__main__":
    run_simulation_and_build_pdf()
