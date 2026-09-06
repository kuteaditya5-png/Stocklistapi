# StockLens AI v1.1 — Larger Universe Monthly Ranking

## What changed
- Added a separate **v1.1 Monthly ranking universe** selector: 10 / 20 / 30 / 50 stocks.
- Default monthly ranking test now uses 20 representative NIFTY 50 stocks.
- The old 3 / 5 Representative stocks selector remains for legacy Strategy Lab / intraday comparisons.
- Monthly ranking continues to select Top 3 and compare approximately 1-month portfolio returns with NIFTY.
- Research vs unseen metrics include positive months, NIFTY beat rate, average return, excess return and max drawdown.

## GitHub / Vercel
Replace the repository files with this package, preserving the `api/` and `static/` folders, then commit to `main`. Vercel should redeploy automatically.

## First test
Open Strategy Lab, leave **v1.1 Monthly ranking universe = 20 stocks**, and press **Run v1.1 Ranking Test**.
