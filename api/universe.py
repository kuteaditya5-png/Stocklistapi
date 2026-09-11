"""Tradable universes, as Yahoo Finance NSE tickers.

IMPORTANT: index membership changes. These lists are a snapshot, not a live
feed, and a backtest over a current list carries survivorship bias -- the names
dropped from the index are missing, and the ones that survived are winners by
construction. Refresh them from NSE's published constituent files and treat any
measured edge as optimistic until a point-in-time list is wired in.

Tickers Yahoo does not recognise, or that lack enough history, are skipped by
the ranking engine rather than raising, so a stale list degrades quietly.
"""

NIFTY_50 = [
    "ADANIENT.NS",
    "ADANIPORTS.NS",
    "APOLLOHOSP.NS",
    "ASIANPAINT.NS",
    "AXISBANK.NS",
    "BAJAJ-AUTO.NS",
    "BAJFINANCE.NS",
    "BAJAJFINSV.NS",
    "BEL.NS",
    "BHARTIARTL.NS",
    "CIPLA.NS",
    "COALINDIA.NS",
    "DRREDDY.NS",
    "EICHERMOT.NS",
    "ETERNAL.NS",
    "GRASIM.NS",
    "HCLTECH.NS",
    "HDFCBANK.NS",
    "HDFCLIFE.NS",
    "HEROMOTOCO.NS",
    "HINDALCO.NS",
    "HINDUNILVR.NS",
    "ICICIBANK.NS",
    "INDUSINDBK.NS",
    "INFY.NS",
    "ITC.NS",
    "JIOFIN.NS",
    "JSWSTEEL.NS",
    "KOTAKBANK.NS",
    "LT.NS",
    "M&M.NS",
    "MARUTI.NS",
    "NESTLEIND.NS",
    "NTPC.NS",
    "ONGC.NS",
    "POWERGRID.NS",
    "RELIANCE.NS",
    "SBILIFE.NS",
    "SBIN.NS",
    "SHRIRAMFIN.NS",
    "SUNPHARMA.NS",
    "TATACONSUM.NS",
    "TATAMOTORS.NS",
    "TATASTEEL.NS",
    "TCS.NS",
    "TECHM.NS",
    "TITAN.NS",
    "TRENT.NS",
    "ULTRACEMCO.NS",
    "WIPRO.NS",
]

NIFTY_NEXT_50 = [
    "ABB.NS", "ADANIENSOL.NS", "ADANIGREEN.NS", "ADANIPOWER.NS", "AMBUJACEM.NS",
    "DMART.NS", "BAJAJHLDNG.NS", "BANKBARODA.NS", "BPCL.NS", "BRITANNIA.NS",
    "CANBK.NS", "CGPOWER.NS", "CHOLAFIN.NS", "DABUR.NS", "DIVISLAB.NS",
    "DLF.NS", "GAIL.NS", "GODREJCP.NS", "HAVELLS.NS", "HAL.NS",
    "ICICIGI.NS", "ICICIPRULI.NS", "INDHOTEL.NS", "INDIGO.NS", "IOC.NS",
    "IRFC.NS", "JINDALSTEL.NS", "JSWENERGY.NS", "LICI.NS", "LODHA.NS",
    "LTIM.NS", "MOTHERSON.NS", "NAUKRI.NS", "PFC.NS", "PIDILITIND.NS",
    "PNB.NS", "RECLTD.NS", "SHREECEM.NS", "SIEMENS.NS", "TATAPOWER.NS",
    "TORNTPHARM.NS", "TVSMOTOR.NS", "UNITDSPR.NS", "VBL.NS", "VEDL.NS",
    "ZYDUSLIFE.NS", "BOSCHLTD.NS", "MAZDOCK.NS", "SOLARINDS.NS", "SWIGGY.NS",
]

# Remaining large/mid names that round the list out towards the NIFTY 200.
_BROADER = [
    "ABCAPITAL.NS", "ALKEM.NS", "APLAPOLLO.NS", "ASHOKLEY.NS", "ASTRAL.NS",
    "ATGL.NS", "AUBANK.NS", "AUROPHARMA.NS", "BALKRISIND.NS", "BANDHANBNK.NS",
    "BERGEPAINT.NS", "BHARATFORG.NS", "BHEL.NS", "BIOCON.NS", "BSE.NS",
    "COFORGE.NS", "COLPAL.NS", "CONCOR.NS", "CUMMINSIND.NS", "DALBHARAT.NS",
    "DEEPAKNTR.NS", "DIXON.NS", "ESCORTS.NS", "EXIDEIND.NS", "FEDERALBNK.NS",
    "FORTIS.NS", "GMRAIRPORT.NS", "GODREJPROP.NS", "HDFCAMC.NS", "HINDPETRO.NS",
    "IDEA.NS", "IDFCFIRSTB.NS", "INDUSTOWER.NS", "IPCALAB.NS", "IRCTC.NS",
    "IREDA.NS", "JUBLFOOD.NS", "KALYANKJIL.NS", "KPITTECH.NS", "LAURUSLABS.NS",
    "LICHSGFIN.NS", "LUPIN.NS", "MANKIND.NS", "MARICO.NS", "MAXHEALTH.NS",
    "MFSL.NS", "MPHASIS.NS", "MRF.NS", "MUTHOOTFIN.NS", "NATIONALUM.NS",
    "NHPC.NS", "NMDC.NS", "NYKAA.NS", "OBEROIRLTY.NS", "OFSS.NS",
    "OIL.NS", "PAGEIND.NS", "PATANJALI.NS", "PAYTM.NS", "PERSISTENT.NS",
    "PETRONET.NS", "PHOENIXLTD.NS", "POLICYBZR.NS", "POLYCAB.NS", "PRESTIGE.NS",
    "RVNL.NS", "SAIL.NS", "SBICARD.NS", "SJVN.NS", "SONACOMS.NS",
    "SRF.NS", "SUNTV.NS", "SUPREMEIND.NS", "SUZLON.NS", "SYNGENE.NS",
    "TATACHEM.NS", "TATACOMM.NS", "TATAELXSI.NS", "TATATECH.NS", "THERMAX.NS",
    "TIINDIA.NS", "TORNTPOWER.NS", "TRIDENT.NS", "TUBEINVEST.NS", "UBL.NS",
    "UNIONBANK.NS", "UPL.NS", "YESBANK.NS",
]

NIFTY_100 = NIFTY_50 + NIFTY_NEXT_50
NIFTY_200 = NIFTY_100 + _BROADER

UNIVERSES = {
    "nifty50": NIFTY_50,
    "nifty100": NIFTY_100,
    "nifty200": NIFTY_200,
}

DEFAULT_UNIVERSE = "nifty200"


def get_universe(name: str = DEFAULT_UNIVERSE) -> list[str]:
    return list(UNIVERSES.get((name or "").lower(), NIFTY_200))
