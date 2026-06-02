# IlyonAI Coder Handoff

This document is for the next coder taking over the project from the GitHub repository.

## Exact Version To Install

Use the latest GitHub `main` commit currently present on `origin/main`:

```bash
git clone https://github.com/Griffiniskid/IlyonAI.git
cd IlyonAI
git fetch origin --prune
git checkout main
git pull --ff-only origin main
git checkout ae5f8a70224dc7ff6c1360855919fbbab133e57e
```

Latest GitHub commit at handoff time:

| Field | Value |
|---|---|
| Branch | `origin/main` |
| Commit | `ae5f8a70224dc7ff6c1360855919fbbab133e57e` |
| Short SHA | `ae5f8a7` |
| Date | `2026-05-23T15:25:54+03:00` |
| Message | `docs: wallet-tailored tester script for Phantom Solana (Аккаунт 1)` |
| Remote | `https://github.com/Griffiniskid/IlyonAI.git` |

If you want to keep working on the live branch instead of a detached commit, run this after verifying the SHA:

```bash
git checkout main
```

## Local Workspace Versus GitHub

At handoff time, local `HEAD` equals `origin/main` at `ae5f8a7`. There are no local commits ahead of GitHub. The differences are uncommitted local files only.

Tracked local changes not in GitHub before this handoff file was created:

| Status | Path | Meaning |
|---|---|---|
| Deleted | `.claude/commands/goal.md` | Local deletion of the old autonomous goal command. GitHub still has the file. |
| Modified | `docs/matrix-runs/passA-waveD1/regression-sweep.md` | Local update from 2 reopened regression patterns to 1 reopened pattern, with revised sample text. |
| Modified | `scripts/validation/post_deploy_smoke.py` | Local smoke-test timeout bump from 60/70s to 120/130s and sanitizer for `user_message` / `cross_chain_message` before forbidden-substring checks. |

Untracked local files not in GitHub before this handoff file was created:

| Count | Area | Notes |
|---:|---|---|
| 1363 | `docs/playwright-runs/` | Local Playwright validation artifacts, JSON summaries, screenshots. |
| 242 | `docs/conversation-runs/` | Local conversation matrix artifacts. |
| 2 | `docs/audit-runs/` | Local static/regression audit run docs. |
| 1 | `docs/anvil-fork-runs/` | Local Anvil fork plan artifact. |
| 1 | `services/solana-yield-builder/package-lock.json` | Local npm lock generated for the Solana sidecar; latest GitHub does not include it. |
| 1 | `.claude/scheduled_tasks.lock` | Local automation lock file. |
| 1 | `.claude/commands/goal-ilyon.md` | Local replacement command file. |

This `HANDOFF.md` file is also a local addition until someone commits and pushes it. Do not assume it exists in a fresh clone unless it has been committed after this handoff.

## What The Project Is

Ilyon AI is an AI-native, non-custodial DeFi copilot. Users ask natural-language questions or execution requests, and the system returns typed cards, analysis, or unsigned wallet-ready transactions for the user to sign in their own wallet.

Main product surfaces:

- Agent chat with typed cards for token reports, pool reports, allocations, swaps, execution plans, blockers, and final text.
- Sentinel risk scoring across token security, pool durability, exit depth, deployer/entity history, whale/smart-money signals, and wallet approval exposure.
- Multi-chain DeFi discovery and execution across Solana plus Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, and Avalanche.
- Solana Actions / Blinks endpoints.
- EVM transaction building through Enso, 0x, and deBridge.
- Solana transaction building through Jupiter plus Raydium, Orca, Meteora, Kamino, Marinade, Jito, and Sanctum adapters.

## Runtime Architecture

The repo is a multi-service system:

| Component | Path | Runtime | Role |
|---|---|---|---|
| Sentinel API | `src/` | Python 3.11, aiohttp | Main backend, agent endpoint, Sentinel scoring, DeFi intelligence, Blinks, portfolio, Shield, smart money, routes under `/api/v1/*` and `/api/v2/defi/*`. |
| Web frontend | `web/` | Next.js 14, React 18, TypeScript | Chat UI, wallet adapters, typed card rendering, frontend API rewrites. |
| Wallet Assistant | `IlyonAi-Wallet-assistant-main/server/` | Python 3.11, FastAPI | EVM-side action builder for Enso, 0x, deBridge, LLM agent platform sidecar. |
| Solana Yield Builder | `services/solana-yield-builder/` | Node 20 | Solana transaction sidecar for LP, lend, stake, and swap build paths. |
| Redis | Docker image | Redis 7 | Cache/session acceleration. |
| Postgres | Docker image | Postgres 15 | Persistent storage for sessions/app state where enabled. |

Important backend entry points:

- `src/main.py` starts the aiohttp app and lifecycle hooks.
- `src/api/app.py` wires middleware and all HTTP route groups.
- `src/config.py` is the central Pydantic settings file and reads `.env`.
- `src/api/routes/agent.py` is the main agent chat route wiring.
- `src/agent/` and `src/defi/` contain the active execution/intelligence logic.
- `web/types/agent.ts` mirrors card payload types used by the frontend.

Important docs:

- `README.md` for public product overview.
- `docs/ARCHITECTURE.md` for internal architecture. It is useful but partially stale in small details, so verify against code.
- `deploy/README.md` for production/staging VPS layout.
- `docs/ops/vps-access-and-docker-runbook.md` for VPS operations.
- `docs/TESTER_WALLET_SCRIPT.md` and `docs/TESTER_WALKTHROUGH_v2.md` for current tester-ready validation.
- `IlyonAi_Development_Plan_v2.md`, `IlyonAi_LP_Execution_Spec.pdf`, and `docs/SPEC_COVERAGE.md` for the LP execution spec and coverage history.

## Recommended Install: Docker Compose

Use Docker Compose first. It is the closest path to the deployed service graph.

Requirements:

- Git.
- Docker Engine with Docker Compose v2.
- Enough disk for Python/Node images and Playwright Chromium in the API image.

Create a root `.env` file. Do not commit it.

Minimum local `.env` skeleton:

```env
COMPOSE_PROJECT_NAME=ilyonai-local
API_HOST_PORT=8080
WEB_HOST_PORT=3000
API_CONTAINER_PORT=8080
LOGS_DIR=./logs/local

POSTGRES_DB=ilyon_ai
POSTGRES_USER=sentinel
POSTGRES_PASSWORD=change-me-local
DATABASE_URL=postgresql://sentinel:change-me-local@postgres:5432/ilyon_ai
REDIS_URL=redis://redis:6379/0

WEB_API_PORT=8080
WEB_API_HOST=0.0.0.0
WEBAPP_URL=http://localhost:3000
ACTIONS_BASE_URL=http://localhost:8080
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

NEXT_PUBLIC_API_URL=http://localhost:3000
NEXT_PUBLIC_SOLANA_NETWORK=mainnet-beta
NEXT_PUBLIC_SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
API_REWRITE_TARGET=http://api:8080
ASSISTANT_API_TARGET=http://assistant-api:8000
SENTINEL_API_TARGET=http://api:8080
AGENT_BACKEND=hybrid

SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
OPENROUTER_API_KEY=
GROK_API_KEY=
OPENAI_API_KEY=
HELIUS_API_KEY=
MORALIS_API_KEY=
ENSO_API_KEY=
JUPITER_API_KEY=
SESSION_SECRET=change-me-local-session-secret
JWT_SECRET=change-me-local-jwt-secret
```

Notes on secrets:

- At least one LLM provider key is needed for live agent behavior. The code prefers OpenRouter/Groq/OpenAI depending on the path.
- Helius, Moralis, Enso, Jupiter, deBridge referral, Etherscan-family, GoPlus, Birdeye, and similar provider keys improve production parity but are not all required for the containers to start.
- Never copy a production `.env` into a commit or chat transcript.

Start the full stack:

```bash
docker compose up -d --build
docker compose ps
```

Health checks:

```bash
curl -i http://localhost:8080/health
curl -i http://localhost:3000/api/v1/agent-health
```

Logs:

```bash
docker compose logs -f api web assistant-api solana-yield-builder
```

Stop the stack:

```bash
docker compose down
```

## Local Development Install

Use this if you need fast edit/test loops outside Docker.

Backend API:

```bash
python -m venv .venv
. .venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r IlyonAi-Wallet-assistant-main/server/requirements.txt
python -m playwright install chromium
python -m src.main
```

On Windows PowerShell, activate with:

```powershell
.\.venv\Scripts\Activate.ps1
```

Frontend:

```bash
cd web
npm ci
copy .env.local.example .env.local
npm run dev
```

Edit `web/.env.local` if needed:

```env
NEXT_PUBLIC_API_URL=http://localhost:8080
API_REWRITE_TARGET=http://localhost:8080
ASSISTANT_API_TARGET=http://localhost:8000
NEXT_PUBLIC_SOLANA_NETWORK=mainnet-beta
NEXT_PUBLIC_SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
```

Wallet Assistant sidecar:

```bash
cd IlyonAi-Wallet-assistant-main/server
python -m venv .venv
. .venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Solana Yield Builder sidecar:

```bash
cd services/solana-yield-builder
npm install
set PORT=8090
set SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
npm start
```

The sidecar has no committed `package-lock.json` in latest GitHub, so use `npm install` rather than `npm ci` unless the lock file is intentionally committed later.

## Common Commands

Frontend checks:

```bash
cd web
npm run type-check
npm run build
npm test
```

Backend unit tests:

```bash
pytest tests/defi
```

Validation and staging smoke scripts:

```bash
python scripts/validation/post_deploy_smoke.py
python scripts/validation/static_sweep.py
python scripts/validation/regression_sweep.py
python scripts/validation/conversation_matrix.py
```

Browser smoke and fork replay tooling also exist:

```bash
python scripts/playwright_browser_smoke.py
python scripts/anvil_fork_replay.py
```

Some validation scripts are designed for `https://staging.ilyonai.com`, not local Docker. Read the script constants before running them.

## Deployment Notes

The deployment docs describe two isolated VPS stacks:

| Stack | Branch | Directory | Public URL |
|---|---|---|---|
| Production | `main` | `/home/aisentinel/ai-sentinel` | `https://ilyonai.com` |
| Staging | `staging` | `/home/aisentinel/ai-sentinel-staging` | `https://staging.ilyonai.com` |

Normal VPS deploy command from the target directory:

```bash
git pull --ff-only
docker compose up -d --build
docker compose ps
```

The repo docs say production should be treated as protected. Validate on staging first.

## Work Areas To Understand Before Editing

- Agent/card pipeline: `src/api/routes/agent.py`, `src/agent/`, `web/types/agent.ts`, and the card components under `web/`.
- DeFi execution: `src/defi/execution/`, `src/defi/adapters/`, `src/defi/routing/`, and the wallet assistant sidecar.
- Runtime invariants and blockers: `src/agent/runtime_invariants.py`, `tests/defi/test_runtime_invariants.py`, and wave-specific tests in `tests/defi/`.
- Solana transaction builds: `services/solana-yield-builder/src/`.
- Frontend API rewrites and wallet UI: `web/next.config.js`, `web/components/`, `web/app/`.

## Current Validation Context

The current GitHub history is centered around `tester-ready-v2` work. Recent top commits include:

- `ae5f8a7` docs: wallet-tailored tester script for Phantom Solana.
- `33a273e` docs: tester walkthrough v2 with 18 prompts covering 23 BUG-RC closures.
- `6483747` tagged `tester-ready-v2` with 23/23 BUG-RC closed, matrix passes, Playwright, Anvil baseline, and conversation matrix claims.

Important caution: local untracked validation artifacts suggest additional validation was run after the latest GitHub commit, but those artifacts are not part of GitHub unless committed.

## Safe Handoff Checklist For The Next Coder

1. Clone the repo and verify `git rev-parse HEAD` is `ae5f8a70224dc7ff6c1360855919fbbab133e57e` if reproducing the current GitHub state.
2. Create local env files from the skeletons; never commit secrets.
3. Start with `docker compose up -d --build` and confirm `api`, `web`, `assistant-api`, `solana-yield-builder`, `redis`, and `postgres` are healthy.
4. Read `README.md`, `docs/ARCHITECTURE.md`, `docs/TESTER_WALLET_SCRIPT.md`, and `docs/ops/vps-access-and-docker-runbook.md` before changing execution code.
5. Before trusting local-only changes, inspect `git status --short --branch` and decide whether each local artifact should be committed, ignored, or discarded.
6. For code changes, add or run the nearest existing pin test under `tests/defi/` and run the relevant validation script.
7. Do not deploy production directly. Use staging first and record receipts.
