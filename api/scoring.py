from __future__ import annotations

from typing import Dict, List, Tuple


WEIGHTS = {
    "fundamentals": 35,
    "financial_health": 15,
    "valuation": 15,
    "technicals": 20,
    "management": 10,
    "risk": 5,
}


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _ratio_to_pct(value):
    if value is None:
        return None
    # yfinance commonly returns ratios as decimals, e.g. 0.18 = 18%.
    return value * 100 if abs(value) <= 2 else value


def score_fundamentals(snapshot: dict) -> Tuple[float, List[str], List[str]]:
    score = 50.0
    positives, flags = [], []

    rev = _ratio_to_pct(snapshot.get("revenue_growth"))
    earn = _ratio_to_pct(snapshot.get("earnings_growth"))
    roe = _ratio_to_pct(snapshot.get("roe"))
    margin = _ratio_to_pct(snapshot.get("profit_margin"))

    if rev is not None:
        if rev >= 15:
            score += 12; positives.append("Strong revenue growth")
        elif rev >= 8:
            score += 6
        elif rev < 0:
            score -= 12; flags.append("Revenue is declining")

    if earn is not None:
        if earn >= 15:
            score += 12; positives.append("Strong earnings growth")
        elif earn >= 8:
            score += 6
        elif earn < 0:
            score -= 14; flags.append("Earnings growth is negative")

    if roe is not None:
        if roe >= 18:
            score += 14; positives.append("High ROE")
        elif roe >= 12:
            score += 7
        elif roe < 8:
            score -= 8; flags.append("Low ROE")

    if margin is not None:
        if margin >= 15:
            score += 8
        elif margin < 5:
            score -= 7

    return _clamp(score), positives, flags


def score_financial_health(snapshot: dict) -> Tuple[float, List[str], List[str]]:
    score = 55.0
    positives, flags = [], []

    dte = snapshot.get("debt_to_equity")
    ocf = snapshot.get("operating_cashflow")
    fcf = snapshot.get("free_cashflow")

    # This is a general-company rule. Banks/NBFCs need sector-specific treatment later.
    if dte is not None:
        if dte <= 50:
            score += 18; positives.append("Debt level is relatively low")
        elif dte >= 150:
            score -= 18; flags.append("High debt-to-equity")

    if ocf is not None:
        if ocf > 0:
            score += 13; positives.append("Positive operating cash flow")
        else:
            score -= 15; flags.append("Negative operating cash flow")

    if fcf is not None:
        if fcf > 0:
            score += 10; positives.append("Positive free cash flow")
        else:
            score -= 10; flags.append("Negative free cash flow")

    return _clamp(score), positives, flags


def score_valuation(snapshot: dict) -> Tuple[float, List[str], List[str]]:
    score = 55.0
    positives, flags = [], []

    pe = snapshot.get("trailing_pe")
    pb = snapshot.get("price_to_book")
    peg = snapshot.get("peg_ratio")

    # Temporary generic bands. Phase 2 will compare each stock with sector peers
    # and its own historical valuation.
    if pe is not None:
        if 0 < pe <= 20:
            score += 15; positives.append("P/E is in a reasonable starter range")
        elif pe >= 50:
            score -= 15; flags.append("P/E is expensive on a generic basis")

    if pb is not None:
        if 0 < pb <= 3:
            score += 10
        elif pb >= 10:
            score -= 8

    if peg is not None:
        if 0 < peg <= 1.5:
            score += 10; positives.append("PEG looks reasonable")
        elif peg >= 3:
            score -= 8

    return _clamp(score), positives, flags


def score_technicals(t: dict) -> Tuple[float, List[str], List[str]]:
    score = 50.0
    positives, flags = [], []

    c = t.get("close")
    e20, e50, e200 = t.get("ema20"), t.get("ema50"), t.get("ema200")
    rsi = t.get("rsi14")
    macd = t.get("macd")
    signal = t.get("macd_signal")
    vr = t.get("volume_ratio")
    h20 = t.get("high_20")

    if c and e20 and e50:
        if c > e20 > e50:
            score += 15; positives.append("Price is above EMA20 and EMA50")
        elif c < e20 < e50:
            score -= 12; flags.append("Short-term trend is bearish")

    if c and e200:
        if c > e200:
            score += 12; positives.append("Price is above EMA200")
        else:
            score -= 10; flags.append("Price is below EMA200")

    if rsi is not None:
        if 50 <= rsi <= 65:
            score += 10; positives.append("RSI shows healthy momentum")
        elif rsi >= 75:
            score -= 7; flags.append("RSI is overbought")
        elif rsi < 35:
            score -= 7; flags.append("RSI is weak")

    if macd is not None and signal is not None:
        if macd > signal:
            score += 9; positives.append("MACD is bullish")
        else:
            score -= 5

    if vr is not None and vr >= 1.5:
        score += 7; positives.append("Volume is above its 20-day average")

    if c and h20 and c >= h20 * 0.995:
        score += 7; positives.append("Price is near a 20-day breakout")

    return _clamp(score), positives, flags


def score_management(snapshot: dict) -> Tuple[float, List[str], List[str]]:
    # yfinance does not reliably expose Indian promoter pledge/governance details.
    # Start neutral and replace this with dedicated NSE/BSE/shareholding inputs later.
    positives, flags = [], []
    insider = snapshot.get("held_percent_insiders")

    score = 50.0
    if insider is not None and insider >= 0.25:
        score += 10
        positives.append("Meaningful insider/promoter-style ownership signal")

    return _clamp(score), positives, flags


def score_risk(snapshot: dict, technical: dict) -> Tuple[float, List[str], List[str]]:
    """
    Here, higher score means LOWER observed risk.
    """
    score = 65.0
    positives, flags = [], []

    dte = snapshot.get("debt_to_equity")
    rsi = technical.get("rsi14")

    if dte is not None and dte >= 200:
        score -= 25
        flags.append("Very high leverage")

    if rsi is not None and rsi >= 80:
        score -= 15
        flags.append("Momentum is extremely stretched")

    if score >= 70:
        positives.append("No major starter-model risk flags detected")

    return _clamp(score), positives, flags


def recommendation(score: float) -> str:
    if score >= 85:
        return "STRONG CANDIDATE"
    if score >= 75:
        return "BUY CANDIDATE"
    if score >= 65:
        return "WATCHLIST"
    if score >= 50:
        return "WEAK"
    return "AVOID"


def risk_level(risk_score: float) -> str:
    if risk_score >= 70:
        return "LOW"
    if risk_score >= 45:
        return "MEDIUM"
    return "HIGH"


def calculate_stocklens_score(snapshot: Dict, technical: Dict) -> Dict:
    f, fp, ff = score_fundamentals(snapshot)
    h, hp, hf = score_financial_health(snapshot)
    v, vp, vf = score_valuation(snapshot)
    t, tp, tf = score_technicals(technical)
    m, mp, mf = score_management(snapshot)
    r, rp, rf = score_risk(snapshot, technical)

    breakdown = {
        "fundamentals": round(f, 2),
        "financial_health": round(h, 2),
        "valuation": round(v, 2),
        "technicals": round(t, 2),
        "management": round(m, 2),
        "risk": round(r, 2),
    }

    total = (
        f * WEIGHTS["fundamentals"] / 100
        + h * WEIGHTS["financial_health"] / 100
        + v * WEIGHTS["valuation"] / 100
        + t * WEIGHTS["technicals"] / 100
        + m * WEIGHTS["management"] / 100
        + r * WEIGHTS["risk"] / 100
    )

    return {
        "score": round(total, 2),
        "recommendation": recommendation(total),
        "risk_level": risk_level(r),
        "breakdown": breakdown,
        "positives": list(dict.fromkeys(fp + hp + vp + tp + mp + rp))[:6],
        "red_flags": list(dict.fromkeys(ff + hf + vf + tf + mf + rf))[:6],
    }
