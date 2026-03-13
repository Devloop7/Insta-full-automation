@echo off
title InstaBot Dashboard
color 0A

echo.
echo  ==========================================
echo   InstaBot Dashboard - Starting...
echo  ==========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found!
    echo.
    echo  Please install Python from: https://python.org/downloads
    echo  Make sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

:: Create .env if missing
if not exist .env (
    echo  Creating .env from template...
    copy .env.example .env >nul
    echo  [!] Edit .env to add your MiniMax API key when ready.
    echo.
)

:: Install dependencies
echo  Installing dependencies...
pip install -r requirements.txt -q

echo.
echo  ==========================================
echo   Dashboard is starting at:
echo   http://localhost:8000
echo  ==========================================
echo.

:: Open browser after 3 seconds
start "" timeout /t 3 /nobreak >nul && start http://localhost:8000

:: Start server
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

pause
