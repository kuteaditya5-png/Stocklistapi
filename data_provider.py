from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pandas as pd
import yfinance as yf


def get_price_history(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval, auto_adjust=True)

    if df is None or df.empty:
        raise ValueError(f"No price history returned for {symbol}")

    return df.dropna(subset=["Close"]).copy()


def get_company_snapshot(symbol: str) -> Dict[str, Any]:
    """
    Best-effort snapshot from yfinance.

    Some fields may be unavailable for some stocks or at some times, so the
    scoring engine is designed to tolerate missing values.
    """
    ticker = yf.Ticker(symbol)

    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    return {
        "symbol": symbol,
        "company_name": info.get("longName") or info.get("shortName"),
        "market_cap": info.get("marketCap"),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "price_to_book": info.get("priceToBook"),
        "peg_ratio": info.get("pegRatio"),
        "enterprise_to_ebitda": info.get("enterpriseToEbitda"),
        "roe": info.get("returnOnEquity"),
        "roa": info.get("returnOnAssets"),
        "profit_margin": info.get("profitMargins"),
        "operating_margin": info.get("operatingMargins"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "debt_to_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "operating_cashflow": info.get("operatingCashflow"),
        "free_cashflow": info.get("freeCashflow"),
        "held_percent_insiders": info.get("heldPercentInsiders"),
        "held_percent_institutions": info.get("heldPercentInstitutions"),
        "current_price": info.get("currentPrice"),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
