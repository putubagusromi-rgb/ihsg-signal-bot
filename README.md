# 📊 IHSG & Whale Bandarmology Signal Bot 🇮🇩

Bot analisis teknikal dan deteksi akumulasi **Big Money / Whale (Bandarmology)** untuk Indeks Harga Saham Gabungan (IHSG) dan saham-saham Bursa Efek Indonesia (IDX) menggunakan data gratis dan real-time dari **Yahoo Finance API**.

Dilengkapi dengan antarmuka **Telegram Bot interaktif** dan **Command Line Interface (CLI)** untuk pengujian langsung di terminal.

---

## 🌟 Fitur Utama

1. **Analisis IHSG Komprehensif (`^JKSE`)**:
   - Tren pasar otomatis (EMA 20, 50, 200).
   - Momentum RSI (14) & Deteksi Oversold / Overbought.
   - MACD Cross & Histogram status.
   - Deteksi Support & Resistance dinamis (Swing High/Low & Moving Averages).
   - Rekomendasi aksi pasar (*Agresif Buy*, *Buy on Weakness*, *Wait and See*, atau *Defensif / Cash is King*).

2. **Deteksi Akumulasi Whale / Smart Money (Bandarmology Kuantitatif)**:
   - **Skor Akumulasi Whale (0 - 100)**: Klasifikasi *Big Accumulation*, *Accumulation*, *Neutral*, *Distribution*, dan *Big Distribution*.
   - **Chaikin Money Flow (CMF)**: Mengukur tekanan beli riil institusi saat harga ditutup di dekat harga tertinggi harian.
   - **Relative Volume (RVOL)**: Mendeteksi lonjakan volume anomali (> 1.5x dari rata-rata 20 hari).
   - **OBV Breakout**: Mendeteksi saat On-Balance Volume menembus rata-rata bergeraknya.
   - **Estimasi Harga Masuk Whale (VWAP)**: Menghitung perkiraan harga rata-rata beli institusi selama periode akumulasi.
   - **Estimasi Net Flow Whale**: Perkiraan nilai uang yang masuk/keluar dalam Miliar Rupiah.

3. **Trading Plan Otomatis (Swing Trading)**:
   - Area Beli (Entry Area).
   - Target Profit 1 & Target Profit 2 (TP1 / TP2).
   - Stop Loss (SL) berbasis support teknikal.
   - Perhitungan Risk to Reward Ratio (RR Ratio).

4. **Telegram Bot Interaktif & Terjadwal**:
   - Perintah interaktif: `/ihsg`, `/whale`, `/scan KODE`, `/daily`, `/help`.
   - Scheduler otomatis:
     - 🌅 **08:30 WIB**: Morning Market Briefing sebelum pembukaan sesi 1.
     - 🌇 **16:15 WIB**: Post-Market Closing Report & Top Whale Picks setelah penutupan bursa.

---

## 📁 Struktur Direktori

```text
ihsg-signal-bot/
├── .env                  # Token bot Telegram dan Chat ID
├── .env.example          # Template konfigurasi environment
├── config.py             # Konfigurasi watchlist saham, parameter indikator, jadwal
├── indicators.py         # Perhitungan teknikal (EMA, RSI, MACD, BB) & Indikator Whale (CMF, OBV, RVOL)
├── broker_summary.py     # Logika Bandarmology Kuantitatif & Adapter Broker Summary
├── signal_engine.py      # Mesin analisis IHSG, scanning saham, dan penyusunan trading plan
├── telegram_bot.py       # Bot Telegram API polling & scheduler pengirim notifikasi
├── cli.py                # Command Line Interface untuk analisis cepat di terminal
├── main.py               # Titik masuk utama untuk menjalankan bot Telegram
├── requirements.txt      # Daftar dependensi Python
└── README.md             # Panduan lengkap penggunaan
```

---

## 🚀 Panduan Instalasi & Penggunaan

### 1. Menyiapkan Python Environment

Proyek ini telah disiapkan di direktori:
`C:\Users\Pongo\.gemini\antigravity\scratch\ihsg-signal-bot`

Jika menjalankan dari terminal baru:
```bash
cd C:\Users\Pongo\.gemini\antigravity\scratch\ihsg-signal-bot
py -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

---

### 2. Menguji Langsung via Terminal (CLI Mode)

Kamu bisa langsung melihat analisis dan sinyal tanpa perlu token Telegram:

#### a. Analisis IHSG Hari Ini:
```powershell
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python cli.py --ihsg
```

#### b. Screening Saham yang Sedang Diakumulasi Whale:
```powershell
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python cli.py --whale
```

#### c. Analisis Mendalam Saham Tertentu (Contoh: BBCA / BBRI / ASII):
```powershell
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python cli.py --scan BBCA
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python cli.py --scan BMRI
```

#### d. Laporan Harian Lengkap (IHSG + Top Whale Watchlist):
```powershell
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python cli.py --daily
```

---

### 3. Menghubungkan ke Telegram Bot

1. Buka aplikasi **Telegram**, cari akun resmi **[@BotFather](https://t.me/BotFather)**.
2. Kirim pesan `/newbot` dan ikuti petunjuk untuk memberi nama bot kamu (misalnya: `MyIHSGSignalBot`).
3. Kamu akan mendapatkan **API Token** (contoh: `7123456789:AAHfd7-xk...`).
4. Untuk mengetahui **Chat ID** kamu:
   - Cari bot **[@userinfobot](https://t.me/userinfobot)** di Telegram dan tekan Start. Catat angka `Id` kamu (misal: `123456789`).
5. Buka file `.env` di folder proyek dan masukkan nilainya:
   ```env
   TELEGRAM_BOT_TOKEN=7123456789:AAHfd7-xk...
   TELEGRAM_CHAT_ID=123456789
   ```
6. Jalankan bot:
   ```powershell
   $env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python main.py
   ```
7. Buka bot kamu di Telegram dan ketik `/start` atau `/ihsg`!

---

## 💬 Perintah Bot Telegram

| Perintah | Deskripsi |
| :--- | :--- |
| `/start` atau `/help` | Menampilkan menu perintah dan panduan bot |
| `/ihsg` | Menampilkan level terkini IHSG, tren EMA, RSI, MACD, Support/Resistance & rekomendasi aksi |
| `/whale` atau `/akumulasi` | Menampilkan peringkat saham Big Cap yang sedang dimasuki Big Money / Whale |
| `/scan [KODE]` | Analisis teknikal & bandarmology lengkap untuk kode saham tertentu (misal: `/scan BBCA` atau `/scan BREN`) |
| `/daily` | Ringkasan harian menyeluruh pasar modal Indonesia |

---

## 🧠 Cara Membaca Indikator Whale & Bandarmology

1. **Skor Akumulasi Whale (0 - 100)**:
   - **75 - 100 (BIG ACCUMULATION 🟢🟢🟢)**: Terjadi akumulasi masif. Dominasi pembeli besar sangat tinggi dengan kenaikan volume di atas rata-rata.
   - **60 - 74 (ACCUMULATION 🟢)**: Tekanan beli institusi terdeteksi secara konsisten.
   - **40 - 59 (NEUTRAL ⚪)**: Konsolidasi harga wajar / sideways.
   - **25 - 39 (DISTRIBUTION 🔴)**: Tekanan jual mulai mendominasi.
   - **0 - 24 (BIG DISTRIBUTION 🔴🔴🔴)**: Aksi buang barang / pelepasan posisi dalam jumlah besar.

2. **Chaikin Money Flow (CMF)**:
   - CMF > +0.05 menandakan akumulasi institusional (uang masuk).
   - CMF < -0.05 menandakan distribusi / aliran dana keluar.

3. **Relative Volume (RVOL)**:
   - Nilai RVOL > 1.5x menandakan transaksi hari ini 150% lebih besar dari rata-rata 20 hari bursa, menjadi indikator awal entri *Whale*.

4. **Whale VWAP (Volume Weighted Average Price)**:
   - Estimasi harga rata-rata barang yang dikumpulkan oleh institusi. Jika harga pasar saat ini masih dekat dengan harga VWAP Whale (< 3%), maka rasio risiko/keuntungan untuk entri masih sangat optimal.
