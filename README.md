# StockLens AI v0.9.2 — Vercel Embedded Dashboard Fix

The v0.9.1 screenshot confirmed:
- FastAPI backend was running.
- Vercel's Python function bundle did NOT contain root `index.html`.

v0.9.2 removes that dependency.

## Fix
The full StockLens dashboard HTML + CSS + JavaScript is now embedded in:
- `api/dashboard.py`

The root `/` route loads that Python module, so Vercel bundles the dashboard together
with `api/index.py`.

## Fastest GitHub update
Add/replace only:
1. `api/dashboard.py`  <-- NEW
2. `api/index.py`

Keep `api/optimizer.py` and the other v0.9 files already in the repository.

Commit to `main`, wait for Vercel redeploy, then test:
- `/api/health`
- `/`

Expected health output includes:
- `"status":"ok"`
- `"version":"0.9.2"`
- `"dashboard_mode":"embedded"`
- `"dashboard_module":true`

`index.html` and `static/style.css` may remain in the repository, but the Vercel root
dashboard no longer depends on them.
