from __future__ import annotations

import numpy as np
import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = out["Close"]

    out["EMA20"] = close.ewm(span=20, adjust=False).mean()
    out["EMA50"] = close.ewm(span=50, adjust=False).mean()
    out["EMA200"] = close.ewm(span=200, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out["RSI14"] = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["MACD"] = ema12 - ema26
    out["MACD_SIGNAL"] = out["MACD"].ewm(span=9, adjust=False).mean()
    out["MACD_HIST"] = out["MACD"] - out["MACD_SIGNAL"]

    if "Volume" in out.columns:
        out["VOL20"] = out["Volume"].rolling(20).mean()
        out["VOLUME_RATIO"] = out["Volume"] / out["VOL20"].replace(0, np.nan)
    else:
        out["VOLUME_RATIO"] = np.nan

    out["HIGH_20"] = out["High"].rolling(20).max() if "High" in out.columns else close.rolling(20).max()

    return out


def latest_technical_snapshot(df: pd.DataFrame) -> dict:
    data = add_indicators(df)
    row = data.iloc[-1]

    def safe(v):
        if pd.isna(v):
            return None
        return float(v)

    return {
        "close": safe(row.get("Close")),
        "ema20": safe(row.get("EMA20")),
        "ema50": safe(row.get("EMA50")),
        "ema200": safe(row.get("EMA200")),
        "rsi14": safe(row.get("RSI14")),
        "macd": safe(row.get("MACD")),
        "macd_signal": safe(row.get("MACD_SIGNAL")),
        "macd_hist": safe(row.get("MACD_HIST")),
        "volume_ratio": safe(row.get("VOLUME_RATIO")),
        "high_20": safe(row.get("HIGH_20")),
    }
