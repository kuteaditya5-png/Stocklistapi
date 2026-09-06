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
    return {"engine":"v1.1 Monthly Cross-Sectional Ranking","total_months":len(months),"research":a,"unseen":u,"verdict":"PASS" if passed else "REJECT","approved_for_live_candidate":passed,"recent_unseen":unseen[-6:],"weights":{"3M relative strength":25,"1M relative strength":15,"3M momentum":15,"6M momentum":10,"trend":10,"low volatility":10,"near 52-week high":10,"volume strength":5},"warning":"Technical/market-data research only; current-universe history can have survivorship bias. PASS is not a return guarantee."}


def rolling_validation(symbols, period="5y", top_n=3, warmup_months=18, block_months=6):
    """v1.2 frozen-rule rolling historical validation.

    Uses the same point-in-time technical ranking as v1.1. No weights or thresholds
    are re-fit inside the evaluation window. The initial months are treated as a
    research/warm-up segment; all later months are reported in sequential blocks.
    """
    base = monthly_ranking_backtest(symbols, period=period, top_n=top_n)
    # Rebuild the monthly observations by joining the two chronological v1.1 segments.
    # monthly_ranking_backtest exposes only the recent unseen rows, so generate a
    # compact chronological series from a private helper-compatible rerun below.
    rows = _monthly_rows(symbols, period=period, top_n=top_n)
    if len(rows) <= warmup_months + 6:
        raise ValueError("Not enough history for rolling validation")
    evaluation = rows[warmup_months:]
    blocks=[]
    for i in range(0, len(evaluation), block_months):
        chunk=evaluation[i:i+block_months]
        if len(chunk)<3: continue
        m=_metrics(chunk)
        blocks.append({"block":len(blocks)+1,"start":chunk[0]["date"],"end":chunk[-1]["date"],**m})
    overall=_metrics(evaluation)
    p=np.array([r["portfolio_return"] for r in evaluation],dtype=float)
    n=np.array([r["nifty_return"] for r in evaluation],dtype=float)
    overall["cumulative_return"]=round(float((np.prod(1+p/100)-1)*100),2)
    overall["nifty_cumulative"]=round(float((np.prod(1+n/100)-1)*100),2)
    overall["cumulative_excess"]=round(overall["cumulative_return"]-overall["nifty_cumulative"],2)
    positive_blocks=sum(1 for b in blocks if b["avg_excess"]>0)
    beat_blocks=sum(1 for b in blocks if b["beat_nifty"]>50)
    stable=(len(blocks)>=3 and positive_blocks/len(blocks)>=0.6 and beat_blocks/len(blocks)>=0.6)
    passed=(overall["months"]>=18 and overall["avg_excess"]>0 and overall["beat_nifty"]>50 and stable)
    return {
        "engine":"v1.2 Rolling Historical Validation",
        "frozen_universe":len(symbols),"top_n":top_n,"warmup_months":warmup_months,
        "evaluation":overall,"blocks":blocks,
        "positive_excess_blocks":positive_blocks,"nifty_beating_blocks":beat_blocks,
        "verdict":"PASS" if passed else "REJECT",
        "warning":"Historical rolling validation, not future accuracy. The current-stock universe can create survivorship bias; transaction costs, taxes and slippage are not included."
    }


def _monthly_rows(symbols,period="5y",top_n=3):
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
        months.append({"date":str(pd.Timestamp(dt).date()),"portfolio_return":round(pr,2),"nifty_return":round(nr,2),"excess":round(pr-nr,2)})
    return months



def regime_validation(symbols, period="5y", top_n=3, warmup_months=18):
    """v1.3 point-in-time market-regime validation of the frozen v1.2 model."""
    rows = _monthly_rows_with_regime(symbols, period=period, top_n=top_n)
    if len(rows) <= warmup_months + 6:
        raise ValueError("Not enough history for regime validation")
    evaluation = rows[warmup_months:]

    def pack(items):
        if not items:
            return {"months":0,"positive_months":0.0,"beat_nifty":0.0,"avg_return":0.0,"avg_nifty":0.0,"avg_excess":0.0,"max_drawdown":0.0}
        return _metrics(items)

    trend_order = ["BULLISH", "SIDEWAYS", "BEARISH"]
    vol_order = ["NORMAL VOL", "HIGH VOL"]
    trend = [{"regime":k, **pack([r for r in evaluation if r["trend_regime"]==k])} for k in trend_order]
    volatility = [{"regime":k, **pack([r for r in evaluation if r["vol_regime"]==k])} for k in vol_order]
    combos=[]
    for t in trend_order:
        for v in vol_order:
            x=[r for r in evaluation if r["trend_regime"]==t and r["vol_regime"]==v]
            if x: combos.append({"regime":f"{t} · {v}", **pack(x)})

    overall=pack(evaluation)
    adequate=[x for x in trend if x["months"]>=3]
    weak=[x["regime"] for x in adequate if x["avg_excess"]<=0 or x["beat_nifty"]<=50]
    passed=(overall["avg_excess"]>0 and overall["beat_nifty"]>50 and len(adequate)>=2 and len(weak)==0)
    return {
        "engine":"v1.3 Market Regime Validation",
        "frozen_model":"v1.2 · 20-stock universe · Top 3",
        "evaluation_months":len(evaluation),
        "overall":overall,
        "trend_regimes":trend,
        "volatility_regimes":volatility,
        "combined_regimes":combos,
        "weak_regimes":weak,
        "verdict":"PASS" if passed else "REVIEW",
        "method":"Regime is classified using only information available on each ranking date: NIFTY 3-month trend vs its 200-day EMA; high volatility uses NIFTY 20-day realized volatility above its trailing 252-day 70th percentile.",
        "warning":"Regime analysis is diagnostic research, not a guarantee. Small regime samples can be noisy; current-universe survivorship bias, costs, taxes and slippage remain excluded."
    }


def _monthly_rows_with_regime(symbols,period="5y",top_n=3):
    raw=yf.download(symbols+["^NSEI"],period=period,interval="1d",auto_adjust=True,progress=False,threads=True,group_by="ticker")
    fs={s:_frame(raw,s) for s in symbols+["^NSEI"]}; b=fs["^NSEI"]["Close"].copy(); b.index=pd.DatetimeIndex(b.index).tz_localize(None).normalize()
    bm=pd.DataFrame({"Close":b})
    bm["R63"]=bm.Close.pct_change(63); bm["E200"]=bm.Close.ewm(span=200,adjust=False).mean()
    bm["VOL20"]=bm.Close.pct_change().rolling(20).std(); bm["VOL70"]=bm.VOL20.rolling(252,min_periods=126).quantile(.70)
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
        if dt not in bm.index: continue
        br=bm.loc[dt]
        if pd.isna(br.R63) or pd.isna(br.E200) or pd.isna(br.VOL20): continue
        if br.Close>br.E200 and br.R63>0.03: trend_regime="BULLISH"
        elif br.Close<br.E200 and br.R63<-0.03: trend_regime="BEARISH"
        else: trend_regime="SIDEWAYS"
        vol_regime="HIGH VOL" if pd.notna(br.VOL70) and br.VOL20>br.VOL70 else "NORMAL VOL"
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
        months.append({"date":str(pd.Timestamp(dt).date()),"portfolio_return":round(pr,2),"nifty_return":round(nr,2),"excess":round(pr-nr,2),"trend_regime":trend_regime,"vol_regime":vol_regime})
    return months
