@echo off
:: ====================================================================
:: Envoy Rainmaker Flight Time Converter for Windows PC
:: Double-click this file in Windows Explorer to run automatically!
:: ====================================================================

title Envoy Rainmaker Flight Time Converter
cd /d "%~dp0"

echo ========================================================
echo Envoy Rainmaker Flight Time Converter
echo ========================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [INFO] Initializing setup on Windows...
    call "setup.bat"
    echo.
)

echo [INFO] Processing flight schedule PDFs...
"venv\Scripts\python.exe" scrape_flight_time.py %*

echo.
echo ========================================================
echo Execution finished.
echo ========================================================
pause
