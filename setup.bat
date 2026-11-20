@echo off
:: ====================================================================
:: Setup Script for Windows PC
:: ====================================================================

title Envoy Rainmaker Setup
cd /d "%~dp0"

echo [INFO] Setting up Python virtual environment on Windows...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to PATH!
    echo Please install Python 3.10 or newer from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

if not exist "venv" (
    echo [INFO] Creating venv directory...
    python -m venv venv
)

echo [INFO] Installing required packages...
"venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
"venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet

if not exist "new" mkdir "new"
if not exist "scraped" mkdir "scraped"
if not exist "logten pro format" mkdir "logten pro format"

echo.
echo [SUCCESS] Windows setup complete!
echo --------------------------------------------------------
echo To process flight time PDFs:
echo 1. Place your monthly PDF files in the 'new' folder.
echo 2. Run: run.bat
echo --------------------------------------------------------
