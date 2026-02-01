# AI Sentinel - Complete Startup Guide

## Prerequisites

Before starting, ensure you have:
- Docker and Docker Compose installed
- Git (to clone/pull updates)
- A configured `.env` file (copy from `.env.example`)

---

## Quick Start (TL;DR)

```bash
cd /home/griffiniskid/Documents/ai-sentinel

# 1. Fix permissions
chmod -R 777 logs/
sudo chown -R $(whoami):$(whoami) web/.next web/node_modules 2>/dev/null || true

# 2. Set required environment variable
export POSTGRES_PASSWORD=changeme

# 3. Start all services
docker-compose up -d --build

# 4. Verify everything is running
docker ps
curl http://localhost:8080/health
```

---

## Step-by-Step Guide

### Step 1: Navigate to Project Directory

```bash
cd /home/griffiniskid/Documents/ai-sentinel
```

### Step 2: Verify .env File Exists

```bash
# Check if .env exists
ls -la .env

# If it doesn't exist, create from example
cp .env.example .env
```

**Required variables in .env:**
| Variable | Description | Example |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram bot token from @BotFather | `8404113626:AAF...` |
| `OPENROUTER_API_KEY` | AI provider API key | `sk-or-v1-...` |
| `HELIUS_API_KEY` | Solana RPC (for whale tracking) | `ea3c96bd-...` |

### Step 3: Fix Permission Issues

The most common startup failure is permission errors. Run these commands:

```bash
# Fix logs directory (required)
chmod -R 777 logs/

# Clear old log files if needed
rm -f logs/*.log logs/*.json

# Fix web directory if needed (for frontend development)
sudo chown -R $(whoami):$(whoami) web/.next web/node_modules 2>/dev/null || true
```

### Step 4: Set PostgreSQL Password

Docker Compose requires this environment variable:

```bash
export POSTGRES_PASSWORD=changeme
```

Or add it to your `.env` file:
```
POSTGRES_PASSWORD=changeme
```

### Step 5: Start Services with Docker

```bash
# Build and start all containers
docker-compose up -d --build
```

This starts 3 containers:
| Container | Port | Purpose |
|-----------|------|---------|
| `ai-sentinel-bot` | 8080, 8443 | Main bot + API server |
| `ai-sentinel-postgres` | 5432 (internal) | Database for Blinks & stats |
| `ai-sentinel-redis` | 6379 (internal) | Cache layer |

### Step 6: Verify Containers Are Running

```bash
# Check container status
docker ps

# Expected output - all containers should show "Up" status:
# ai-sentinel-bot       Up (healthy)
# ai-sentinel-postgres  Up (healthy)
# ai-sentinel-redis     Up (healthy)
```

If `ai-sentinel-bot` shows "Restarting", check logs:
```bash
docker logs ai-sentinel-bot --tail 50
```

### Step 7: Test API Endpoints

```bash
# Health check
curl http://localhost:8080/health

# Expected response:
# {"status": "healthy", "service": "AI Sentinel Web API", ...}

# Test trending tokens
curl http://localhost:8080/api/v1/trending

# Test stats
curl http://localhost:8080/api/v1/stats
```

---

## Starting the Frontend (Optional)

The Next.js frontend runs separately on port 3000:

```bash
cd web

# Install dependencies (first time only)
npm install

# Development mode
npm run dev

# Or production build
npm run build && npm start
```

Access at: http://localhost:3000

---

## Common Issues & Fixes

### Issue 1: "Permission denied: '/app/logs/ai_sentinel.log'"

**Cause:** Docker container can't write to mounted logs directory.

**Fix:**
```bash
chmod -R 777 logs/
docker restart ai-sentinel-bot
```

### Issue 2: "POSTGRES_PASSWORD is required"

**Cause:** Environment variable not set.

**Fix:**
```bash
export POSTGRES_PASSWORD=changeme
docker-compose up -d
```

### Issue 3: Container keeps restarting

**Diagnose:**
```bash
docker logs ai-sentinel-bot --tail 100
```

**Common causes:**
- Missing API keys in `.env`
- Permission issues (see Issue 1)
- Python import errors (check logs)

### Issue 4: Port 8080 not responding

**Check if container is running:**
```bash
docker ps | grep ai-sentinel-bot
```

**Check if port is bound:**
```bash
netstat -tlnp | grep 8080
# or
ss -tlnp | grep 8080
```

**Check for port conflicts:**
```bash
lsof -i :8080
```

### Issue 5: Frontend shows no data

**Cause:** Backend API (port 8080) not running or not accessible.

**Fix:**
1. Ensure backend is running: `curl http://localhost:8080/health`
2. Check frontend environment: `web/.env.local` should have:
   ```
   NEXT_PUBLIC_API_URL=http://localhost:8080
   ```

### Issue 6: "Cannot connect to database"

**Check PostgreSQL is healthy:**
```bash
docker logs ai-sentinel-postgres
docker exec ai-sentinel-postgres pg_isready -U sentinel -d ai_sentinel
```

---

## Useful Commands

### View Logs
```bash
# Bot logs (live)
docker logs -f ai-sentinel-bot

# All services
docker-compose logs -f

# Last 100 lines
docker logs ai-sentinel-bot --tail 100
```

### Restart Services
```bash
# Restart single container
docker restart ai-sentinel-bot

# Restart all
docker-compose restart

# Full rebuild
docker-compose down && docker-compose up -d --build
```

### Stop Services
```bash
# Stop all containers
docker-compose down

# Stop and remove volumes (WARNING: deletes database!)
docker-compose down -v
```

### Enter Container Shell
```bash
docker exec -it ai-sentinel-bot bash
```

### Check Database
```bash
docker exec -it ai-sentinel-postgres psql -U sentinel -d ai_sentinel
```

---

## API Endpoints Reference

Once running, these endpoints are available at `http://localhost:8080`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1` | GET | API info |
| `/api/v1/trending` | GET | Trending tokens |
| `/api/v1/trending?category=gainers` | GET | Top gainers |
| `/api/v1/trending?category=losers` | GET | Top losers |
| `/api/v1/trending?category=new` | GET | New tokens |
| `/api/v1/analyze` | POST | Analyze token |
| `/api/v1/whales` | GET | Whale activity |
| `/api/v1/stats` | GET | Dashboard stats |
| `/api/v1/portfolio` | GET | Portfolio (auth required) |

---

## Production Deployment

For production, additional steps are recommended:

1. **Use HTTPS** - Set up nginx/traefik reverse proxy
2. **Set webhook mode** - Configure `WEBHOOK_URL` in `.env`
3. **Secure passwords** - Use strong `POSTGRES_PASSWORD`
4. **Enable firewall** - Only expose necessary ports
5. **Set up monitoring** - Use health check endpoints

---

## Complete Startup Script

Save this as `start.sh` for convenience:

```bash
#!/bin/bash
set -e

echo "=== AI Sentinel Startup ==="

cd /home/griffiniskid/Documents/ai-sentinel

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
echo "Telegram Bot: Active (check @your_bot)"
echo "Logs: docker logs -f ai-sentinel-bot"
```

Make it executable:
```bash
chmod +x start.sh
./start.sh
```
