#!/bin/bash
# AI Sentinel - API Launcher

echo "Starting AI Sentinel API..."
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "ERROR: .env file not found!"
    echo ""
    echo "Please create .env file from .env.example:"
    echo "  cp .env.example .env"
    echo ""
    exit 1
fi

# Check if dependencies are installed
if ! python3 -c "import aiohttp" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
    echo ""
fi

# Run the API
echo "Launching API..."
echo ""
python3 -m src.main
