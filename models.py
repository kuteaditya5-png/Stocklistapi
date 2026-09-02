from pydantic import BaseModel
from typing import List, Optional


class ScoreBreakdown(BaseModel):
    fundamentals: float
    financial_health: float
    valuation: float
    technicals: float
    management: float
    risk: float


class StockResult(BaseModel):
    symbol: str
    company_name: Optional[str] = None
    current_price: Optional[float] = None
    stocklens_score: float
    recommendation: str
    risk_level: str
    score_breakdown: ScoreBreakdown
    positives: List[str]
    red_flags: List[str]
    last_updated: str
