# VPS Access And Docker Runbook

This runbook lets another agent manage the production VPS without interactive SSH prompts.

## Host

- Host: `173.249.5.167`
- SSH user: `aisentinel`
- App directory: `/home/aisentinel/ai-sentinel`
- Public domain: `https://ilyonai.com`
- Docker Compose project: `ai-sentinel`

## SSH Access

Use a dedicated key for automation. The current OpenCode key is stored locally at:

```bash
~/.ssh/opencode_ai_sentinel_vps_ed25519
```

Connect non-interactively:

```bash
ssh -i ~/.ssh/opencode_ai_sentinel_vps_ed25519 -o BatchMode=yes aisentinel@173.249.5.167
```

Run one command remotely:

```bash
ssh -i ~/.ssh/opencode_ai_sentinel_vps_ed25519 -o BatchMode=yes aisentinel@173.249.5.167 \
  'cd ~/ai-sentinel && docker compose ps'
```

Do not commit private SSH keys. To add another agent, generate a new keypair and append only its `.pub` key to:

```bash
/home/aisentinel/.ssh/authorized_keys
```

Recommended permissions on the VPS:

```bash
chmod 700 /home/aisentinel/.ssh
chmod 600 /home/aisentinel/.ssh/authorized_keys
```

## Docker Services

List service state:

```bash
cd ~/ai-sentinel
docker compose ps
```

Follow logs:

```bash
docker compose logs -f web assistant-api api
```

Check recent logs:

```bash
docker compose logs --since=10m web assistant-api api
```

Restart after code or env changes:

```bash
docker compose up -d --build --force-recreate web assistant-api api
docker compose ps
```

Stop everything only when necessary:

```bash
docker compose down
```

## Health Checks

From the VPS host:

```bash
curl -i http://localhost:3000/api/v1/agent-health
curl -i http://localhost:8080/health
```

From inside the web container:

```bash
docker compose exec -T web wget -qO- http://assistant-api:8000/health
docker compose exec -T web wget -qO- http://api:8080/health
docker compose exec -T web wget -qO- http://127.0.0.1:3000 >/dev/null && echo web-ok
```

From the public domain:

```bash
curl -i https://ilyonai.com/api/v1/agent-health
```

## Env Files

Production env files live under:

```bash
deploy/prod/compose.env
deploy/prod/app.env
deploy/prod/assistant.env
```

The root `.env` may also be present. Confirm what Compose resolves before restarting:

```bash
docker compose config | sed -n '/assistant-api:/,/^[a-zA-Z0-9_-]*:/p'
docker compose config | sed -n '/web:/,/^[a-zA-Z0-9_-]*:/p'
```

Check assistant config without printing secret values:

```bash
docker compose exec -T assistant-api python - <<'PY'
from app.core.config import settings
print('llm_keys:', sorted(settings.api_keys.keys()))
print('enso:', bool(settings.enso_api_key))
print('debridge:', bool(getattr(settings, 'debridge_referral_code', '')))
print('rpc_urls_type:', type(settings.rpc_urls).__name__)
PY
```

## Deployment Validation

After each deploy, validate the domain with real requests:

```bash
curl -i https://ilyonai.com/api/v1/agent-health

curl -i -m 120 https://ilyonai.com/api/v1/agent \
  -H 'content-type: application/json' \
  --data '{"query":"Hello","session_id":"ops-hello","user_address":"","solana_address":"","chain_id":1}'

curl -i -m 120 https://ilyonai.com/api/v1/agent \
  -H 'content-type: application/json' \
  --data '{"query":"swap 0.003 bnb for eth","session_id":"ops-bsc-swap","user_address":"0xfbc2f432a1f661107632277098814d9bc4fba920","solana_address":"5Mg7Pqgx77vNYCmaPQ5ZVgVZNJdYPS5qZppj9x19839L","chain_id":56,"wallet_type":"metamask"}'
```

Expected result for the BNB swap request: HTTP `200` with JSON response. It may return a valid `evm_action_proposal` or an upstream rate-limit explanation, but it should not return non-JSON HTTP `500`.
