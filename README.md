# StockLens AI v0.9
Adds a walk-forward 1-month strategy optimizer.

It splits history chronologically into training, validation and unseen test data.
Candidate rules are selected without looking at unseen-test results. The main objective
is excess return versus NIFTY, with minimum sample requirements.

New file: api/optimizer.py
Changed: api/index.py, index.html, static/style.css

GitHub/Vercel: add/replace those files, commit to main, then use Strategy Lab -> Run v0.9 Walk-Forward.
Historical performance is not a guarantee of future returns.
