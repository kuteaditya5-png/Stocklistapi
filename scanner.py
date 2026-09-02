from __future__ import annotations

from data_provider import get_company_snapshot, get_price_history
from indicators import latest_technical_snapshot
from scoring import calculate_stocklens_score


def analyse_stock(symbol: str) -> dict:
    history = get_price_history(symbol)
    technical = latest_technical_snapshot(history)
    snapshot = get_company_snapshot(symbol)

    if snapshot.get("current_price") is None:
        snapshot["current_price"] = technical.get("close")

    scored = calculate_stocklens_score(snapshot, technical)

    return {
        "symbol": symbol.replace(".NS", ""),
        "company_name": snapshot.get("company_name"),
        "current_price": snapshot.get("current_price"),
        "stocklens_score": scored["score"],
        "recommendation": scored["recommendation"],
        "risk_level": scored["risk_level"],
        "score_breakdown": scored["breakdown"],
        "positives": scored["positives"],
        "red_flags": scored["red_flags"],
        "last_updated": snapshot["last_updated"],
    }
