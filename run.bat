@echo off
:: ====================================================================
:: Terminal Runner for Envoy Rainmaker Flight Time Converter (Windows)
:: ====================================================================

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Running setup first...
    call "setup.bat"
    if %errorlevel% neq 0 exit /b %errorlevel%
    echo.
)

echo [INFO] Running Envoy Rainmaker Flight Time Converter...
"venv\Scripts\python.exe" scrape_flight_time.py %*
