from __future__ import annotations
from collections import defaultdict
from datetime import time
import numpy as np
import pandas as pd
import yfinance as yf

from intraday import _indicators, intraday_signal_from_row, trade_levels
from indicators import add_indicators
from scoring import score_technicals


def _r(v,n=2):
    try: return round(float(v),n)
    except: return None

def _pct(a,b): return round(a*100/b,1) if b else 0.0

def _extract(raw,symbol):
    if raw is None or raw.empty: return pd.DataFrame()
    if isinstance(raw.columns,pd.MultiIndex):
        l0=set(raw.columns.get_level_values(0)); l1=set(raw.columns.get_level_values(1))
        if symbol in l0: return raw[symbol].dropna(how="all").copy()
        if symbol in l1: return raw.xs(symbol,axis=1,level=1).dropna(how="all").copy()
        return pd.DataFrame()
    return raw.copy()

def _download(symbols,period,interval):
    raw=yf.download(symbols,period=period,interval=interval,auto_adjust=True,
                    progress=False,threads=True,group_by="ticker")
    return {s:_extract(raw,s) for s in symbols}

def _local(idx):
    x=pd.DatetimeIndex(idx)
    return x.tz_localize("Asia/Kolkata") if x.tz is None else x.tz_convert("Asia/Kolkata")

def _metrics(trades):
    if not trades:
        return {"signals":0,"t1_rate":0,"positive_rate":0,"avg_r":0,"profit_factor":0,"max_drawdown_r":0}
    rv=np.array([x["r"] for x in trades],dtype=float)
    wins=rv[rv>0]; losses=rv[rv<0]
    gp=wins.sum() if len(wins) else 0
    gl=abs(losses.sum()) if len(losses) else 0
    pf=gp/gl if gl else (99 if gp else 0)
    cum=np.cumsum(rv); peak=np.maximum.accumulate(np.insert(cum,0,0))[1:]
    dd=abs(float((cum-peak).min())) if len(cum) else 0
    return {"signals":len(trades),
            "t1_rate":_pct(sum(x["outcome"]=="TARGET1" for x in trades),len(trades)),
            "positive_rate":_pct(sum(x["r"]>0 for x in trades),len(trades)),
            "avg_r":_r(rv.mean(),2),"profit_factor":_r(pf,2),"max_drawdown_r":_r(dd,2)}

def _eval_trade(day,pos,sig,maxbars=12):
    row=day.iloc[pos]; entry=float(row.Close); levels=trade_levels(entry,float(row.ATR),sig)
    risk=float(levels["risk_per_share"]); stop=float(levels["stop_loss"]); target=float(levels["target1"])
    fut=day.iloc[pos+1:pos+1+maxbars]
    if fut.empty:return None
    outcome="TIMEOUT"; exitp=float(fut.iloc[-1].Close)
    for _,b in fut.iterrows():
        hi=float(b.High); lo=float(b.Low)
        if sig=="BUY": sh=lo<=stop; th=hi>=target
        else: sh=hi>=stop; th=lo<=target
        if sh: outcome="STOP"; exitp=stop; break
        if th: outcome="TARGET1"; exitp=target; break
    direction=1 if sig=="BUY" else -1
    return {"outcome":outcome,"r":direction*(exitp-entry)/risk}

def compare_intraday(symbols,period="1mo"):
    histories=_download(symbols,period,"5m")
    old=[]; new=[]; errors=[]
    for sym in symbols:
        try:
            df=histories[sym]
            if len(df)<40: raise ValueError("insufficient data")
            x=_indicators(df).dropna(subset=["EMA9","EMA20","VWAP","ATR"]).copy()
            x["_ts"]=_local(x.index); x["_day"]=[t.date() for t in x["_ts"]]
            # 15m trend proxy from rolling 3x5m closes: reduces noise without look-ahead.
            x["EMA15_FAST"]=x["Close"].ewm(span=15,adjust=False).mean()
            x["EMA15_SLOW"]=x["Close"].ewm(span=30,adjust=False).mean()
            for _,day in x.groupby("_day"):
                elig=day[day["_ts"].map(lambda t: time(9,45)<=t.time()<=time(14,15))]
                if len(elig)<3: continue
                got_old=got_new=False
                for idx,row in elig.iterrows():
                    sig=intraday_signal_from_row(row)
                    if sig["signal"]=="NO TRADE": continue
                    pos=day.index.get_loc(idx)
                    if isinstance(pos,slice): pos=pos.start
                    if not got_old:
                        tr=_eval_trade(day,pos,sig["signal"])
                        if tr: old.append({"symbol":sym,**tr}); got_old=True
                    # v0.8 candidate: higher score, relative volume, aligned slower trend,
                    # and price meaningfully on correct side of VWAP.
                    price=float(row.Close); vwap=float(row.VWAP)
                    vr=float(row.VR) if pd.notna(row.VR) else 0
                    aligned=(sig["signal"]=="BUY" and row.EMA15_FAST>row.EMA15_SLOW) or \
                            (sig["signal"]=="SELL" and row.EMA15_FAST<row.EMA15_SLOW)
                    vwap_edge=abs(price-vwap)/price
                    if (not got_new and sig["confidence"]>=80 and vr>=1.15 and aligned and vwap_edge>=0.001):
                        tr=_eval_trade(day,pos,sig["signal"])
                        if tr: new.append({"symbol":sym,**tr}); got_new=True
                    if got_old and got_new: break
        except Exception as e: errors.append({"symbol":sym,"error":str(e)})
    return {"old":_metrics(old),"candidate":_metrics(new),"errors":errors,
            "candidate_rules":["Start after 09:45 and stop new entries after 14:15",
                               "Model score ≥80","Relative volume ≥1.15",
                               "Slower trend must agree with trade direction",
                               "Price must be at least 0.10% away from VWAP"]}

def _snap(r):
    def v(k):
        z=r.get(k); return None if pd.isna(z) else float(z)
    return {"close":v("Close"),"ema20":v("EMA20"),"ema50":v("EMA50"),"ema200":v("EMA200"),
            "rsi14":v("RSI14"),"macd":v("MACD"),"macd_signal":v("MACD_SIGNAL"),
            "macd_hist":v("MACD_HIST"),"volume_ratio":v("VOLUME_RATIO"),"high_20":v("HIGH_20")}

def compare_monthly(symbols,period="2y",horizon=21):
    histories=_download(symbols+["^NSEI"],period,"1d")
    bench=histories["^NSEI"]["Close"].copy()
    bench.index=pd.DatetimeIndex(bench.index).normalize()
    old=[]; new=[]; errors=[]
    for sym in symbols:
        try:
            df=histories[sym]
            if len(df)<230: raise ValueError("insufficient data")
            x=add_indicators(df); x.index=pd.DatetimeIndex(x.index).normalize()
            x["NIFTY"]=bench.reindex(x.index).ffill()
            x["RET21"]=x["Close"].pct_change(21)
            x["RET63"]=x["Close"].pct_change(63)
            x["VOL20D"]=x["Close"].pct_change().rolling(20).std()
            x=x.dropna(subset=["EMA20","EMA50","EMA200","RSI14","MACD","MACD_SIGNAL","NIFTY","RET21","RET63","VOL20D"])
            i=0
            while i+horizon<len(x):
                row=x.iloc[i]; score=float(score_technicals(_snap(row))[0])
                future=x.iloc[i+horizon]
                sr=(float(future.Close)/float(row.Close)-1)*100
                nr=(float(future.NIFTY)/float(row.NIFTY)-1)*100
                sample={"ret":sr,"excess":sr-nr,"positive":sr>0,"beat":sr>nr}
                if score>=65: old.append(sample)
                # v0.8 candidate: demand high technical quality + established uptrend
                # + positive medium momentum while avoiding extreme RSI.
                if (score>=85 and row.Close>row.EMA50>row.EMA200 and
                    row.RET21>0 and row.RET63>0 and 50<=row.RSI14<=70):
                    new.append(sample)
                i+=horizon
        except Exception as e: errors.append({"symbol":sym,"error":str(e)})
    def m(vals):
        if not vals:return {"samples":0,"positive_rate":0,"beat_nifty_rate":0,"avg_return":0,"avg_excess":0}
        return {"samples":len(vals),"positive_rate":_pct(sum(v["positive"] for v in vals),len(vals)),
                "beat_nifty_rate":_pct(sum(v["beat"] for v in vals),len(vals)),
                "avg_return":_r(np.mean([v["ret"] for v in vals]),2),
                "avg_excess":_r(np.mean([v["excess"] for v in vals]),2)}
    return {"old":m(old),"candidate":m(new),"errors":errors,
            "candidate_rules":["Technical score ≥85","Close > EMA50 > EMA200",
                               "1-month momentum positive","3-month momentum positive","RSI between 50 and 70"]}
