from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import yfinance as yf
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

API_DIR = Path(__file__).resolve().parent
ROOT = API_DIR.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from scanner import analyse_stock
from universe import NIFTY_50

app = FastAPI(title="StockLens AI", version="0.6.0")

STATIC = ROOT / "static"
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
def home():
    return FileResponse(ROOT / "index.html", media_type="text/html")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.6.0"}


def _within_price(price, min_price: float, max_price: float) -> bool:
    if price is None:
        return False
    try:
        p = float(price)
    except (TypeError, ValueError):
        return False

    if min_price > 0 and p < min_price:
        return False
    if max_price > 0 and p > max_price:
        return False
    return True


def _batch_price_prefilter(
    symbols: list[str],
    min_price: float,
    max_price: float,
    max_candidates: int,
) -> tuple[list[str], dict[str, float]]:
    """
    Search the full NIFTY 50 for the chosen price band using a lightweight
    batch daily-price call, then perform the heavier StockLens analysis only
    on matching candidates. If the batch call fails, fall back safely.
    """
    if min_price <= 0 and max_price <= 0:
        return symbols[:max_candidates], {}

    prices: dict[str, float] = {}

    try:
        raw = yf.download(
            symbols,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
            group_by="ticker",
        )

        if raw is not None and not raw.empty:
            if isinstance(raw.columns, pd.MultiIndex):
                level0 = set(raw.columns.get_level_values(0))
                for symbol in symbols:
                    if symbol not in level0:
                        continue
                    try:
                        close = raw[symbol]["Close"].dropna()
                        if not close.empty:
                            prices[symbol] = float(close.iloc[-1])
                    except Exception:
                        pass
            else:
                # Defensive path for a single-symbol-like response.
                if "Close" in raw.columns and symbols:
                    close = raw["Close"].dropna()
                    if not close.empty:
                        prices[symbols[0]] = float(close.iloc[-1])

        matched = [
            symbol
            for symbol in symbols
            if symbol in prices
            and _within_price(prices[symbol], min_price, max_price)
        ]

        if matched:
            return matched[:max_candidates], prices

    except Exception:
        pass

    # Fallback: analyze a normal capped slice, with an exact price filter
    # applied after analysis.
    return symbols[:max_candidates], prices


def scan(
    limit: int,
    min_price: float = 0,
    max_price: float = 0,
) -> tuple[list[dict], list[dict], int]:
    candidates, _ = _batch_price_prefilter(
        NIFTY_50,
        min_price=min_price,
        max_price=max_price,
        max_candidates=limit,
    )

    out = []
    errors = []

    with ThreadPoolExecutor(max_workers=min(5, len(candidates) or 1)) as ex:
        fs = {ex.submit(analyse_stock, s): s for s in candidates}
        for f in as_completed(fs):
            symbol = fs[f]
            try:
                row = f.result()
                if _within_price(row.get("current_price"), min_price, max_price):
                    out.append(row)
            except Exception as e:
                errors.append({"symbol": symbol, "error": str(e)})

    out.sort(key=lambda x: x.get("stocklens_score", 0), reverse=True)
    return out, errors, len(candidates)


@app.get("/api/ranking")
def ranking(
    top: int = Query(3, ge=1, le=5),
    limit_universe: int = Query(10, ge=3, le=20),
    min_price: float = Query(0, ge=0),
    max_price: float = Query(0, ge=0),
):
    rows, errors, analysed = scan(
        limit_universe,
        min_price=min_price,
        max_price=max_price,
    )
    return {
        "analysed": analysed,
        "matched": len(rows),
        "failed": len(errors),
        "top": rows[:top],
        "errors": errors[:5],
    }


@app.get("/api/intraday")
def intraday(
    capital: float = Query(50000, gt=0),
    risk_pct: float = Query(1.0, gt=0, le=3),
    limit_universe: int = Query(10, ge=3, le=20),
    min_price: float = Query(0, ge=0),
    max_price: float = Query(0, ge=0),
):
    from intraday import analyse_intraday

    candidates, _ = _batch_price_prefilter(
        NIFTY_50,
        min_price=min_price,
        max_price=max_price,
        max_candidates=limit_universe,
    )

    rows = []
    errors = []

    with ThreadPoolExecutor(max_workers=min(5, len(candidates) or 1)) as ex:
        fs = {
            ex.submit(analyse_intraday, s, capital, risk_pct): s
            for s in candidates
        }
        for f in as_completed(fs):
            symbol = fs[f]
            try:
                row = f.result()
                price = row.get("price")

                if not _within_price(price, min_price, max_price):
                    continue
                if price is None or float(price) > capital:
                    # NSE cash-equity prototype assumes at least one whole share
                    # must fit inside the supplied capital.
                    continue

                price = float(price)
                max_affordable_qty = int(capital // price)
                row["max_affordable_qty"] = max_affordable_qty
                row["capital_used"] = round(row.get("quantity", 0) * price, 2)
                row["cash_left"] = round(
                    max(0, capital - row["capital_used"]), 2
                )
                rows.append(row)

            except Exception as e:
                errors.append({"symbol": symbol, "error": str(e)})

    order = {"BUY": 2, "SELL": 2, "NO TRADE": 0}
    rows.sort(
        key=lambda x: (
            order.get(x.get("signal"), 0),
            x.get("confidence", 0),
        ),
        reverse=True,
    )

    tradeable = [x for x in rows if x.get("signal") != "NO TRADE"]

    return {
        "mode": "intraday",
        "analysed": len(candidates),
        "matched_price_filter": len(rows),
        "top": tradeable[:3],
        "no_trade_count": len(rows) - len(tradeable),
        "errors": errors[:5],
        "price_filter": {
            "min": min_price,
            "max": max_price or None,
        },
        "disclaimer": (
            "Intraday signals are model outputs, not guaranteed outcomes "
            "or investment advice."
        ),
    }


@app.get("/api/portfolio")
def portfolio(
    amount: float = Query(..., gt=0),
    risk: str = Query("moderate"),
    limit_universe: int = Query(10, ge=3, le=20),
    min_price: float = Query(0, ge=0),
    max_price: float = Query(0, ge=0),
):
    rows, errors, analysed = scan(
        limit_universe,
        min_price=min_price,
        max_price=max_price,
    )

    risk = risk.lower()
    picks = []

    for r in rows:
        current_price = r.get("current_price")
        if current_price is None:
            continue

        price = float(current_price)

        # Delivery-equity prototype uses whole shares only.
        affordable_qty = int(amount // price)
        if affordable_qty < 1:
            continue

        capital_used = affordable_qty * price
        cash_left = amount - capital_used

        score = float(r.get("stocklens_score", 0))
        rb = r.get("score_breakdown", {}) or {}
        tech = float(rb.get("technicals", 50))

        # Prototype one-month scenario band. This is intentionally an estimate,
        # not a promise of future return.
        center = max(
            -2.0,
            min(8.0, (score - 55) * 0.22 + (tech - 50) * 0.05),
        )
        width = {
            "low": 3.0,
            "moderate": 4.5,
            "high": 6.0,
        }.get(risk, 4.5)

        low = center - width
        high = center + width
        downside = min(low, -2.0)

        # Estimate only the invested shares; untouched cash remains cash.
        estimated_value_low = (
            cash_left + capital_used * (1 + low / 100)
        )
        estimated_value_high = (
            cash_left + capital_used * (1 + high / 100)
        )
        downside_value = (
            cash_left + capital_used * (1 + downside / 100)
        )

        picks.append({
            **r,
            "affordability": {
                "share_price": round(price, 2),
                "affordable_qty": affordable_qty,
                "capital_used": round(capital_used, 2),
                "cash_left": round(cash_left, 2),
            },
            "one_month_estimate": {
                "expected_return_low_pct": round(low, 1),
                "expected_return_high_pct": round(high, 1),
                "estimated_value_low": round(estimated_value_low, 2),
                "estimated_value_high": round(estimated_value_high, 2),
                "downside_value": round(downside_value, 2),
                "confidence": round(max(40, min(85, score)), 1),
            },
        })

        if len(picks) >= 3:
            break

    return {
        "investment_amount": amount,
        "risk": risk,
        "horizon": "1 month",
        "analysed": analysed,
        "matched_price_filter": len(rows),
        "top": picks,
        "failed": len(errors),
        "price_filter": {
            "min": min_price,
            "max": max_price or None,
        },
        "disclaimer": (
            "Scenario estimates are model outputs, not guaranteed returns "
            "or investment advice."
        ),
    }
