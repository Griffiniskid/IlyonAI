# Staging + Production Deployment

This repo can run two isolated stacks on the same VPS:

- `ai-sentinel` serves `https://ilyonai.com`
- `ilyonai-staging` serves `https://staging.ilyonai.com`

Each stack gets its own:

- Docker Compose project name
- container names (via the Compose project prefix)
- host ports
- PostgreSQL volume
- Redis volume
- frontend build-time API URL

## 1. VPS layout

Keep production and staging in separate directories so each can track a
different branch and carry its own `.env`:

```
/home/aisentinel/ai-sentinel          ← main branch  (production)
/home/aisentinel/ai-sentinel-staging  ← staging branch
```

Create the staging worktree (one-time):

```bash
cd /home/aisentinel/ai-sentinel
git fetch origin
git worktree add ../ai-sentinel-staging origin/staging
```

## 2. Single `.env` per directory

Docker Compose automatically reads `.env` from the working directory.
Each directory has its own `.env` with **both** compose settings and app
secrets — no `--env-file` or `-p` flags needed.

### Production (`~/ai-sentinel/.env`)

Add these lines at the top of your existing `.env`:

```env
COMPOSE_PROJECT_NAME=ai-sentinel
API_HOST_PORT=8080
WEB_HOST_PORT=3000
LOGS_DIR=./logs
NEXT_PUBLIC_API_URL=https://ilyonai.com
NEXT_PUBLIC_SOLANA_NETWORK=mainnet-beta
NEXT_PUBLIC_SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
POSTGRES_DB=ilyon_ai
POSTGRES_USER=sentinel
```

### Staging (`~/ai-sentinel-staging/.env`)

Copy the production `.env` and change these values:

```env
COMPOSE_PROJECT_NAME=ilyonai-staging
API_HOST_PORT=18080
WEB_HOST_PORT=13000
LOGS_DIR=./logs/staging
NEXT_PUBLIC_API_URL=https://staging.ilyonai.com

POSTGRES_DB=ilyon_ai_staging
POSTGRES_PASSWORD=<different-password>
DATABASE_URL=postgresql://sentinel:<different-password>@postgres:5432/ilyon_ai_staging
SESSION_SECRET=<different-secret>
ACTIONS_BASE_URL=https://staging.ilyonai.com
WEBAPP_URL=https://staging.ilyonai.com
CORS_ORIGINS=https://staging.ilyonai.com
```

## 3. Deploy commands

From either directory, just:

```bash
git pull --ff-only
docker compose up -d --build
```

That's it. No `--env-file`, no `-p` flags. Docker reads `.env` automatically
and picks up the correct project name, ports, and API URL.

Check status:

```bash
docker compose ps
docker compose logs -f --tail=50
```

## 4. Reverse proxy (Caddy)

Copy `deploy/Caddyfile.example` to `/etc/caddy/Caddyfile` on the VPS:

```bash
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Routes:

- `ilyonai.com` → API on `127.0.0.1:8080`, web on `127.0.0.1:3000`
- `staging.ilyonai.com` → API on `127.0.0.1:18080`, web on `127.0.0.1:13000`

## 5. Cloudflare DNS

In Cloudflare DNS for `ilyonai.com`:

| Type | Name      | IPv4            | Proxy   |
|------|-----------|-----------------|---------|
| A    | @         | 173.249.5.167   | Proxied |
| A    | www       | 173.249.5.167   | Proxied |
| A    | staging   | 173.249.5.167   | Proxied |

## 6. Promotion flow

```bash
# laptop: merge feature into staging
git checkout staging
git merge --ff-only your-feature-branch
git push origin staging

# vps: deploy staging
cd ~/ai-sentinel-staging
git pull --ff-only
docker compose up -d --build

# laptop: promote to production after testing
git checkout main
git merge --ff-only staging
git push origin main

# vps: deploy production
cd ~/ai-sentinel
git pull --ff-only
docker compose up -d --build
```
