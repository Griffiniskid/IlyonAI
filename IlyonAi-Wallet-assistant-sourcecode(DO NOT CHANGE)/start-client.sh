#!/bin/bash
set -e
cd "$(dirname "$0")/client"

# Add bun to PATH
export PATH="$HOME/.bun/bin:$PATH"

echo "▶ Starting Vite dev server"
echo ""
echo "  Popup    → http://localhost:5173/popup.html"
echo "  SidePanel → http://localhost:5173/sidepanel.html"
echo ""
bun run dev
