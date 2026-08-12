#!/bin/bash
# ====================================================================
# Setup Script for Envoy Rainmaker Flight Time Converter
# ====================================================================

set -e

echo "🚀 Setting up Envoy Rainmaker Flight Time Converter..."

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is required but not installed."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  -> Found Python $PYTHON_VERSION"

# Create Virtual Environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment (venv)..."
    python3 -m venv venv
fi

# Upgrade pip and install requirements
echo "📥 Installing required Python packages..."
./venv/bin/pip install --upgrade pip --quiet
./venv/bin/pip install -r requirements.txt --quiet

# Ensure directories exist
mkdir -p "new" "scraped" "logten pro format"

# Make scripts executable
chmod +x scrape_flight_time.py setup.sh run.sh 2>/dev/null || true

echo ""
echo "✅ Setup complete!"
echo "--------------------------------------------------------"
echo "To process flight time PDFs:"
echo "1. Place your monthly PDF files in the 'new/' folder."
echo "2. Run: ./run.sh"
echo "--------------------------------------------------------"
