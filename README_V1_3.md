# StockLens AI v1.3 — Market Regime Validation

Adds point-in-time regime diagnostics to the frozen v1.2 monthly Top-3 model.

- Bullish / Sideways / Bearish classification from NIFTY 3-month trend and 200-day EMA.
- High volatility classification from 20-day realized volatility vs its trailing 252-day 70th percentile.
- No v1.2 ranking weights are changed.
- New endpoint: `/api/research/regime-validation`.
- New Strategy Lab button: `Run v1.3 Market Regime Test`.
