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
    top_n: int = 8,
    period: str = DEFAULT_PERIOD,
    horizon_days: int = 21,
    regime_filter: bool = True,
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

    # When the index is below its own 200-day average, the frozen rule sits in
    # cash rather than picking the best of a falling market.
    index_below_trend = float(b.iloc[-1]) < bench_e200

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
        "index_below_200day": bool(index_below_trend),
        "hold_cash": bool(regime_filter and index_below_trend),
        "top": out,
        "disclaimer": (
            "Ranking only. The historical range is this stock's own past "
            f"{horizon_days}-day return distribution, not a forecast."
        ),
    }


def attach_affordability(ranking: dict, amount: float) -> dict:
    """Size the whole basket, not each name against the full amount.

    Capital is split evenly across the picks and rounded down to whole shares,
    so an expensive share can leave a name unfunded. Unspent money is reported
    rather than quietly assumed away.
    """
    picks = ranking.get("top", [])
    if not picks:
        ranking["investment_amount"] = amount
        return ranking

    # A small amount cannot carry a wide basket: at 8 names, a 5,000 rupee
    # budget is 625 per name and most NSE shares cost more than that. Shrink
    # the basket to the widest size this amount can actually fund, rather than
    # listing names the person cannot buy.
    requested = len(picks)
    fitted = requested
    for n in range(requested, 0, -1):
        if all(x["price"] <= amount / n for x in picks[:n]):
            fitted = n
            break
    else:
        fitted = 1

    picks = picks[:fitted]
    ranking["top"] = picks
    per_name = amount / len(picks)
    cash = amount
    deployed_total = 0.0
    funded = 0

    for row in picks:
        price = row["price"]
        qty = int(per_name // price) if price > 0 else 0
        deployed = round(qty * price, 2)

        if qty > 0:
            funded += 1
            cash -= deployed
            deployed_total += deployed

        row["affordability"] = {
            "share_price": price,
            "budget_per_name": round(per_name, 2),
            "shares": qty,
            "capital_deployed": deployed,
            "unfunded": qty == 0,
        }

        stats = row.get("historical_1m_range")
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
    ranking["basket"] = {
        "names": len(picks),
        "requested_names": requested,
        "narrowed_for_budget": fitted < requested,
        "funded": funded,
        "unfunded": len(picks) - funded,
        "capital_deployed": round(deployed_total, 2),
        "cash_left": round(max(0.0, cash), 2),
        "note": (
            f"{amount:,.0f} rupees spreads across {requested} names at "
            f"{amount / requested:,.0f} each, which is below the share price of "
            f"some picks, so the basket was narrowed to {fitted}. A narrower "
            "basket is more concentrated and swings harder."
            if fitted < requested
            else "Split evenly across the basket and rounded down to whole shares."
        ),
    }
    return ranking
