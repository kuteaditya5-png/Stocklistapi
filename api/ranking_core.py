"""Single source of truth for the frozen v1.5 'Trend + Low Vol' ranking model.

Before this module existed, the scoring formula was written out by hand in
five places inside `monthly_ranker.py` and the live `/api/portfolio` endpoint
used a completely different, never-backtested rubric. Every consumer now calls
the functions below, so the model that is validated is the model that ships.

Nothing here changes the frozen weights. `base_score` and `sideways_score`
reproduce exactly the arithmetic that was previously inlined.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Frozen v1.1 / v1.2 cross-sectional weights. Used in BULLISH and BEARISH
# regimes, and as the baseline everywhere in the research code.
BASE_WEIGHTS = {
    "rs63": 0.25,
    "rs21": 0.15,
    "r63": 0.15,
    "r126": 0.10,
    "trend": 0.10,
    "lowvol": 0.10,
    "d52": 0.10,
    "vr": 0.05,
}

# Frozen v1.5 'Trend + Low Vol' winner. Applied only in SIDEWAYS regimes.
SIDEWAYS_WEIGHTS = {
    "rs63": 0.22,
    "rs21": 0.12,
    "r63": 0.08,
    "r126": 0.05,
    "trend": 0.23,
    "lowvol": 0.20,
    "d52": 0.07,
    "vr": 0.03,
}

FEATURE_KEYS = ["R21", "R63", "R126", "RS21", "RS63", "E50", "E200", "VOL", "D52", "VR", "NIFTY"]


def pct_rank(series: pd.Series, good: bool = True) -> pd.Series:
    """Cross-sectional percentile (0-100). `good=False` inverts, so that a low
    raw value (e.g. volatility) scores high."""
    p = series.rank(pct=True) * 100
    return p if good else 100 - p


def trend_component(price, ema50, ema200):
    """100 if price > EMA50 > EMA200, 60 if only above EMA200, else 20."""
    return np.where(
        (price > ema50) & (ema50 > ema200),
        100,
        np.where(price > ema200, 60, 20),
    )


def _combine(weights, rs63, rs21, r63, r126, trend, lowvol, d52, vr):
    return (
        weights["rs63"] * rs63
        + weights["rs21"] * rs21
        + weights["r63"] * r63
        + weights["r126"] * r126
        + weights["trend"] * trend
        + weights["lowvol"] * lowvol
        + weights["d52"] * d52
        + weights["vr"] * vr
    )


def base_score(rs63, rs21, r63, r126, trend, lowvol, d52, vr):
    """Frozen baseline score. Inputs are already percentile-ranked."""
    return _combine(BASE_WEIGHTS, rs63, rs21, r63, r126, trend, lowvol, d52, vr)


def sideways_score(rs63, rs21, r63, r126, trend, lowvol, d52, vr):
    """Frozen v1.5 SIDEWAYS score. Inputs are already percentile-ranked."""
    return _combine(SIDEWAYS_WEIGHTS, rs63, rs21, r63, r126, trend, lowvol, d52, vr)


def score_frame(z: pd.DataFrame, regime: str | None = None):
    """Score a cross-section held in a DataFrame with the raw feature columns
    (price, e50, e200, rs63, rs21, r63, r126, vol, d52, vr).

    `regime` of "SIDEWAYS" selects the frozen v1.5 weights; anything else
    (including None) uses the baseline weights, matching the research code.
    """
    trend = trend_component(z.price, z.e50, z.e200)
    args = (
        pct_rank(z.rs63),
        pct_rank(z.rs21),
        pct_rank(z.r63),
        pct_rank(z.r126),
        trend,
        pct_rank(z.vol, False),
        pct_rank(z.d52),
        pct_rank(z.vr),
    )
    return sideways_score(*args) if regime == "SIDEWAYS" else base_score(*args)


def market_regime(close: float, ema200: float, r63: float) -> str:
    """Frozen NIFTY trend-regime classifier used throughout v1.3-v2.0."""
    if close > ema200 and r63 > 0.03:
        return "BULLISH"
    if close < ema200 and r63 < -0.03:
        return "BEARISH"
    return "SIDEWAYS"


def add_features(frame: pd.DataFrame, benchmark_close: pd.Series) -> pd.DataFrame:
    """Attach the frozen point-in-time feature set to a single stock's OHLCV
    frame. Identical to the block previously copy-pasted in monthly_ranker."""
    x = frame.copy()
    x.index = pd.DatetimeIndex(x.index).tz_localize(None).normalize()
    x["NIFTY"] = benchmark_close.reindex(x.index).ffill()
    x["R21"] = x.Close.pct_change(21)
    x["R63"] = x.Close.pct_change(63)
    x["R126"] = x.Close.pct_change(126)
    x["RS21"] = x.R21 - x.NIFTY.pct_change(21)
    x["RS63"] = x.R63 - x.NIFTY.pct_change(63)
    x["E50"] = x.Close.ewm(span=50, adjust=False).mean()
    x["E200"] = x.Close.ewm(span=200, adjust=False).mean()
    x["VOL"] = x.Close.pct_change().rolling(20).std()
    x["D52"] = x.Close / x.Close.rolling(252).max() - 1
    x["VR"] = x.Volume / x.Volume.rolling(20).mean()
    return x


def forward_return_stats(close: pd.Series, horizon: int = 21) -> dict | None:
    """Empirical distribution of this stock's own realised `horizon`-day
    returns over the supplied history.

    This replaces the previous hand-picked `(score - 55) * 0.22` formula. It is
    a measured historical dispersion, not a forecast, and callers are expected
    to label it as such.
    """
    r = (close.shift(-horizon) / close - 1).dropna() * 100
    if len(r) < 60:
        return None
    return {
        "samples": int(len(r)),
        "p05": round(float(np.percentile(r, 5)), 1),
        "p20": round(float(np.percentile(r, 20)), 1),
        "median": round(float(np.percentile(r, 50)), 1),
        "p80": round(float(np.percentile(r, 80)), 1),
        "positive_rate": round(float((r > 0).mean() * 100), 1),
    }
