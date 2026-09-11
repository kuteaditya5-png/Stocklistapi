# StockLens AI v2.1 — Ship the model you validated

v2.0 validated one model and served a different one. v2.1 fixes that, plus the
universe truncation bug and the uncalibrated numbers on the investing cards.
No ranking weights were changed.

## 1. `/api/portfolio` now runs the frozen v1.5 model

Previously it called `scanner.analyse_stock` → `scoring.calculate_stocklens_score`,
a hand-written rubric that was never backtested. The Accuracy & Backtest tab
measured the Trend + Low Vol cross-sectional ranker instead. Users were shown
results from the unmeasured model and accuracy figures from the measured one.

`api/live_ranker.py` now runs the same frozen model live, from a single batched
download. `scoring.py` and `scanner.py` are untouched and still serve
`/api/ranking`.

## 2. The universe is no longer truncated alphabetically

`_batch_price_prefilter` returned `symbols[:max_candidates]`. With the default
`limit_universe=10`, "Top 3 of NIFTY 50" was really top 3 of ADANIENT through
BHARTIARTL — RELIANCE, TCS and INFY could never be picked.

- The 1-month tab now ranks all 50 in one download; `limit_universe` is accepted
  but ignored.
- Where a per-symbol cap is still needed (intraday), `_spread()` takes evenly
  spaced tickers instead of the first N.

## 3. Uncalibrated numbers removed

| Removed | Was | Now |
|---|---|---|
| `confidence` | `max(40, min(85, score))` — the score relabelled as a percentage | `score_percentile` (rank within universe) |
| `expected_return_low/high_pct` | `(score-55)*0.22 + (tech-50)*0.05`, clamped −2%…+8% | 20th–80th percentile of that stock's own realised 21-day returns |
| `downside_value` | `min(low, -2.0)` | 5th percentile of the same measured distribution |
| — | — | `positive_rate`: share of historical 21-day windows that closed up |

The card now states that the range is measured history, not a forecast, and
discloses the 49% monthly NIFTY-beat rate inline.

## 4. One scoring code path

The frozen formula was inlined in nine places. `api/ranking_core.py` is now the
single definition; `monthly_ranker.py` imports it. Verified numerically
identical to the previous literals, and all v1.1–v2.0 research endpoints run
unchanged.

## Still outstanding

- Point-in-time NIFTY 50 constituents (survivorship bias remains).
- STT and 20% short-term capital-gains tax are still excluded from v1.9/v2.0.
- Fixed backtest dates; `period="5y"` still slides with the current date.
- `scoring.py` fundamentals are largely inert — yfinance `.info` returns `None`
  for `pegRatio` and several other fields on NSE tickers, so most stocks score
  the 50 baseline in those categories.

## 5. Interface

The old interface was dark navy with a mint accent — the register of a trading
app that promises an edge. That now contradicts what the product says about
itself, so it was rebuilt as a measurement record.

- Light sage ledger stock, petrol-slate ink, hairline rules, no card shadows.
- Newsreader for the headline and figures, IBM Plex Sans for everything
  functional, tabular numerals throughout.
- The hero leads with the 49% beat rate rather than burying it.
- Each pick plots its own p05-p20-median-p80 distribution against a zero line,
  so the spread is visible rather than summarised into one number.
- Copy is sentence case, no all-caps labels, no "guaranteed" register.
  Empty and error states say what happened and what to try.
- Responsive to 380px, visible keyboard focus, reduced motion respected.

`static/style.css` is gone; the CSS is inlined in the dashboard so Vercel
bundling can never drop it. `api/dashboard.py` is the source of truth and
`index.html` is a byte-identical copy for static hosting.
