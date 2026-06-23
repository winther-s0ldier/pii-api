@echo off
echo ========================================================
echo Starting PII Shield Full Stack Development Environment
echo ========================================================

echo.
echo [1/3] Starting Local ML API (Docker) on Port 7860...
docker rm -f pii_ml_api >nul 2>&1
docker run -d --name pii_ml_api -p 7860:7860 pii_ml_api:latest

echo.
echo [2/3] Starting FastAPI Backend on Port 8001...
start cmd /k "cd /d %~dp0 && call .\venv\Scripts\activate.bat && uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --reload-dir app"

echo.
echo [3/3] Starting Main App (Chat ^& Admin) on Port 3000...
start cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================================
echo All servers are starting in separate windows.
echo - Chat UI: http://localhost:3000
echo - Admin UI: http://localhost:3000/admin
echo - API Docs: http://localhost:8001/docs
echo - ML API Docs: http://localhost:7860/docs
echo ========================================================
pause
