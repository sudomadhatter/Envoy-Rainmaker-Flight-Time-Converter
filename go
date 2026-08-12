#!/bin/bash
# ====================================================================
# Double-Clickable Auto-Setup & Runner for macOS Finder / Terminal
# ====================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "========================================================"
echo "✈️  ENVOY RAINMAKER FLIGHT TIME CONVERTER"
echo "========================================================"

# Auto-run setup if virtual environment is missing
if [ ! -d "venv" ]; then
    echo "📦 Initializing setup..."
    bash "./setup.sh"
    echo ""
fi

echo "🚀 Processing flight schedule PDFs..."
./venv/bin/python3 scrape_flight_time.py "$@"

echo ""
echo "========================================================"
echo "✅ Execution finished."
echo "========================================================"
