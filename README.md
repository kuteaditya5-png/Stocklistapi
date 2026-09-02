# StockLens AI v0.6 — Price & Affordability Filter

Vercel-ready update for the existing StockLens AI project.

## New in v0.6
- Dual stock-price range slider.
- Quick filters: Any Affordable, Under ₹200, Under ₹500, ₹500–₹1,000, ₹1,000–₹2,500.
- The price filter works in both 1-Month Investing and Intraday modes.
- The backend searches the full NIFTY 50 for the selected price band before doing heavier analysis.
- 1-Month cards now show:
  - share price
  - affordable whole-share quantity
  - capital used
  - cash remaining
  - estimated 1-month value based on invested shares + remaining cash
- Intraday cards now show:
  - maximum affordable shares
  - risk-based quantity
  - capital used
  - cash remaining
- Stocks that cannot fit at least one whole share inside the supplied capital are excluded in this prototype.

## Deploy
Replace the corresponding files in your existing GitHub repository, then commit to `main`.
Vercel should redeploy automatically.

Most important changed files:
- `index.html`
- `static/style.css`
- `api/index.py`

The full package is included so you can also replace the complete project contents.

## Important
Stock price itself does not make a stock better or worse. The price range is only an affordability filter. StockLens still ranks matching stocks using its model.

Forecasts and intraday signals are model estimates, not guaranteed returns or investment advice.
