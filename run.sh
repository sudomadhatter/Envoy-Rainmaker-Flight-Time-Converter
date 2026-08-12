#!/bin/bash
# ====================================================================
# One-Click Runner for Pilot Flight Time Scraper
# ====================================================================

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "⚙️ Virtual environment not found. Running setup first..."
    ./setup.sh
fi

echo "✈️ Running Pilot Flight Time Scraper..."
./venv/bin/python3 scrape_flight_time.py "$@"
