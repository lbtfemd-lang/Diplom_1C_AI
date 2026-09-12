@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"

echo ======================================================================
echo Запуск автоматического развертывания проекта для 1С:Предприятия...
echo ======================================================================

if exist "Middleware\.venv\Scripts\python.exe" (
    "Middleware\.venv\Scripts\python.exe" scripts\deploy_contest_base.py %*
) else (
    py -3.12 scripts\deploy_contest_base.py %*
)

if errorlevel 1 (
    echo.
    echo Ошибка при развертывании! Проверьте наличие платформы 1С и файла dist\SmallBusinessDemo.dt.
    pause
    exit /b 1
)

exit /b 0
