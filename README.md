# StockLens AI — Vercel Ready v0.3

This package is prepared for:

**Local files → GitHub → Vercel**

## Project structure

```text
StockLens_AI_Vercel_Ready/
├─ index.html
├─ static/
│  └─ style.css
├─ api/
│  ├─ index.py
│  ├─ scanner.py
│  ├─ data_provider.py
│  ├─ indicators.py
│  ├─ scoring.py
│  ├─ universe.py
│  └─ models.py
├─ pyproject.toml
├─ requirements.txt
├─ .gitignore
└─ README.md
```

## API URLs after deployment

```text
/api/health
/api/stock/RELIANCE
/api/ranking?top=5&limit_universe=5
/docs
```

## Local API test

From the project root:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn api.index:app --reload
```

The API will run at:

```text
http://127.0.0.1:8000/api/health
```

Note: when using plain Uvicorn locally, the static `index.html` is not served by
that Python process. Vercel will serve the root static dashboard automatically.

## Push to GitHub

Create an empty GitHub repository, then from this project folder run:

```powershell
git init
git add .
git commit -m "Initial StockLens AI Vercel deployment"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

## Deploy on Vercel

1. Sign in to Vercel.
2. Choose **Add New → Project**.
3. Import the GitHub repository.
4. Leave the framework as auto-detected / Other if Vercel does not select one.
5. Keep the project root as the repository root.
6. Deploy.

Vercel detects `api/index.py` as the FastAPI Python entrypoint and installs
Python dependencies from `pyproject.toml`.

## Important serverless limit

The Vercel starter caps each live ranking request at 20 stocks. The current
scanner performs multiple external Yahoo Finance requests, so a full 50-stock
scan is better implemented later using a scheduled scan + cached results rather
than making the browser wait for all 50 calls in one serverless request.

## Current scoring is still a prototype

Before treating rankings as actionable, add:

- sector-specific bank/NBFC scoring
- 3–5 year fundamentals
- ROCE
- promoter holding / promoter pledge
- peer-relative valuation
- news risk
- historical backtesting
