# StockLens AI v0.8 — Strategy Research Lab

Keeps all v0.7 features and adds an experimental Strategy Lab.

Intraday candidate filters:
- no entries before 09:45 or after 14:15
- model score >= 80
- relative volume >= 1.15
- slower trend alignment
- minimum distance from VWAP

1-month technical candidate:
- technical score >= 85
- Close > EMA50 > EMA200
- positive 1-month momentum
- positive 3-month momentum
- RSI 50–70

The Strategy Lab compares v0.7 baseline vs v0.8 candidate for:
Intraday: signals, T1 hit rate, positive rate, expectancy, profit factor, drawdown.
1-month proxy: samples, positive rate, beat-NIFTY rate, average return, excess return.

IMPORTANT: v0.8 does NOT automatically replace the live rules with whichever historical test looks best. That would invite overfitting. Candidate rules should be promoted only after separate out-of-sample validation.

New file: api/strategy_lab.py
Changed: api/index.py, index.html, static/style.css

Replace project files in GitHub and commit to main for Vercel redeploy.
