from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf


def _indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    c = x["Close"]

    x["EMA9"] = c.ewm(span=9, adjust=False).mean()
    x["EMA20"] = c.ewm(span=20, adjust=False).mean()

    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    x["RSI"] = 100 - (100 / (1 + rs))

    # Intraday VWAP should restart every trading session.
    typical = (x["High"] + x["Low"] + x["Close"]) / 3
    tpv = typical * x["Volume"]
    sessions = pd.Index(pd.DatetimeIndex(x.index).date)
    cum_tpv = tpv.groupby(sessions).cumsum()
    cum_vol = x["Volume"].groupby(sessions).cumsum().replace(0, np.nan)
    x["VWAP"] = cum_tpv / cum_vol

    x["VOL20"] = x["Volume"].rolling(20).mean()
    x["VR"] = x["Volume"] / x["VOL20"].replace(0, np.nan)
    x["H20"] = x["High"].rolling(20).max().shift(1)
    x["L20"] = x["Low"].rolling(20).min().shift(1)

    true_range = pd.concat(
        [
            x["High"] - x["Low"],
            (x["High"] - x["Close"].shift()).abs(),
            (x["Low"] - x["Close"].shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    x["ATR"] = true_range.rolling(14).mean()

    return x


def intraday_signal_from_row(r: pd.Series) -> dict:
    """Return the exact signal logic used by live scan and backtesting."""
    p = float(r["Close"])
    bull = 0
    bear = 0
    reasons = []

    if p > float(r["VWAP"]):
        bull += 2
        reasons.append("Price above VWAP")
    else:
        bear += 2
        reasons.append("Price below VWAP")

    if float(r["EMA9"]) > float(r["EMA20"]):
        bull += 2
        reasons.append("EMA 9 above EMA 20")
    else:
        bear += 2
        reasons.append("EMA 9 below EMA 20")

    rsi = r.get("RSI")
    if pd.notna(rsi):
        rsi = float(rsi)
        if 52 <= rsi <= 70:
            bull += 1
            reasons.append("Bullish RSI momentum")
        elif 30 <= rsi <= 48:
            bear += 1
            reasons.append("Bearish RSI momentum")

    vr = r.get("VR")
    if pd.notna(vr) and float(vr) >= 1.25:
        if bull >= bear:
            bull += 1
        else:
            bear += 1
        reasons.append("Relative volume expansion")

    h20 = r.get("H20")
    l20 = r.get("L20")
    if pd.notna(h20) and p > float(h20):
        bull += 2
        reasons.append("20-bar breakout")
    if pd.notna(l20) and p < float(l20):
        bear += 2
        reasons.append("20-bar breakdown")

    edge = max(bull, bear)

    if edge < 4 or abs(bull - bear) < 2:
        return {
            "signal": "NO TRADE",
            "confidence": round(min(65, 45 + edge * 3), 1),
            "bull_score": bull,
            "bear_score": bear,
            "reasons": reasons[:5],
        }

    signal = "BUY" if bull > bear else "SELL"
    confidence = min(88, 55 + abs(bull - bear) * 5)

    return {
        "signal": signal,
        "confidence": round(confidence, 1),
        "bull_score": bull,
        "bear_score": bear,
        "reasons": reasons[:5],
    }


def trade_levels(entry: float, atr: float, signal: str) -> dict:
    risk_per_share = max(float(atr) * 0.8, float(entry) * 0.003)

    if signal == "BUY":
        stop = entry - risk_per_share
        target1 = entry + risk_per_share * 1.5
        target2 = entry + risk_per_share * 2.2
    else:
        stop = entry + risk_per_share
        target1 = entry - risk_per_share * 1.5
        target2 = entry - risk_per_share * 2.2

    return {
        "risk_per_share": risk_per_share,
        "stop_loss": stop,
        "target1": target1,
        "target2": target2,
    }


def analyse_intraday(symbol: str, capital: float = 50000, risk_pct: float = 1.0) -> dict:
    df = yf.Ticker(symbol).history(
        period="5d",
        interval="5m",
        auto_adjust=True,
    )
    if df is None or len(df) < 30:
        raise ValueError("Insufficient 5-minute data")

    x = _indicators(df).dropna(subset=["EMA9", "EMA20", "VWAP", "ATR"])
    if x.empty:
        raise ValueError("Indicators unavailable")

    r = x.iloc[-1]
    p = float(r["Close"])
    sig = intraday_signal_from_row(r)

    if sig["signal"] == "NO TRADE":
        stop = target1 = target2 = None
        qty = 0
        warnings = ["No sufficiently strong intraday edge"]
    else:
        levels = trade_levels(p, float(r["ATR"]), sig["signal"])
        stop = levels["stop_loss"]
        target1 = levels["target1"]
        target2 = levels["target2"]

        risk_rupees = capital * (risk_pct / 100)
        qty = max(
            0,
            int(
                min(
                    capital / p,
                    risk_rupees / levels["risk_per_share"],
                )
            ),
        )
        warnings = []

    return {
        "symbol": symbol.replace(".NS", ""),
        "signal": sig["signal"],
        "price": round(p, 2),
        "entry": round(p, 2),
        "stop_loss": round(stop, 2) if stop is not None else None,
        "target1": round(target1, 2) if target1 is not None else None,
        "target2": round(target2, 2) if target2 is not None else None,
        "confidence": sig["confidence"],
        "quantity": qty,
        "capital": capital,
        "risk_pct": risk_pct,
        "reasons": sig["reasons"],
        "warnings": warnings,
        "signal_time": datetime.now(timezone.utc).isoformat(),
    }
