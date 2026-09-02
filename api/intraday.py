from __future__ import annotations
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

def _indicators(df):
    x=df.copy()
    c=x["Close"]
    x["EMA9"]=c.ewm(span=9,adjust=False).mean()
    x["EMA20"]=c.ewm(span=20,adjust=False).mean()
    d=c.diff()
    gain=d.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    loss=(-d.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    rs=gain/loss.replace(0,np.nan)
    x["RSI"]=100-(100/(1+rs))
    typical=(x["High"]+x["Low"]+x["Close"])/3
    x["VWAP"]=(typical*x["Volume"]).cumsum()/x["Volume"].cumsum().replace(0,np.nan)
    x["VOL20"]=x["Volume"].rolling(20).mean()
    x["VR"]=x["Volume"]/x["VOL20"].replace(0,np.nan)
    x["H20"]=x["High"].rolling(20).max().shift(1)
    x["L20"]=x["Low"].rolling(20).min().shift(1)
    x["ATR"]=(pd.concat([
        x["High"]-x["Low"],
        (x["High"]-x["Close"].shift()).abs(),
        (x["Low"]-x["Close"].shift()).abs()
    ],axis=1).max(axis=1)).rolling(14).mean()
    return x

def analyse_intraday(symbol, capital=50000, risk_pct=1.0):
    df=yf.Ticker(symbol).history(period="5d",interval="5m",auto_adjust=True)
    if df is None or len(df)<30: raise ValueError("Insufficient 5-minute data")
    x=_indicators(df).dropna(subset=["EMA9","EMA20","VWAP","ATR"])
    r=x.iloc[-1]
    p=float(r["Close"]); atr=float(r["ATR"])
    bull=0; bear=0; reasons=[]; warnings=[]
    if p>r["VWAP"]: bull+=2; reasons.append("Price above VWAP")
    else: bear+=2; reasons.append("Price below VWAP")
    if r["EMA9"]>r["EMA20"]: bull+=2; reasons.append("EMA 9 above EMA 20")
    else: bear+=2; reasons.append("EMA 9 below EMA 20")
    if 52<=r["RSI"]<=70: bull+=1; reasons.append("Bullish RSI momentum")
    if 30<=r["RSI"]<=48: bear+=1; reasons.append("Bearish RSI momentum")
    if r.get("VR",0)>=1.25: 
        bull+=1 if bull>=bear else 0; bear+=1 if bear>bull else 0
        reasons.append("Relative volume expansion")
    if pd.notna(r.get("H20")) and p>r["H20"]: bull+=2; reasons.append("20-bar breakout")
    if pd.notna(r.get("L20")) and p<r["L20"]: bear+=2; reasons.append("20-bar breakdown")
    edge=max(bull,bear)
    if edge<4 or abs(bull-bear)<2:
        signal="NO TRADE"; confidence=min(65,45+edge*3)
        entry=p; stop=None; t1=None; t2=None; qty=0
        warnings.append("No sufficiently strong intraday edge")
    else:
        signal="BUY" if bull>bear else "SELL"
        confidence=min(88,55+abs(bull-bear)*5)
        entry=p
        risk_per_share=max(atr*0.8,p*0.003)
        if signal=="BUY":
            stop=entry-risk_per_share; t1=entry+risk_per_share*1.5; t2=entry+risk_per_share*2.2
        else:
            stop=entry+risk_per_share; t1=entry-risk_per_share*1.5; t2=entry-risk_per_share*2.2
        risk_rupees=capital*(risk_pct/100)
        qty=max(0,int(min(capital/entry, risk_rupees/risk_per_share)))
    return {
        "symbol":symbol.replace(".NS",""),"signal":signal,"price":round(p,2),
        "entry":round(entry,2),"stop_loss":round(stop,2) if stop else None,
        "target1":round(t1,2) if t1 else None,"target2":round(t2,2) if t2 else None,
        "confidence":round(confidence,1),"quantity":qty,
        "capital":capital,"risk_pct":risk_pct,"reasons":reasons[:5],"warnings":warnings,
        "signal_time":datetime.now(timezone.utc).isoformat()
    }
