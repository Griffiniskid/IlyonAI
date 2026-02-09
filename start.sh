#!/bin/bash
set -e

echo "=== AI Sentinel Startup ==="

# Fix permissions
echo "[1/4] Fixing permissions..."
chmod -R 777 logs/ 2>/dev/null || mkdir -p logs && chmod -R 777 logs/

# Check .env
echo "[2/4] Checking configuration..."
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Copy from .env.example first."
    exit 1
fi

# Set postgres password if not in environment
export POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-changeme}

# Start containers
echo "[3/4] Starting Docker containers..."
docker-compose up -d --build

# Wait for startup
echo "[4/4] Waiting for services..."
sleep 5

# Verify
echo ""
echo "=== Container Status ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "=== Health Check ==="
curl -s http://localhost:8080/health | python3 -m json.tool 2>/dev/null || echo "API not ready yet, wait a few seconds..."

echo ""
echo "=== Startup Complete ==="
echo "API: http://localhost:8080"
echo "Frontend: http://localhost:3000 (run 'cd web && npm run dev' separately)"
