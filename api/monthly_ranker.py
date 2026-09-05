from __future__ import annotations
import numpy as np
import pandas as pd
import yfinance as yf

def _frame(raw,s):
    if isinstance(raw.columns,pd.MultiIndex):
        if s in set(raw.columns.get_level_values(0)): return raw[s].dropna(how="all").copy()
        if s in set(raw.columns.get_level_values(1)): return raw.xs(s,axis=1,level=1).dropna(how="all").copy()
    return raw.copy()

def _pct(s,good=True):
    p=s.rank(pct=True)*100
    return p if good else 100-p

def _metrics(rows):
    p=np.array([r["portfolio_return"] for r in rows]); n=np.array([r["nifty_return"] for r in rows])
    eq=np.cumprod(1+p/100); peak=np.maximum.accumulate(eq); dd=(eq/peak-1)*100
    return {"months":len(rows),"positive_months":round(float((p>0).mean()*100),1),"beat_nifty":round(float((p>n).mean()*100),1),"avg_return":round(float(p.mean()),2),"avg_nifty":round(float(n.mean()),2),"avg_excess":round(float((p-n).mean()),2),"max_drawdown":round(float(abs(dd.min())),2)}

def monthly_ranking_backtest(symbols,period="5y",top_n=3):
    raw=yf.download(symbols+["^NSEI"],period=period,interval="1d",auto_adjust=True,progress=False,threads=True,group_by="ticker")
    fs={s:_frame(raw,s) for s in symbols+["^NSEI"]}; b=fs["^NSEI"]["Close"].copy(); b.index=pd.DatetimeIndex(b.index).tz_localize(None).normalize()
    prep={}
    for s in symbols:
        x=fs[s].copy()
        if len(x)<300: continue
        x.index=pd.DatetimeIndex(x.index).tz_localize(None).normalize(); x["NIFTY"]=b.reindex(x.index).ffill()
        x["R21"]=x.Close.pct_change(21); x["R63"]=x.Close.pct_change(63); x["R126"]=x.Close.pct_change(126)
        x["RS21"]=x.R21-x.NIFTY.pct_change(21); x["RS63"]=x.R63-x.NIFTY.pct_change(63)
        x["E50"]=x.Close.ewm(span=50,adjust=False).mean(); x["E200"]=x.Close.ewm(span=200,adjust=False).mean()
        x["VOL"]=x.Close.pct_change().rolling(20).std(); x["D52"]=x.Close/x.Close.rolling(252).max()-1; x["VR"]=x.Volume/x.Volume.rolling(20).mean(); prep[s]=x
    months=[]
    for dt in list(b.index[260:-22:21]):
        q=[]
        for s,x in prep.items():
            h=x.loc[x.index<=dt]
            if h.empty: continue
            i=x.index.get_loc(h.index[-1])
            if not isinstance(i,(int,np.integer)) or i+21>=len(x): continue
            r=x.iloc[i]; f=x.iloc[i+21]; keys=["R21","R63","R126","RS21","RS63","E50","E200","VOL","D52","VR","NIFTY"]
            if any(pd.isna(r[k]) for k in keys): continue
            q.append(dict(symbol=s.replace('.NS',''),price=float(r.Close),r21=float(r.R21),r63=float(r.R63),r126=float(r.R126),rs21=float(r.RS21),rs63=float(r.RS63),e50=float(r.E50),e200=float(r.E200),vol=float(r.VOL),d52=float(r.D52),vr=float(r.VR),future=float(f.Close),nifty=float(r.NIFTY),fnifty=float(f.NIFTY)))
        if len(q)<top_n: continue
        z=pd.DataFrame(q); trend=np.where((z.price>z.e50)&(z.e50>z.e200),100,np.where(z.price>z.e200,60,20))
        z['score']=.25*_pct(z.rs63)+.15*_pct(z.rs21)+.15*_pct(z.r63)+.10*_pct(z.r126)+.10*trend+.10*_pct(z.vol,False)+.10*_pct(z.d52)+.05*_pct(z.vr)
        p=z.nlargest(top_n,'score').copy(); p['ret']=(p.future/p.price-1)*100; pr=float(p.ret.mean()); nr=float((p.iloc[0].fnifty/p.iloc[0].nifty-1)*100)
        months.append({"date":str(pd.Timestamp(dt).date()),"portfolio_return":round(pr,2),"nifty_return":round(nr,2),"excess":round(pr-nr,2),"picks":[{"symbol":r.symbol,"score":round(float(r.score),1),"return":round(float(r.ret),2)} for _,r in p.iterrows()]})
    if len(months)<12: raise ValueError('Not enough monthly observations')
    cut=int(len(months)*.75); research=months[:cut]; unseen=months[cut:]; a=_metrics(research); u=_metrics(unseen)
    passed=u['months']>=6 and u['avg_excess']>0 and u['beat_nifty']>50
    return {"engine":"v1.0 Monthly Cross-Sectional Ranking","total_months":len(months),"research":a,"unseen":u,"verdict":"PASS" if passed else "REJECT","approved_for_live_candidate":passed,"recent_unseen":unseen[-6:],"weights":{"3M relative strength":25,"1M relative strength":15,"3M momentum":15,"6M momentum":10,"trend":10,"low volatility":10,"near 52-week high":10,"volume strength":5},"warning":"Technical/market-data research only; current-universe history can have survivorship bias. PASS is not a return guarantee."}
