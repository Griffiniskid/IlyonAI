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
- runtime env file
- frontend build-time API URL

The production example intentionally keeps `COMPOSE_PROJECT_NAME=ai-sentinel` so your first rollout can keep using the existing production Docker volumes.

## 1. Create environment files

From the repo root:

```bash
cp deploy/prod/compose.env.example deploy/prod/compose.env
cp deploy/prod/app.env.example deploy/prod/app.env
cp deploy/staging/compose.env.example deploy/staging/compose.env
cp deploy/staging/app.env.example deploy/staging/app.env
```

Then fill in the real secrets.

Keep `POSTGRES_PASSWORD` in `deploy/*/compose.env` and the password embedded in `deploy/*/app.env`'s `DATABASE_URL` in sync.

Important staging differences:

- use a different `POSTGRES_PASSWORD`
- use a different `DATABASE_URL` database name (`ilyon_ai_staging`)
- use a different `SESSION_SECRET`
- set `ACTIONS_BASE_URL`, `WEBAPP_URL`, and `CORS_ORIGINS` to `https://staging.ilyonai.com`
- if you use any webhook-style integration, do not point the production webhook at staging

## 2. Reverse proxy by hostname

Copy `deploy/Caddyfile.example` to `/etc/caddy/Caddyfile` on the VPS, then reload Caddy:

```bash
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

The example routes:

- `ilyonai.com` -> API on `127.0.0.1:8080`, web on `127.0.0.1:3000`
- `staging.ilyonai.com` -> API on `127.0.0.1:18080`, web on `127.0.0.1:13000`

## 3. Cloudflare DNS

In Cloudflare DNS for `ilyonai.com`:

1. Keep the existing proxied `A` record for `@` pointing to `173.249.5.167`
2. Keep the existing proxied `A` record for `www` pointing to `173.249.5.167`
3. Add a new proxied `A` record:
   - Name: `staging`
   - IPv4 address: `173.249.5.167`
   - Proxy status: `Proxied`

## 4. Cloudflare Access for private staging

Use Cloudflare Zero Trust to protect only `staging.ilyonai.com`.

1. Open `Zero Trust` -> `Access` -> `Applications`
2. Click `Add an application`
3. Choose `Self-hosted`
4. Name: `Ilyon AI Staging`
5. Domain: `staging.ilyonai.com`
6. Session duration: `24 hours` (or your preference)
7. Under policies, add an `Allow` policy for your testers:
   - include specific emails, or
   - include your team email domain, or
   - include a GitHub org if you already use GitHub auth in Zero Trust
8. Save the application

If you do not already have a login method configured, set one up first in:

- `Zero Trust` -> `Settings` -> `Authentication`

The quickest option is `One-time PIN`, but Google or GitHub login is better for repeat testers.

Note: Cloudflare Access protects the whole host, including `/api/*`. Browser testers will work normally after login, but public webhooks, bots, and unauthenticated unfurls will be blocked unless you add a specific bypass or service-token policy.

## 5. Safe VPS layout

Keep production and staging in separate worktrees on the VPS so each environment can pull a different branch safely.

If the GitHub repository is private, authenticate the VPS first as the `aisentinel` user.

Generate an SSH deploy key on the VPS:

```bash
su - aisentinel -c 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" -C "aisentinel-vps"'
su - aisentinel -c 'cat ~/.ssh/id_ed25519.pub'
```

Add that public key in GitHub -> repository `Settings` -> `Deploy keys` -> `Add deploy key`.
Read-only access is enough.

Then switch the repo remote to SSH:

```bash
su - aisentinel -c 'cat > ~/.ssh/config <<"EOF"
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh-keyscan -H github.com >> ~/.ssh/known_hosts
chmod 644 ~/.ssh/known_hosts
cd /home/aisentinel/ai-sentinel && git remote set-url origin git@github.com:Griffiniskid/AISentinel.git'
```

Example layout:

```bash
cd /home/aisentinel/ai-sentinel
git fetch origin
git worktree add ../ai-sentinel-staging origin/staging
```

That leaves:

- `/home/aisentinel/ai-sentinel` for production (`main`)
- `/home/aisentinel/ai-sentinel-staging` for staging (`staging`)

If the `staging` branch does not exist yet, create it from your laptop first:

```bash
git checkout -b staging
git push -u origin staging
```

## 6. Deploy commands

Production deploy from `/home/aisentinel/ai-sentinel`:

```bash
docker compose --env-file deploy/prod/compose.env up -d --build
```

Staging deploy from `/home/aisentinel/ai-sentinel-staging`:

```bash
docker compose --env-file deploy/staging/compose.env up -d --build
```

Check status:

```bash
docker compose --env-file deploy/prod/compose.env ps
docker compose --env-file deploy/staging/compose.env ps
```

## 7. Recommended promotion flow

1. Create a feature branch on your laptop
2. Push the feature branch to GitHub
3. Merge that work into `staging`
4. On the VPS, pull the `staging` worktree and rebuild the staging stack
5. Test on `https://staging.ilyonai.com` through Cloudflare Access
6. When the exact staging commit is approved, fast-forward `main` to that commit
7. Pull production and rebuild the production stack

Example commands:

```bash
# laptop: move approved code into staging
git checkout staging
git merge --ff-only your-feature-branch
git push origin staging

# vps: update staging
cd /home/aisentinel/ai-sentinel-staging
git pull --ff-only
docker compose --env-file deploy/staging/compose.env up -d --build

# laptop: promote the tested commit to production
git checkout main
git merge --ff-only staging
git push origin main

# vps: update production
cd /home/aisentinel/ai-sentinel
git pull --ff-only
docker compose --env-file deploy/prod/compose.env up -d --build
```

This keeps staging ahead of production without changing production until you promote the tested commit.
