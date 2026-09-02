from __future__ import annotations
import itertools
import numpy as np
import pandas as pd
import yfinance as yf
from indicators import add_indicators
from scoring import score_technicals

def _pct(n,d): return round(100*n/d,1) if d else 0.0
def _r(v,n=2):
    try: return round(float(v),n)
    except: return 0.0

def _extract(raw,symbol):
    if raw is None or raw.empty: return pd.DataFrame()
    if isinstance(raw.columns,pd.MultiIndex):
        l0=set(raw.columns.get_level_values(0)); l1=set(raw.columns.get_level_values(1))
        if symbol in l0: return raw[symbol].dropna(how="all").copy()
        if symbol in l1: return raw.xs(symbol,axis=1,level=1).dropna(how="all").copy()
        return pd.DataFrame()
    return raw.dropna(how="all").copy()

def _snapshot(r):
    def v(k):
        z=r.get(k); return None if pd.isna(z) else float(z)
    return {"close":v("Close"),"ema20":v("EMA20"),"ema50":v("EMA50"),"ema200":v("EMA200"),
            "rsi14":v("RSI14"),"macd":v("MACD"),"macd_signal":v("MACD_SIGNAL"),
            "macd_hist":v("MACD_HIST"),"volume_ratio":v("VOLUME_RATIO"),"high_20":v("HIGH_20")}

def _prepare(symbols,period="5y",horizon=21):
    all_syms=symbols+["^NSEI"]
    raw=yf.download(all_syms,period=period,interval="1d",auto_adjust=True,
                    progress=False,threads=True,group_by="ticker")
    histories={s:_extract(raw,s) for s in all_syms}
    bench=histories["^NSEI"]["Close"].copy()
    bench.index=pd.DatetimeIndex(bench.index).tz_localize(None).normalize()
    rows=[]; errors=[]
    for sym in symbols:
        try:
            df=histories[sym]
            if len(df)<260: raise ValueError("insufficient history")
            x=add_indicators(df).copy()
            x.index=pd.DatetimeIndex(x.index).tz_localize(None).normalize()
            x["NIFTY"]=bench.reindex(x.index).ffill()
            x["RET21"]=x["Close"].pct_change(21)
            x["RET63"]=x["Close"].pct_change(63)
            x["NRET63"]=x["NIFTY"].pct_change(63)
            x["RS63"]=x["RET63"]-x["NRET63"]
            x["DIST52H"]=x["Close"]/x["Close"].rolling(252).max()-1
            x=x.dropna(subset=["Close","EMA50","EMA200","RSI14","MACD","MACD_SIGNAL",
                               "NIFTY","RET21","RET63","RS63","DIST52H"])
            i=0
            while i+horizon<len(x):
                r=x.iloc[i]; f=x.iloc[i+horizon]
                tech=float(score_technicals(_snapshot(r))[0])
                sr=(float(f["Close"])/float(r["Close"])-1)*100
                nr=(float(f["NIFTY"])/float(r["NIFTY"])-1)*100
                rows.append({"symbol":sym.replace(".NS",""),"date":x.index[i],"tech":tech,
                    "trend":bool(r["Close"]>r["EMA50"]>r["EMA200"]),"rsi":float(r["RSI14"]),
                    "mom63":float(r["RET63"]),"rs63":float(r["RS63"]),
                    "dist52h":float(r["DIST52H"]),"ret":sr,"excess":sr-nr})
                i+=horizon
        except Exception as e: errors.append({"symbol":sym,"error":str(e)})
    return pd.DataFrame(rows),errors

def _grid():
    for tech,rs,mom,trend,rmax,near in itertools.product(
        [60,70,80],[0.0,0.02],[0.0,0.03],[False,True],[70,75],[False,True]):
        yield {"tech_min":tech,"rs63_min":rs,"mom63_min":mom,"trend_required":trend,
               "rsi_min":45,"rsi_max":rmax,"near_52w_high":near}

def _mask(df,r):
    m=(df.tech>=r["tech_min"])&(df.rs63>=r["rs63_min"])&(df.mom63>=r["mom63_min"])&\
      (df.rsi>=r["rsi_min"])&(df.rsi<=r["rsi_max"])
    if r["trend_required"]: m &= df.trend
    if r["near_52w_high"]: m &= df.dist52h>=-0.15
    return m

def _metrics(x):
    if x.empty:return {"samples":0,"positive_rate":0,"beat_nifty_rate":0,"avg_return":0,"avg_excess":0}
    return {"samples":int(len(x)),"positive_rate":_pct((x.ret>0).sum(),len(x)),
            "beat_nifty_rate":_pct((x.excess>0).sum(),len(x)),
            "avg_return":_r(x.ret.mean()),"avg_excess":_r(x.excess.mean())}

def walk_forward_monthly(symbols,period="5y"):
    df,errors=_prepare(symbols,period)
    if df.empty: raise ValueError("No historical samples")
    dates=sorted(pd.unique(df.date))
    c1=dates[int(len(dates)*.60)-1]; c2=dates[int(len(dates)*.80)-1]
    train=df[df.date<=c1]; val=df[(df.date>c1)&(df.date<=c2)]; test=df[df.date>c2]
    candidates=[]
    for rule in _grid():
        a=train[_mask(train,rule)]; b=val[_mask(val,rule)]
        if len(a)<15 or len(b)<5: continue
        ma=_metrics(a); mb=_metrics(b)
        penalty=abs(ma["avg_excess"]-mb["avg_excess"])*.35
        score=mb["avg_excess"]*1.8+(mb["beat_nifty_rate"]-50)*.035+ma["avg_excess"]*.35-penalty
        candidates.append((score,rule,ma,mb))
    if not candidates: raise ValueError("No candidate passed sample requirements")
    candidates.sort(key=lambda z:z[0],reverse=True)
    _,rule,tm,vm=candidates[0]
    um=_metrics(test[_mask(test,rule)])
    base=_metrics(test[test.tech>=65])
    passed=um["samples"]>=5 and um["avg_excess"]>0 and um["beat_nifty_rate"]>50 and um["avg_excess"]>base["avg_excess"]
    return {"engine":"1-month walk-forward optimizer","total_samples":int(len(df)),
      "split":{"train_end":str(pd.Timestamp(c1).date()),"validation_end":str(pd.Timestamp(c2).date()),
               "train_samples":int(len(train)),"validation_samples":int(len(val)),"test_samples":int(len(test))},
      "selected_rule":rule,"train":tm,"validation":vm,"unseen_test":um,
      "baseline_unseen_test":base,"approved_for_live_candidate":passed,"errors":errors,
      "notes":["Rule selected without using unseen test results.",
               "Primary objective is excess return versus NIFTY.",
               "This remains a technical market-data backtest, not full point-in-time fundamentals validation."]}
