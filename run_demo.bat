@echo off
setlocal
cd /d "%~dp0"
if exist "Middleware\.venv\Scripts\python.exe" (
    "Middleware\.venv\Scripts\python.exe" scripts\run_demo.py %*
) else (
    py -3.12 scripts\run_demo.py %*
)
if errorlevel 1 (
    echo Demo failed. Install Python 3.12 and Middleware/requirements.txt.
    exit /b 1
)
