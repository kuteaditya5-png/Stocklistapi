from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

API_DIR = Path(__file__).resolve().parent
PROJECT_DIR = API_DIR.parent

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from scanner import analyse_stock
from universe import NIFTY_50

app = FastAPI(
    title="StockLens AI",
    version="0.3.2",
    description="Stock ranking and research dashboard for the Indian market.",
)

STATIC_DIR = PROJECT_DIR / "static"
INDEX_FILE = PROJECT_DIR / "index.html"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def dashboard():
    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE, media_type="text/html")

    return {
        "app": "StockLens AI",
        "version": "0.3.2",
        "status": "running",
        "error": "index.html was not found in the repository root",
    }


@app.get("/api")
def api_home():
    return {
        "app": "StockLens AI",
        "version": "0.3.2",
        "status": "running",
        "deployment": "Vercel",
        "endpoints": [
            "/api/health",
            "/api/stock/RELIANCE",
            "/api/ranking?top=5&limit_universe=5",
        ],
        "disclaimer": "Research tool only; not investment advice.",
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": "0.3.2",
        "deployment": "vercel",
        "dashboard_file": INDEX_FILE.exists(),
        "static_folder": STATIC_DIR.exists(),
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
