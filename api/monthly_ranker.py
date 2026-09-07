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


def regime_aware_validation(symbols, period="5y", top_n=3, warmup_months=18, block_months=6):
    """v1.4 candidate vs the frozen v1.2 score on identical point-in-time months.

    Regime classification uses only NIFTY information available on the ranking date.
    The v1.2 baseline is untouched. The candidate changes ranking weights only; it
    remains fully invested in Top-3 stocks so comparisons are like-for-like.
    """
    raw=yf.download(symbols+["^NSEI"],period=period,interval="1d",auto_adjust=True,progress=False,threads=True,group_by="ticker")
    fs={s:_frame(raw,s) for s in symbols+["^NSEI"]}; b=fs["^NSEI"]["Close"].copy(); b.index=pd.DatetimeIndex(b.index).tz_localize(None).normalize()
    bm=pd.DataFrame({"Close":b}); bm["R63"]=bm.Close.pct_change(63); bm["E200"]=bm.Close.ewm(span=200,adjust=False).mean(); bm["VOL20"]=bm.Close.pct_change().rolling(20).std(); bm["VOL70"]=bm.VOL20.rolling(252,min_periods=126).quantile(.70)
    prep={}
    for s in symbols:
        x=fs[s].copy()
        if len(x)<300: continue
        x.index=pd.DatetimeIndex(x.index).tz_localize(None).normalize(); x["NIFTY"]=b.reindex(x.index).ffill()
        x["R21"]=x.Close.pct_change(21); x["R63"]=x.Close.pct_change(63); x["R126"]=x.Close.pct_change(126); x["RS21"]=x.R21-x.NIFTY.pct_change(21); x["RS63"]=x.R63-x.NIFTY.pct_change(63)
        x["E50"]=x.Close.ewm(span=50,adjust=False).mean(); x["E200"]=x.Close.ewm(span=200,adjust=False).mean(); x["VOL"]=x.Close.pct_change().rolling(20).std(); x["D52"]=x.Close/x.Close.rolling(252).max()-1; x["VR"]=x.Volume/x.Volume.rolling(20).mean(); prep[s]=x
    base_rows=[]; cand_rows=[]
    for dt in list(b.index[260:-22:21]):
        if dt not in bm.index: continue
        br=bm.loc[dt]
        if pd.isna(br.R63) or pd.isna(br.E200) or pd.isna(br.VOL20): continue
        regime="BULLISH" if br.Close>br.E200 and br.R63>0.03 else ("BEARISH" if br.Close<br.E200 and br.R63<-0.03 else "SIDEWAYS")
        highvol=bool(pd.notna(br.VOL70) and br.VOL20>br.VOL70)
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
        prs63=_pct(z.rs63); prs21=_pct(z.rs21); pr63=_pct(z.r63); pr126=_pct(z.r126); pvol=_pct(z.vol,False); pd52=_pct(z.d52); pvr=_pct(z.vr)
        z['base_score']=.25*prs63+.15*prs21+.15*pr63+.10*pr126+.10*trend+.10*pvol+.10*pd52+.05*pvr
        # Predefined v1.4 candidate: attack the diagnosed SIDEWAYS weakness with
        # more relative strength/trend quality; in HIGH VOL emphasize low volatility.
        if regime=="SIDEWAYS":
            z['cand_score']=.32*prs63+.18*prs21+.10*pr63+.05*pr126+.15*trend+.08*pvol+.08*pd52+.04*pvr
        else:
            z['cand_score']=z['base_score']
        if highvol:
            z['cand_score']=.85*z['cand_score']+.15*pvol
        pb=z.nlargest(top_n,'base_score').copy(); pc=z.nlargest(top_n,'cand_score').copy()
        pb['ret']=(pb.future/pb.price-1)*100; pc['ret']=(pc.future/pc.price-1)*100; nr=float((pb.iloc[0].fnifty/pb.iloc[0].nifty-1)*100)
        common={"date":str(pd.Timestamp(dt).date()),"nifty_return":round(nr,2),"trend_regime":regime,"vol_regime":"HIGH VOL" if highvol else "NORMAL VOL"}
        brw={**common,"portfolio_return":round(float(pb.ret.mean()),2)}; brw["excess"]=round(brw["portfolio_return"]-brw["nifty_return"],2); base_rows.append(brw)
        crw={**common,"portfolio_return":round(float(pc.ret.mean()),2)}; crw["excess"]=round(crw["portfolio_return"]-crw["nifty_return"],2); cand_rows.append(crw)
    if len(base_rows)<=warmup_months+6: raise ValueError("Not enough history for v1.4 validation")
    base=base_rows[warmup_months:]; cand=cand_rows[warmup_months:]; mb=_metrics(base); mc=_metrics(cand)
    trend=[]
    for k in ["BULLISH","SIDEWAYS","BEARISH"]:
        x=[r for r in cand if r["trend_regime"]==k]
        if x: trend.append({"regime":k,**_metrics(x)})
    blocks=[]
    for i in range(0,len(cand),block_months):
        cb=cand[i:i+block_months]; bb=base[i:i+block_months]
        if len(cb)<3: continue
        cm=_metrics(cb); bmtr=_metrics(bb); blocks.append({"block":len(blocks)+1,"candidate_excess":cm["avg_excess"],"baseline_excess":bmtr["avg_excess"]})
    improved_blocks=sum(1 for x in blocks if x["candidate_excess"]>=x["baseline_excess"])
    # Conservative promotion: candidate must improve excess and NIFTY hit rate,
    # not worsen drawdown by >2pp, and improve/not lose in >=60% rolling blocks.
    passed=(mc["avg_excess"]>mb["avg_excess"] and mc["beat_nifty"]>mb["beat_nifty"] and mc["max_drawdown"]<=mb["max_drawdown"]+2 and len(blocks)>=3 and improved_blocks/len(blocks)>=.6)
    return {"engine":"v1.4 Regime-Aware Ranking Candidate","evaluation_months":len(cand),"baseline":mb,"candidate":mc,"candidate_regimes":trend,"rolling_blocks":blocks,"improved_blocks":improved_blocks,"verdict":"PASS" if passed else "REJECT","rules":["Bullish/Bearish: preserve frozen v1.2 ranking weights","Sideways: increase relative-strength and trend-quality weight; reduce raw momentum weight","High volatility: blend an additional 15% low-volatility preference","Always hold Top 3 so the comparison with v1.2 stays like-for-like"],"pass_rule":"Candidate must improve average excess AND NIFTY-beating rate, keep drawdown within +2 percentage points of baseline, and equal/beat baseline excess in at least 60% of rolling blocks.","warning":"Experimental historical candidate. The v1.2 model remains the frozen baseline unless v1.4 passes. Current-universe survivorship bias, costs, taxes and slippage are not included."}



def sideways_optimizer_validation(symbols, period="5y", top_n=3, warmup_months=18):
    """v1.5: compare predefined SIDEWAYS-only ranking candidates.
    Bullish and bearish months keep the frozen v1.2 score unchanged.
    """
    raw=yf.download(symbols+["^NSEI"],period=period,interval="1d",auto_adjust=True,progress=False,threads=True,group_by="ticker")
    fs={s:_frame(raw,s) for s in symbols+["^NSEI"]}; b=fs["^NSEI"]["Close"].copy(); b.index=pd.DatetimeIndex(b.index).tz_localize(None).normalize()
    bm=pd.DataFrame({"Close":b}); bm["R63"]=bm.Close.pct_change(63); bm["E200"]=bm.Close.ewm(span=200,adjust=False).mean()
    prep={}
    for s in symbols:
        x=fs[s].copy()
        if len(x)<300: continue
        x.index=pd.DatetimeIndex(x.index).tz_localize(None).normalize(); x["NIFTY"]=b.reindex(x.index).ffill()
        x["R21"]=x.Close.pct_change(21); x["R63"]=x.Close.pct_change(63); x["R126"]=x.Close.pct_change(126)
        x["RS21"]=x.R21-x.NIFTY.pct_change(21); x["RS63"]=x.R63-x.NIFTY.pct_change(63)
        x["E50"]=x.Close.ewm(span=50,adjust=False).mean(); x["E200"]=x.Close.ewm(span=200,adjust=False).mean()
        x["VOL"]=x.Close.pct_change().rolling(20).std(); x["D52"]=x.Close/x.Close.rolling(252).max()-1; x["VR"]=x.Volume/x.Volume.rolling(20).mean(); prep[s]=x

    rows={"BASE":[],"RS":[],"QUALITY":[],"BALANCED":[]}
    for dt in list(b.index[260:-22:21]):
        if dt not in bm.index: continue
        br=bm.loc[dt]
        if pd.isna(br.R63) or pd.isna(br.E200): continue
        regime="BULLISH" if br.Close>br.E200 and br.R63>0.03 else ("BEARISH" if br.Close<br.E200 and br.R63<-0.03 else "SIDEWAYS")
        q=[]
        for s,x in prep.items():
            h=x.loc[x.index<=dt]
            if h.empty: continue
            i=x.index.get_loc(h.index[-1])
            if not isinstance(i,(int,np.integer)) or i+21>=len(x): continue
            r=x.iloc[i]; f=x.iloc[i+21]; keys=["R21","R63","R126","RS21","RS63","E50","E200","VOL","D52","VR","NIFTY"]
            if any(pd.isna(r[k]) for k in keys): continue
            q.append(dict(symbol=s.replace(".NS",""),price=float(r.Close),r21=float(r.R21),r63=float(r.R63),r126=float(r.R126),
                rs21=float(r.RS21),rs63=float(r.RS63),e50=float(r.E50),e200=float(r.E200),vol=float(r.VOL),d52=float(r.D52),
                vr=float(r.VR),future=float(f.Close),nifty=float(r.NIFTY),fnifty=float(f.NIFTY)))
        if len(q)<top_n: continue
        z=pd.DataFrame(q); trend=np.where((z.price>z.e50)&(z.e50>z.e200),100,np.where(z.price>z.e200,60,20))
        rs63=_pct(z.rs63); rs21=_pct(z.rs21); r63=_pct(z.r63); r126=_pct(z.r126); lowvol=_pct(z.vol,False); d52=_pct(z.d52); vr=_pct(z.vr)
        base=.25*rs63+.15*rs21+.15*r63+.10*r126+.10*trend+.10*lowvol+.10*d52+.05*vr
        scores={"BASE":base}
        if regime=="SIDEWAYS":
            scores["RS"]=.40*rs63+.25*rs21+.08*r63+.04*r126+.10*trend+.05*lowvol+.05*d52+.03*vr
            scores["QUALITY"]=.22*rs63+.12*rs21+.08*r63+.05*r126+.23*trend+.20*lowvol+.07*d52+.03*vr
            scores["BALANCED"]=.32*rs63+.18*rs21+.08*r63+.05*r126+.17*trend+.12*lowvol+.05*d52+.03*vr
        else:
            scores.update({"RS":base,"QUALITY":base,"BALANCED":base})
        nr=float((z.iloc[0].fnifty/z.iloc[0].nifty-1)*100)
        for name,score in scores.items():
            p=z.assign(_score=score).nlargest(top_n,"_score").copy()
            pr=float(((p.future/p.price-1)*100).mean())
            rows[name].append({"date":str(pd.Timestamp(dt).date()),"portfolio_return":round(pr,2),"nifty_return":round(nr,2),
                               "excess":round(pr-nr,2),"trend_regime":regime})

    evals={k:v[warmup_months:] for k,v in rows.items()}
    if len(evals["BASE"])<10: raise ValueError("Not enough history for v1.5 validation")
    base=_metrics(evals["BASE"])
    candidates=[]
    for name,label in [("RS","Relative Strength"),("QUALITY","Trend + Low Vol"),("BALANCED","Balanced")]:
        allm=_metrics(evals[name])
        sw=_metrics([r for r in evals[name] if r["trend_regime"]=="SIDEWAYS"])
        candidates.append({"id":name,"name":label,"overall":allm,"sideways":sw})
    # This is a research comparison, not automatic model selection.
    winner=max(candidates,key=lambda x:(x["sideways"]["avg_excess"],x["sideways"]["beat_nifty"],-x["overall"]["max_drawdown"]))
    passed=(winner["sideways"]["avg_excess"]>0 and winner["sideways"]["beat_nifty"]>50
            and winner["overall"]["avg_excess"]>=base["avg_excess"]
            and winner["overall"]["beat_nifty"]>=base["beat_nifty"]
            and winner["overall"]["max_drawdown"]<=base["max_drawdown"]+2)
    return {"engine":"v1.5 Sideways-Market Optimizer","evaluation_months":len(evals["BASE"]),"baseline":base,
            "candidates":candidates,"best_candidate":winner["name"],"verdict":"PASS" if passed else "REJECT",
            "rules":["Bullish/Bearish months use frozen v1.2 ranking unchanged",
                     "Relative Strength: strongly favors RS63/RS21 in sideways markets",
                     "Trend + Low Vol: favors EMA trend quality and lower realized volatility",
                     "Balanced: combines relative strength, trend quality and low volatility"],
            "pass_rule":"Best predefined candidate must make SIDEWAYS excess positive and beat NIFTY >50%, while not reducing overall excess/beat rate or worsening drawdown by more than 2pp.",
            "warning":"Research test only. Candidate comparison is performed on the same historical evaluation set, so a PASS still requires a later untouched/rolling confirmation before promotion."}


def sideways_holdout_confirmation(symbols, period="10y", top_n=3):
    """v1.6: freeze v1.5 Trend + Low Vol and test only dates outside v1.5's 5-year selection window.
    This is a backward pre-selection holdout, not future data. No candidate tuning occurs here.
    """
    raw=yf.download(symbols+["^NSEI"],period=period,interval="1d",auto_adjust=True,progress=False,threads=True,group_by="ticker")
    fs={s:_frame(raw,s) for s in symbols+["^NSEI"]}; b=fs["^NSEI"]["Close"].copy(); b.index=pd.DatetimeIndex(b.index).tz_localize(None).normalize()
    if len(b)<1500: raise ValueError("Not enough long history for v1.6 holdout confirmation")
    # v1.5 used period='5y'. Exclude the most recent 5 calendar years entirely.
    cutoff=(b.index.max()-pd.DateOffset(years=5)).normalize()
    bm=pd.DataFrame({"Close":b}); bm["R63"]=bm.Close.pct_change(63); bm["E200"]=bm.Close.ewm(span=200,adjust=False).mean()
    prep={}
    for s in symbols:
        x=fs[s].copy()
        if len(x)<500: continue
        x.index=pd.DatetimeIndex(x.index).tz_localize(None).normalize(); x["NIFTY"]=b.reindex(x.index).ffill()
        x["R21"]=x.Close.pct_change(21); x["R63"]=x.Close.pct_change(63); x["R126"]=x.Close.pct_change(126)
        x["RS21"]=x.R21-x.NIFTY.pct_change(21); x["RS63"]=x.R63-x.NIFTY.pct_change(63)
        x["E50"]=x.Close.ewm(span=50,adjust=False).mean(); x["E200"]=x.Close.ewm(span=200,adjust=False).mean()
        x["VOL"]=x.Close.pct_change().rolling(20).std(); x["D52"]=x.Close/x.Close.rolling(252).max()-1; x["VR"]=x.Volume/x.Volume.rolling(20).mean(); prep[s]=x
    base_rows=[]; cand_rows=[]
    dates=[dt for dt in b.index[260:-22:21] if dt < cutoff]
    for dt in dates:
        if dt not in bm.index: continue
        br=bm.loc[dt]
        if pd.isna(br.R63) or pd.isna(br.E200): continue
        regime="BULLISH" if br.Close>br.E200 and br.R63>0.03 else ("BEARISH" if br.Close<br.E200 and br.R63<-0.03 else "SIDEWAYS")
        q=[]
        for s,x in prep.items():
            h=x.loc[x.index<=dt]
            if h.empty: continue
            i=x.index.get_loc(h.index[-1])
            if not isinstance(i,(int,np.integer)) or i+21>=len(x): continue
            r=x.iloc[i]; f=x.iloc[i+21]; keys=["R21","R63","R126","RS21","RS63","E50","E200","VOL","D52","VR","NIFTY"]
            if any(pd.isna(r[k]) for k in keys): continue
            q.append(dict(symbol=s.replace(".NS",""),price=float(r.Close),r21=float(r.R21),r63=float(r.R63),r126=float(r.R126),rs21=float(r.RS21),rs63=float(r.RS63),e50=float(r.E50),e200=float(r.E200),vol=float(r.VOL),d52=float(r.D52),vr=float(r.VR),future=float(f.Close),nifty=float(r.NIFTY),fnifty=float(f.NIFTY)))
        if len(q)<top_n: continue
        z=pd.DataFrame(q); trend=np.where((z.price>z.e50)&(z.e50>z.e200),100,np.where(z.price>z.e200,60,20))
        rs63=_pct(z.rs63); rs21=_pct(z.rs21); r63=_pct(z.r63); r126=_pct(z.r126); lowvol=_pct(z.vol,False); d52=_pct(z.d52); vr=_pct(z.vr)
        base=.25*rs63+.15*rs21+.15*r63+.10*r126+.10*trend+.10*lowvol+.10*d52+.05*vr
        # Frozen v1.5 winner. Do not change these weights in v1.6.
        quality=.22*rs63+.12*rs21+.08*r63+.05*r126+.23*trend+.20*lowvol+.07*d52+.03*vr if regime=="SIDEWAYS" else base
        nr=float((z.iloc[0].fnifty/z.iloc[0].nifty-1)*100)
        for score,target in [(base,base_rows),(quality,cand_rows)]:
            p=z.assign(_score=score).nlargest(top_n,"_score").copy(); pr=float(((p.future/p.price-1)*100).mean())
            target.append({"date":str(pd.Timestamp(dt).date()),"portfolio_return":round(pr,2),"nifty_return":round(nr,2),"excess":round(pr-nr,2),"trend_regime":regime})
    if len(cand_rows)<12: raise ValueError("Not enough pre-selection holdout months for v1.6")
    mb=_metrics(base_rows); mc=_metrics(cand_rows)
    bsw=_metrics([r for r in base_rows if r["trend_regime"]=="SIDEWAYS"]); csw=_metrics([r for r in cand_rows if r["trend_regime"]=="SIDEWAYS"])
    passed=(csw["months"]>=6 and csw["avg_excess"]>0 and csw["beat_nifty"]>50 and mc["avg_excess"]>=mb["avg_excess"] and mc["max_drawdown"]<=mb["max_drawdown"]+2)
    return {"engine":"v1.6 Frozen Winner Holdout Confirmation","holdout_start":cand_rows[0]["date"],"holdout_end":cand_rows[-1]["date"],"selection_window_excluded_from":str(cutoff.date()),"baseline":mb,"candidate":mc,"baseline_sideways":bsw,"candidate_sideways":csw,"verdict":"PASS" if passed else "REJECT","frozen_candidate":"Trend + Low Vol","pass_rule":"At least 6 SIDEWAYS holdout months, positive SIDEWAYS excess, >50% SIDEWAYS NIFTY-beat rate, no reduction in overall average excess versus frozen v1.2, and drawdown no more than 2pp worse.","warning":"v1.6 uses older pre-selection history excluded from v1.5's 5-year optimization window. This is a genuine out-of-selection historical holdout, but it is backward-looking—not future live validation—and current-universe survivorship bias can remain."}


def stress_robustness_validation(symbols, period="10y"):
    """v1.7: stress the frozen v1.5 Trend + Low Vol rule without retuning it.
    Tests Top-N sensitivity, small predefined weight perturbations, volatility/trend regimes,
    and early-vs-late stability over the available long history.
    """
    raw=yf.download(symbols+["^NSEI"],period=period,interval="1d",auto_adjust=True,progress=False,threads=True,group_by="ticker")
    fs={s:_frame(raw,s) for s in symbols+["^NSEI"]}; b=fs["^NSEI"]["Close"].copy()
    b.index=pd.DatetimeIndex(b.index).tz_localize(None).normalize()
    if len(b)<1500: raise ValueError("Not enough long history for v1.7 robustness validation")
    bm=pd.DataFrame({"Close":b}); bm["R63"]=bm.Close.pct_change(63); bm["E200"]=bm.Close.ewm(span=200,adjust=False).mean()
    bm["RET"]=bm.Close.pct_change(); bm["VOL20"]=bm.RET.rolling(20).std()
    bm["VOL_Q70"]=bm.VOL20.rolling(252,min_periods=126).quantile(.70)
    prep={}
    for s in symbols:
        x=fs[s].copy()
        if len(x)<500: continue
        x.index=pd.DatetimeIndex(x.index).tz_localize(None).normalize(); x["NIFTY"]=b.reindex(x.index).ffill()
        x["R21"]=x.Close.pct_change(21); x["R63"]=x.Close.pct_change(63); x["R126"]=x.Close.pct_change(126)
        x["RS21"]=x.R21-x.NIFTY.pct_change(21); x["RS63"]=x.R63-x.NIFTY.pct_change(63)
        x["E50"]=x.Close.ewm(span=50,adjust=False).mean(); x["E200"]=x.Close.ewm(span=200,adjust=False).mean()
        x["VOL"]=x.Close.pct_change().rolling(20).std(); x["D52"]=x.Close/x.Close.rolling(252).max()-1
        x["VR"]=x.Volume/x.Volume.rolling(20).mean(); prep[s]=x
    # Frozen winner plus small, PREDEFINED perturbations. These are diagnostics, not new candidates.
    weight_sets={
      "Frozen":(.22,.12,.08,.05,.23,.20,.07,.03),
      "Trend -10%":(.23,.13,.08,.05,.207,.22,.073,.027),
      "Trend +10%":(.21,.11,.08,.05,.253,.19,.067,.03),
      "LowVol -10%":(.23,.12,.08,.05,.24,.18,.07,.03),
      "LowVol +10%":(.21,.12,.08,.05,.22,.22,.07,.03),
    }
    rows={(name,n):[] for name in weight_sets for n in (2,3,4,5)}
    dates=b.index[260:-22:21]
    for dt in dates:
        if dt not in bm.index: continue
        br=bm.loc[dt]
        if pd.isna(br.R63) or pd.isna(br.E200): continue
        regime="BULLISH" if br.Close>br.E200 and br.R63>0.03 else ("BEARISH" if br.Close<br.E200 and br.R63<-0.03 else "SIDEWAYS")
        highvol=bool(pd.notna(br.VOL_Q70) and br.VOL20>br.VOL_Q70)
        q=[]
        for s,x in prep.items():
            h=x.loc[x.index<=dt]
            if h.empty: continue
            i=x.index.get_loc(h.index[-1])
            if not isinstance(i,(int,np.integer)) or i+21>=len(x): continue
            r=x.iloc[i]; f=x.iloc[i+21]
            keys=["R21","R63","R126","RS21","RS63","E50","E200","VOL","D52","VR","NIFTY"]
            if any(pd.isna(r[k]) for k in keys): continue
            q.append(dict(symbol=s.replace(".NS",""),price=float(r.Close),r21=float(r.R21),r63=float(r.R63),
              r126=float(r.R126),rs21=float(r.RS21),rs63=float(r.RS63),e50=float(r.E50),e200=float(r.E200),
              vol=float(r.VOL),d52=float(r.D52),vr=float(r.VR),future=float(f.Close),nifty=float(r.NIFTY),fnifty=float(f.NIFTY)))
        if len(q)<5: continue
        z=pd.DataFrame(q); trend=np.where((z.price>z.e50)&(z.e50>z.e200),100,np.where(z.price>z.e200,60,20))
        feats=[_pct(z.rs63),_pct(z.rs21),_pct(z.r63),_pct(z.r126),trend,_pct(z.vol,False),_pct(z.d52),_pct(z.vr)]
        base=.25*feats[0]+.15*feats[1]+.15*feats[2]+.10*feats[3]+.10*feats[4]+.10*feats[5]+.10*feats[6]+.05*feats[7]
        nr=float((z.iloc[0].fnifty/z.iloc[0].nifty-1)*100)
        for name,w in weight_sets.items():
            score=sum(float(wi)*fi for wi,fi in zip(w,feats)) if regime=="SIDEWAYS" else base
            for n in (2,3,4,5):
                pick=z.assign(_score=score).nlargest(n,"_score")
                pr=float(((pick.future/pick.price-1)*100).mean())
                rows[(name,n)].append({"date":str(pd.Timestamp(dt).date()),"portfolio_return":round(pr,2),
                    "nifty_return":round(nr,2),"excess":round(pr-nr,2),"trend_regime":regime,
                    "vol_regime":"HIGH" if highvol else "NORMAL"})
    frozen=rows[("Frozen",3)]
    if len(frozen)<36: raise ValueError("Not enough monthly observations for v1.7")
    overall=_metrics(frozen)
    topn={str(n):_metrics(rows[("Frozen",n)]) for n in (2,3,4,5)}
    perturb=[]
    for name in weight_sets:
        m=_metrics(rows[(name,3)])
        sw=_metrics([r for r in rows[(name,3)] if r["trend_regime"]=="SIDEWAYS"])
        perturb.append({"name":name,"overall":m,"sideways":sw})
    regimes={}
    for rg in ("BULLISH","SIDEWAYS","BEARISH"):
        regimes[rg]=_metrics([r for r in frozen if r["trend_regime"]==rg])
    vol={"NORMAL":_metrics([r for r in frozen if r["vol_regime"]=="NORMAL"]),
         "HIGH":_metrics([r for r in frozen if r["vol_regime"]=="HIGH"])}
    mid=len(frozen)//2
    periods={"EARLY":_metrics(frozen[:mid]),"LATE":_metrics(frozen[mid:])}
    # Robustness gate: frozen Top3 positive excess; Top2-5 average excess not negative;
    # all perturbations retain positive overall excess; sideways frozen remains positive and >50% beat;
    # both chronological halves retain positive excess.
    passed=(overall["avg_excess"]>0
        and all(v["avg_excess"]>=0 for v in topn.values())
        and all(x["overall"]["avg_excess"]>0 for x in perturb)
        and perturb[0]["sideways"]["avg_excess"]>0 and perturb[0]["sideways"]["beat_nifty"]>50
        and periods["EARLY"]["avg_excess"]>0 and periods["LATE"]["avg_excess"]>0)
    return {"engine":"v1.7 Stress & Robustness Validation","frozen_candidate":"Trend + Low Vol",
      "months":len(frozen),"overall":overall,"top_n_sensitivity":topn,"weight_perturbations":perturb,
      "trend_regimes":regimes,"volatility_regimes":vol,"chronological_stability":periods,
      "verdict":"PASS" if passed else "REVIEW",
      "pass_rule":"Frozen Top-3 must retain positive overall excess; Top-2/3/4/5 must not have negative average excess; all small predefined weight perturbations must retain positive overall excess; frozen SIDEWAYS performance must stay positive and beat NIFTY >50%; and both chronological halves must retain positive excess.",
      "warning":"Stress test only. The v1.5 winner remains frozen; perturbations are sensitivity diagnostics, not retuning. Historical tests remain subject to survivorship/data-quality bias and are not a guarantee of future returns."}


def execution_cost_validation(symbols, period="10y"):
    """v1.8: execution/cost validation of the frozen Trend + Low Vol Top-3 model."""
    raw=yf.download(symbols+["^NSEI"],period=period,interval="1d",auto_adjust=True,progress=False,threads=True,group_by="ticker")
    fs={s:_frame(raw,s) for s in symbols+["^NSEI"]}; b=fs["^NSEI"]["Close"].copy()
    b.index=pd.DatetimeIndex(b.index).tz_localize(None).normalize()
    if len(b)<1500: raise ValueError("Not enough long history for v1.8 execution validation")
    bm=pd.DataFrame({"Close":b}); bm["R63"]=bm.Close.pct_change(63); bm["E200"]=bm.Close.ewm(span=200,adjust=False).mean()
    prep={}
    for s in symbols:
        x=fs[s].copy()
        if len(x)<500: continue
        x.index=pd.DatetimeIndex(x.index).tz_localize(None).normalize(); x["NIFTY"]=b.reindex(x.index).ffill()
        x["R21"]=x.Close.pct_change(21); x["R63"]=x.Close.pct_change(63); x["R126"]=x.Close.pct_change(126)
        x["RS21"]=x.R21-x.NIFTY.pct_change(21); x["RS63"]=x.R63-x.NIFTY.pct_change(63)
        x["E50"]=x.Close.ewm(span=50,adjust=False).mean(); x["E200"]=x.Close.ewm(span=200,adjust=False).mean()
        x["VOL"]=x.Close.pct_change().rolling(20).std(); x["D52"]=x.Close/x.Close.rolling(252).max()-1
        x["VR"]=x.Volume/x.Volume.rolling(20).mean(); prep[s]=x

    frozen_w=(.22,.12,.08,.05,.23,.20,.07,.03)
    rows=[]
    dates=b.index[260:-22:21]
    for dt in dates:
        if dt not in bm.index: continue
        br=bm.loc[dt]
        if pd.isna(br.R63) or pd.isna(br.E200): continue
        regime="BULLISH" if br.Close>br.E200 and br.R63>0.03 else ("BEARISH" if br.Close<br.E200 and br.R63<-0.03 else "SIDEWAYS")
        q=[]
        for s,x in prep.items():
            h=x.loc[x.index<=dt]
            if h.empty: continue
            i=x.index.get_loc(h.index[-1])
            if not isinstance(i,(int,np.integer)) or i+21>=len(x): continue
            r=x.iloc[i]; f=x.iloc[i+21]
            keys=["R21","R63","R126","RS21","RS63","E50","E200","VOL","D52","VR","NIFTY"]
            if any(pd.isna(r[k]) for k in keys): continue
            q.append(dict(symbol=s.replace(".NS",""),price=float(r.Close),r21=float(r.R21),r63=float(r.R63),
              r126=float(r.R126),rs21=float(r.RS21),rs63=float(r.RS63),e50=float(r.E50),e200=float(r.E200),
              vol=float(r.VOL),d52=float(r.D52),vr=float(r.VR),future=float(f.Close),nifty=float(r.NIFTY),fnifty=float(f.NIFTY)))
        if len(q)<5: continue
        z=pd.DataFrame(q); trend=np.where((z.price>z.e50)&(z.e50>z.e200),100,np.where(z.price>z.e200,60,20))
        feats=[_pct(z.rs63),_pct(z.rs21),_pct(z.r63),_pct(z.r126),trend,_pct(z.vol,False),_pct(z.d52),_pct(z.vr)]
        base=.25*feats[0]+.15*feats[1]+.15*feats[2]+.10*feats[3]+.10*feats[4]+.10*feats[5]+.10*feats[6]+.05*feats[7]
        score=sum(float(wi)*fi for wi,fi in zip(frozen_w,feats)) if regime=="SIDEWAYS" else base
        pick=z.assign(_score=score).nlargest(3,"_score")
        pr=float(((pick.future/pick.price-1)*100).mean())
        nr=float((z.iloc[0].fnifty/z.iloc[0].nifty-1)*100)
        rows.append({"date":str(pd.Timestamp(dt).date()),"portfolio_return":pr,"nifty_return":nr,
                     "excess":pr-nr,"picks":pick.symbol.tolist(),"trend_regime":regime})
    if len(rows)<36: raise ValueError("Not enough monthly observations for v1.8")

    turnovers=[]; prev=None
    for r in rows:
        cur=set(r["picks"])
        turnovers.append(1.0 if prev is None else 1.0-len(cur & prev)/3.0)
        prev=cur

    def net_rows(total_bps, timing_bps=0):
        out=[]
        for r,turn in zip(rows,turnovers):
            # total_bps is round-trip friction on the fraction of portfolio replaced.
            # timing_bps is an additional adverse implementation assumption.
            cost_pct=((total_bps*turn)+timing_bps)/100.0
            x=dict(r); x["portfolio_return"]=r["portfolio_return"]-cost_pct
            x["excess"]=x["portfolio_return"]-r["nifty_return"]; out.append(x)
        return out

    gross=_metrics(rows)
    scenarios=[]
    for name,bps in [("Low friction",10),("Base realistic",25),("High friction",50),("Stress",100)]:
        m=_metrics(net_rows(bps))
        scenarios.append({"name":name,"round_trip_bps":bps,**m})
    timing=[]
    for name,extra in [("Signal close",0),("Next-session execution",15),("Adverse gap stress",35)]:
        m=_metrics(net_rows(25,extra))
        timing.append({"name":name,"base_cost_bps":25,"extra_timing_bps":extra,**m})

    avg_turn=round(float(np.mean(turnovers))*100,1)
    base=scenarios[1]; stress=scenarios[-1]
    passed=(base["avg_excess"]>0 and base["beat_nifty"]>50 and stress["avg_excess"]>0
            and timing[-1]["avg_excess"]>0)
    return {"engine":"v1.8 Execution & Cost Validation","frozen_candidate":"Trend + Low Vol",
      "months":len(rows),"gross":gross,"average_monthly_turnover_pct":avg_turn,
      "cost_scenarios":scenarios,"timing_sensitivity":timing,
      "verdict":"PASS" if passed else "REVIEW",
      "pass_rule":"Frozen model must keep positive average excess and >50% NIFTY-beat rate at 25 bps base friction, remain positive at 100 bps round-trip stress, and retain positive excess under the adverse timing stress. No ranking weights are retuned.",
      "warning":"Execution-cost research only. Cost assumptions are simplified and actual brokerage, taxes/fees, spread, slippage and market impact vary. The frozen Trend + Low Vol ranking is unchanged."}
