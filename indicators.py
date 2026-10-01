import pandas as pd
import numpy as np


def add_all_indicators(df: pd.DataFrame, config: dict = None) -> pd.DataFrame:
    """
    Menghitung seluruh indikator teknikal (EMA, RSI, MACD, BB)
    dan indikator Akumulasi Whale / Smart Money (CMF, OBV, A/D, RVOL, VWAP).
    """
    if config is None:
        from config import INDICATOR_CONFIG
        config = INDICATOR_CONFIG

    df = df.copy()

    # Pastikan data terurut berdasarkan tanggal
    df = df.sort_index()

    # 1. Moving Averages (EMA 20, 50, 200)
    df["EMA_20"] = df["Close"].ewm(span=config["ema_short"], adjust=False).mean()
    df["EMA_50"] = df["Close"].ewm(span=config["ema_medium"], adjust=False).mean()
    df["EMA_200"] = df["Close"].ewm(span=config["ema_long"], adjust=False).mean()

    # 2. Relative Strength Index (RSI 14)
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/config["rsi_period"], min_periods=config["rsi_period"], adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/config["rsi_period"], min_periods=config["rsi_period"], adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    # 3. MACD (12, 26, 9)
    ema_fast = df["Close"].ewm(span=config["macd_fast"], adjust=False).mean()
    ema_slow = df["Close"].ewm(span=config["macd_slow"], adjust=False).mean()
    df["MACD"] = ema_fast - ema_slow
    df["MACD_Signal"] = df["MACD"].ewm(span=config["macd_signal"], adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

    # 4. Bollinger Bands (20, 2)
    bb_sma = df["Close"].rolling(window=20).mean()
    bb_std = df["Close"].rolling(window=20).std()
    df["BB_Upper"] = bb_sma + (2 * bb_std)
    df["BB_Middle"] = bb_sma
    df["BB_Lower"] = bb_sma - (2 * bb_std)

    # 5. Volume Indicators & Relative Volume (RVOL)
    df["Vol_SMA20"] = df["Volume"].rolling(window=config["rvol_period"]).mean()
    # Hindari division by zero
    df["RVOL"] = np.where(df["Vol_SMA20"] > 0, df["Volume"] / df["Vol_SMA20"], 1.0)

    # 6. Chaikin Money Flow (CMF 20) - Indikator Tekanan Beli / Akumulasi Institusi
    high_low_diff = df["High"] - df["Low"]
    # Money Flow Multiplier: ((Close - Low) - (High - Close)) / (High - Low)
    mf_multiplier = np.where(
        high_low_diff != 0,
        ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / high_low_diff,
        0.0
    )
    mf_volume = mf_multiplier * df["Volume"]
    sum_mf_volume = pd.Series(mf_volume, index=df.index).rolling(window=config["cmf_period"]).sum()
    sum_volume = df["Volume"].rolling(window=config["cmf_period"]).sum()
    df["CMF"] = np.where(sum_volume > 0, sum_mf_volume / sum_volume, 0.0)

    # 7. On-Balance Volume (OBV) & OBV EMA
    obv_direction = np.where(df["Close"] > df["Close"].shift(1), 1,
                    np.where(df["Close"] < df["Close"].shift(1), -1, 0))
    df["OBV"] = (obv_direction * df["Volume"]).fillna(0).cumsum()
    df["OBV_EMA20"] = df["OBV"].ewm(span=20, adjust=False).mean()

    # 8. Accumulation / Distribution Line (A/D)
    df["AD_Line"] = pd.Series(mf_volume, index=df.index).fillna(0).cumsum()

    # 9. Estimasi VWAP 20 hari (Volume Weighted Average Price) - Proxy harga rata-rata beli institusi
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3.0
    pv_sum = (typical_price * df["Volume"]).rolling(window=20).sum()
    v_sum = df["Volume"].rolling(window=20).sum()
    df["VWAP_20"] = np.where(v_sum > 0, pv_sum / v_sum, df["Close"])

    # 10. Skor Whale / Bandarmology Accumulation Score (0 - 100)
    df["Whale_Score"], df["Whale_Status"] = calculate_whale_score_series(df)

    return df


def calculate_whale_score_series(df: pd.DataFrame):
    """
    Menghitung skor akumulasi bandar/whale komposit (0-100) untuk setiap bar:
    - CMF (Chaikin Money Flow): bobot 30 poin
    - RVOL (Relative Volume Spike): bobot 25 poin
    - OBV vs OBV EMA (Tren Aliran Volume): bobot 25 poin
    - Close Position in High-Low Range: bobot 20 poin
    """
    scores = []
    statuses = []

    for i in range(len(df)):
        row = df.iloc[i]
        score = 0

        # Komponen 1: CMF (30 Poin)
        cmf = row.get("CMF", 0.0)
        if cmf > 0.15:
            score += 30
        elif cmf > 0.05:
            score += 22
        elif cmf > 0:
            score += 15
        elif cmf > -0.05:
            score += 8
        else:
            score += 0

        # Komponen 2: Relative Volume / RVOL (25 Poin)
        rvol = row.get("RVOL", 1.0)
        if rvol >= 2.0:
            score += 25
        elif rvol >= 1.5:
            score += 20
        elif rvol >= 1.2:
            score += 15
        elif rvol >= 0.8:
            score += 10
        else:
            score += 5

        # Komponen 3: OBV vs OBV EMA20 (25 Poin)
        obv = row.get("OBV", 0)
        obv_ema = row.get("OBV_EMA20", 0)
        if obv > obv_ema:
            # OBV di atas EMA menandakan volume buying mendominasi
            score += 25
        else:
            score += 5

        # Komponen 4: Penutupan di area atas candle (20 Poin)
        hl_range = row["High"] - row["Low"]
        if hl_range > 0:
            close_pos = (row["Close"] - row["Low"]) / hl_range
            if close_pos >= 0.70:    # Tutup di 30% area tertinggi (Whale menyerap harga)
                score += 20
            elif close_pos >= 0.50:  # Tutup di paruh atas
                score += 13
            elif close_pos >= 0.30:
                score += 7
            else:
                score += 0
        else:
            score += 10

        scores.append(score)

        # Klasifikasi Status Akumulasi
        if score >= 75:
            status = "BIG ACCUMULATION"
        elif score >= 60:
            status = "ACCUMULATION"
        elif score >= 40:
            status = "NEUTRAL"
        elif score >= 25:
            status = "DISTRIBUTION"
        else:
            status = "BIG DISTRIBUTION"

        statuses.append(status)

    return pd.Series(scores, index=df.index), pd.Series(statuses, index=df.index)
