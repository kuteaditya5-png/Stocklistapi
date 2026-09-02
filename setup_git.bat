@echo off
echo Initializing StockLens AI Git repository...
git init
git add .
git commit -m "Initial StockLens AI Vercel deployment"
git branch -M main
echo.
echo Git repository initialized.
echo Next run:
echo git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
echo git push -u origin main
pause
