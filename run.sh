#!/bin/bash
# AI Sentinel Bot Launcher

echo "🛡️  Starting AI Sentinel Bot..."
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ ERROR: .env file not found!"
    echo ""
    echo "Please create .env file with:"
    echo "  BOT_TOKEN=your_telegram_bot_token"
    echo "  OPENAI_API_KEY=sk-..."
    echo ""
    exit 1
fi

# Check if dependencies are installed
if ! python3 -c "import aiogram" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip3 install -r requirements.txt
    echo ""
fi

# Run the bot
echo "🚀 Launching bot..."
echo ""
python3 -m src.main
