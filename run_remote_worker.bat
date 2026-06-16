@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"

echo.
echo ========================================
echo   PICADIRI Remote Drive Render Worker
echo ========================================
echo.

if not exist "venv" (
    echo [1/3] Creating virtual environment...
    python -m venv venv
) else (
    echo [1/3] Virtual environment found.
)

echo [2/3] Activating virtual environment...
call venv\Scripts\activate.bat

if not exist "venv\Lib\site-packages\fastapi" (
    echo [3/3] Installing dependencies...
    python -m pip install -r requirements.txt
) else (
    echo [3/3] Dependencies look installed.
)

echo.
echo Worker modes:
echo   1. Continuous worker
echo   2. Check settings and queue
echo   3. Process one job and exit
echo.
set /p mode="Select mode [1/2/3, default 1]: "

if "%mode%"=="2" (
    python remote_drive_worker.py --check
    pause
    exit /b
)

if "%mode%"=="3" (
    python remote_drive_worker.py --once
    pause
    exit /b
)

python remote_drive_worker.py
pause
