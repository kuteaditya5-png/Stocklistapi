"""Live 1-month ranking.

Runs the *validated* frozen v1.5 model against the full universe in a single
batched download, rather than the unvalidated `scoring.py` rubric over the
first N alphabetical tickers.

One `yf.download` call covers all symbols, so there is no per-stock cost and
therefore no reason to truncate the universe.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from ranking_core import (
    FEATURE_KEYS,
    add_features,
    forward_return_stats,
    market_regime,
    score_frame,
)

BENCHMARK = "^NSEI"

# 2y of daily bars is the minimum that supports the 252-day 52-week high and a
# settled 200-day EMA, while keeping the single download small enough for a
# serverless request.
DEFAULT_PERIOD = "2y"
MIN_BARS = 300


def _frame(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        if symbol in set(raw.columns.get_level_values(0)):
            return raw[symbol].dropna(how="all").copy()
        if symbol in set(raw.columns.get_level_values(1)):
            return raw.xs(symbol, axis=1, level=1).dropna(how="all").copy()
    return raw.copy()


def live_monthly_ranking(
    symbols: list[str],
    top_n: int = 3,
    period: str = DEFAULT_PERIOD,
    horizon_days: int = 21,
) -> dict:
    raw = yf.download(
        symbols + [BENCHMARK],
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="ticker",
    )

    if raw is None or raw.empty:
        raise ValueError("No market data returned for the universe")

    bench = _frame(raw, BENCHMARK)
    b = bench["Close"].copy()
    b.index = pd.DatetimeIndex(b.index).tz_localize(None).normalize()

    bench_e200 = float(b.ewm(span=200, adjust=False).mean().iloc[-1])
    bench_r63 = float(b.pct_change(63).iloc[-1]) if len(b) > 63 else 0.0
    regime = market_regime(float(b.iloc[-1]), bench_e200, bench_r63)

    rows = []
    skipped = []

    for s in symbols:
        try:
            frame = _frame(raw, s)
            if frame is None or frame.empty or len(frame) < MIN_BARS:
                skipped.append(s)
                continue

            x = add_features(frame, b)
            r = x.iloc[-1]

            if any(pd.isna(r[k]) for k in FEATURE_KEYS):
                skipped.append(s)
                continue

            rows.append(
                dict(
                    symbol=s.replace(".NS", ""),
                    yahoo_symbol=s,
                    price=float(r.Close),
                    r21=float(r.R21),
                    r63=float(r.R63),
                    r126=float(r.R126),
                    rs21=float(r.RS21),
                    rs63=float(r.RS63),
                    e50=float(r.E50),
                    e200=float(r.E200),
                    vol=float(r.VOL),
                    d52=float(r.D52),
                    vr=float(r.VR),
                    history=x.Close,
                )
            )
        except Exception:
            skipped.append(s)

    if len(rows) < top_n:
        raise ValueError("Not enough usable symbols to build a ranking")

    z = pd.DataFrame([{k: v for k, v in r.items() if k != "history"} for r in rows])
    histories = {r["symbol"]: r["history"] for r in rows}

    z["score"] = score_frame(z, regime=regime)
    z["score_percentile"] = (z.score.rank(pct=True) * 100).round(1)

    picks = z.nlargest(top_n, "score").copy()

    out = []
    for _, r in picks.iterrows():
        stats = forward_return_stats(histories[r.symbol], horizon=horizon_days)

        out.append(
            {
                "symbol": r.symbol,
                "price": round(float(r.price), 2),
                "model_score": round(float(r.score), 1),
                "score_percentile": float(r.score_percentile),
                "signals": {
                    "relative_strength_3m_pct": round(float(r.rs63) * 100, 2),
                    "relative_strength_1m_pct": round(float(r.rs21) * 100, 2),
                    "return_3m_pct": round(float(r.r63) * 100, 2),
                    "return_6m_pct": round(float(r.r126) * 100, 2),
                    "below_52w_high_pct": round(float(r.d52) * 100, 2),
                    "daily_volatility_pct": round(float(r.vol) * 100, 2),
                    "above_ema50": bool(r.price > r.e50),
                    "above_ema200": bool(r.price > r.e200),
                },
                # Measured dispersion of this stock's own past 21-day returns.
                # Explicitly NOT a forecast and NOT a probability.
                "historical_1m_range": stats,
            }
        )

    return {
        "engine": "frozen v1.5 Trend + Low Vol (same model as Accuracy & Backtest)",
        "market_regime": regime,
        "universe_size": len(symbols),
        "ranked": int(len(z)),
        "skipped": len(skipped),
        "horizon_trading_days": horizon_days,
        "history_window": period,
        "top": out,
        "disclaimer": (
            "Ranking only. The historical range is this stock's own past "
            f"{horizon_days}-day return distribution, not a forecast. The model's "
            "measured monthly NIFTY-beat rate is 49%."
        ),
    }


def attach_affordability(ranking: dict, amount: float) -> dict:
    """Convert a ranking into whole-share position sizes for a given capital.

    Rupee values are derived from the *historical* percentile band, and are
    labelled as historical dispersion rather than an expected value.
    """
    for row in ranking.get("top", []):
        price = row["price"]
        qty = int(amount // price) if price > 0 else 0
        deployed = round(qty * price, 2)
        stats = row.get("historical_1m_range")

        row["affordability"] = {
            "share_price": price,
            "affordable_qty": qty,
            "capital_deployed": deployed,
            "cash_left": round(max(0.0, amount - deployed), 2),
        }

        if stats and qty > 0:
            row["historical_value_band"] = {
                "basis": "20th-80th percentile of this stock's past 1-month returns",
                "low": round(deployed * (1 + stats["p20"] / 100), 2),
                "median": round(deployed * (1 + stats["median"] / 100), 2),
                "high": round(deployed * (1 + stats["p80"] / 100), 2),
                "worst_5pct": round(deployed * (1 + stats["p05"] / 100), 2),
            }
        else:
            row["historical_value_band"] = None

    ranking["investment_amount"] = amount
    return ranking
