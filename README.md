# StockLens AI v0.7 — Accuracy & Backtesting

This version keeps:
- 1-Month Investing
- Intraday Trading
- Intraday-only stock price filter

And adds a new:
- Accuracy & Backtest tab

## Intraday backtest
The intraday backtest uses the SAME signal rules as the live intraday scanner:
- 5-minute bars
- VWAP (now reset each trading session)
- EMA 9 / EMA 20
- RSI
- relative volume
- 20-bar breakout / breakdown
- Target 1 = +1.5R
- Stop = -1R
- default maximum hold = 12 x 5-minute bars (~60 minutes)
- first valid signal per stock per day
- same-bar stop + target ambiguity is counted as a stop conservatively

Metrics:
- signals tested
- Target 1 hit rate
- positive outcome rate
- expectancy in R
- average winner / loser
- profit factor
- max drawdown in R
- BUY vs SELL breakdown
- confidence/model-score breakdown
- stock-price breakdown
- time-of-day breakdown

## 1-Month backtest
The app also includes a historical 1-month TECHNICAL PROXY:
- 21 trading-day forward returns
- technical score threshold
- positive-after-1-month rate
- beat-NIFTY rate
- average stock return
- average NIFTY return
- average excess return

IMPORTANT:
This is deliberately labelled a technical proxy, not full StockLens accuracy.
A true historical test of the complete 1-month model needs point-in-time historical
fundamentals, valuation and shareholding data. Free Yahoo data does not reliably
provide those historical snapshots.

## Deployment
Replace the files in your existing GitHub repository and commit to `main`.
Vercel should redeploy automatically.

New file:
- `api/backtest.py`

Main changed files:
- `api/index.py`
- `api/intraday.py`
- `index.html`
- `static/style.css`

## Backtest limitations
Historical results do not guarantee future performance.
Intraday tests currently exclude brokerage, taxes, slippage and bid/ask spread.
Yahoo data can contain gaps/revisions.
Using current NIFTY 50 constituents creates survivorship bias.
