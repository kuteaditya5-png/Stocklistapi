# StockLens AI v0.5
Vercel-ready dual-mode build.

Modes:
- 1-Month Investment Finder
- Intraday Trading Finder

Intraday uses 5-minute Yahoo Finance data with VWAP, EMA 9/20, RSI, relative volume, 20-bar breakout/breakdown and ATR-based stop/targets. It includes a NO TRADE gate and risk-based position sizing.

Replace the corresponding files in your existing GitHub repository and commit. Vercel should redeploy automatically.

Prototype research model only; backtesting and more reliable real-time market data are required before relying on it for trading.
