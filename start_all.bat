@echo off
echo ========================================================
echo Starting PII Shield Full Stack Development Environment
echo ========================================================

echo.
echo [1/2] Starting FastAPI Backend on Port 8000...
start cmd /k "cd /d %~dp0 && call .\venv\Scripts\activate.bat && uvicorn app.main:app --reload"

echo.
echo [2/2] Starting Main App (Chat & Admin) on Port 3000...
start cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================================
echo All servers are starting in separate windows.
echo - Chat UI: http://localhost:3000
echo - Admin UI: http://localhost:3000/admin
echo - API Docs: http://localhost:8000/docs
echo ========================================================
pause
