# StockLens AI v1.7 — Stress & Robustness Validation

v1.7 keeps the v1.5 Trend + Low Vol sideways-market winner frozen. It does not optimize the model.

## Tests
- Top-N sensitivity: Top 2, 3, 4, and 5 portfolios
- Small predefined weight perturbations around trend and low-volatility weights
- Bullish / sideways / bearish regime breakdown
- Normal / high-volatility breakdown
- Early-vs-late chronological stability over long history

## Promotion rule
The frozen model must remain positive across the principal robustness checks. A PASS advances StockLens to v1.8 real-world execution/cost simulation. A REVIEW means diagnose the weak stress dimension rather than retune blindly.
