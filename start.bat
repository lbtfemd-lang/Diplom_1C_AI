@echo off
chcp 65001 >nul
echo ═══════════════════════════════════════
echo   1C AI Assistant — Middleware
echo ═══════════════════════════════════════
echo.
echo Starting server on http://127.0.0.1:8000
echo Press Ctrl+C to stop
echo.
cd /d "%~dp0\Middleware"
python main.py
pause
