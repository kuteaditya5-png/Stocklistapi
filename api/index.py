from __future__ import annotations
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

API_DIR = Path(__file__).resolve().parent
ROOT = API_DIR.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from scanner import analyse_stock
from universe import NIFTY_50

app = FastAPI(title="StockLens AI", version="0.4.0")
STATIC = ROOT/"static"
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

@app.get("/")
def home():
    return FileResponse(ROOT/"index.html", media_type="text/html")

@app.get("/api/health")
def health():
    return {"status":"ok","version":"0.4.0"}

def scan(limit):
    syms=NIFTY_50[:limit]
    out=[]; errors=[]
    with ThreadPoolExecutor(max_workers=min(5,len(syms))) as ex:
        fs={ex.submit(analyse_stock,s):s for s in syms}
        for f in as_completed(fs):
            s=fs[f]
            try: out.append(f.result())
            except Exception as e: errors.append({"symbol":s,"error":str(e)})
    out.sort(key=lambda x:x.get("stocklens_score",0), reverse=True)
    return out,errors

@app.get("/api/ranking")
def ranking(top:int=Query(3,ge=1,le=5), limit_universe:int=Query(10,ge=3,le=20)):
    rows,errors=scan(limit_universe)
    return {"scanned":len(rows),"failed":len(errors),"top":rows[:top],"errors":errors[:5]}

@app.get("/api/portfolio")
def portfolio(amount:float=Query(...,gt=0), risk:str=Query("moderate"), limit_universe:int=Query(10,ge=3,le=20)):
    rows,errors=scan(limit_universe)
    risk=risk.lower()
    # Prototype 1-month scenario bands derived from score + technical/risk quality.
    picks=[]
    for r in rows[:3]:
        score=float(r.get("stocklens_score",0))
        rb=r.get("score_breakdown",{}) or {}
        tech=float(rb.get("technicals",50))
        rq=float(rb.get("risk", rb.get("risk_quality",50)))
        # Conservative model scenarios; estimates, never guarantees.
        center=max(-2.0,min(8.0,(score-55)*0.22 + (tech-50)*0.05))
        width={"low":3.0,"moderate":4.5,"high":6.0}.get(risk,4.5)
        low=center-width
        high=center+width
        downside=min(low,-2.0)
        picks.append({
            **r,
            "one_month_estimate":{
                "expected_return_low_pct":round(low,1),
                "expected_return_high_pct":round(high,1),
                "estimated_value_low":round(amount*(1+low/100),2),
                "estimated_value_high":round(amount*(1+high/100),2),
                "downside_value":round(amount*(1+downside/100),2),
                "confidence":round(max(40,min(85,score)),1)
            }
        })
    return {
        "investment_amount":amount,"risk":risk,"horizon":"1 month",
        "scanned":len(rows),"top":picks,"failed":len(errors),
        "disclaimer":"Scenario estimates are model outputs, not guaranteed returns or investment advice."
    }
