from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import FastAPI, HTTPException, Query

from .scanner import analyse_stock
from .universe import NIFTY_50

app = FastAPI(
    title="StockLens AI API",
    version="0.3.0",
    description="Stock ranking and research API for StockLens AI.",
)


@app.get("/api")
def api_home():
    return {
        "app": "StockLens AI",
        "version": "0.3.0",
        "status": "running",
        "deployment": "Vercel",
        "endpoints": [
            "/api/health",
            "/api/stock/RELIANCE",
            "/api/ranking?top=5&limit_universe=5",
            "/docs",
        ],
        "disclaimer": "Research tool only; not investment advice.",
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": "0.3.0",
        "deployment": "vercel-ready",
    }


@app.get("/api/stock/{symbol}")
def stock_analysis(symbol: str):
    yahoo_symbol = symbol.upper()
    if not yahoo_symbol.endswith(".NS"):
        yahoo_symbol += ".NS"

    try:
        return analyse_stock(yahoo_symbol)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to analyse {symbol}: {exc}",
        )


@app.get("/api/ranking")
def ranking(
    top: int = Query(default=5, ge=1, le=10),
    limit_universe: int = Query(default=5, ge=1, le=20),
):
    """
    Vercel-safe starter scan.

    The public serverless version intentionally caps one request at 20 stocks.
    Full NIFTY 50 scans should later be handled through cached/scheduled jobs.
    """
    symbols = NIFTY_50[:limit_universe]
    results = []
    errors = []

    with ThreadPoolExecutor(max_workers=min(5, len(symbols))) as executor:
        futures = {
            executor.submit(analyse_stock, symbol): symbol
            for symbol in symbols
        }

        for future in as_completed(futures):
            symbol = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append({
                    "symbol": symbol,
                    "error": str(exc),
                })

    results.sort(
        key=lambda row: row["stocklens_score"],
        reverse=True,
    )

    return {
        "universe": "NIFTY 50 starter universe",
        "scanned": len(results),
        "failed": len(errors),
        "top": results[:top],
        "errors": errors[:10],
        "disclaimer": (
            "Ranking is model-based research output, "
            "not investment advice."
        ),
    }
