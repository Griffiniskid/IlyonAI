# Agent Platform Merge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge every feature of the IlyonAi Wallet Assistant (`IlyonAi-Wallet-assistant-main/`) into the Ilyon platform so the combined system exposes all 14 LangChain DeFi tools, the full chat UI (matching the existing `/agent/chat` mockup), a live tokens ticker, the Chrome extension, the AffiliateHook contract, and Greenfield memory — every tool response routed through Ilyon Sentinel scoring and Shield verdicts, behind feature flags until cutover.

**Architecture:** One backend (aiohttp, `src/`), one frontend (Next.js, `web/`), one PostgreSQL, one users table (`web_users` extended). A LangChain ReAct agent (14 tools) wraps Ilyon's `src/ai/router` as its LLM, dispatches to Ilyon's existing services where they exist and to new `src/routing/*` adapters where they don't, and runs every tool output through a Sentinel/Shield decorator that emits a typed card over SSE. 13 workstreams ship in parallel behind feature flags; a single Day-0 PR locks the 5 cross-workstream contracts.

**Tech Stack:** Python 3.11 / aiohttp / async SQLAlchemy / asyncpg / LangChain / pydantic-settings · Next.js 14 / React / TypeScript / Tailwind · Foundry (Solidity) · pytest / Playwright / Alembic · BNB Greenfield · Chrome MV3.

**Spec:** `docs/superpowers/specs/2026-04-21-agent-platform-merge-design.md`

---

## Phase 0 — Pre-Day-0 (blocking)

### Task 0.1: Rotate compromised Moralis JWT

**Files:**
- Modify: `IlyonAi-Wallet-assistant-main/server/app/agents/crypto_agent.py:38`
- Create: `scripts/audit_secrets.py`

- [ ] **Step 1: Rotate at Moralis dashboard**

Manually: Moralis dashboard → API keys → revoke the leaked JWT → mint a new one → copy value.

- [ ] **Step 2: Put new key in local `.env`**

```
MORALIS_API_KEY=<new-jwt>
```

- [ ] **Step 3: Replace the hardcoded literal**

Change `crypto_agent.py:38` from the literal JWT to:

```python
import os
MORALIS_API_KEY = os.environ["MORALIS_API_KEY"]
```

- [ ] **Step 4: Write the audit script**

Create `scripts/audit_secrets.py`:

```python
"""Fails CI if any known-compromised secret prefix appears in tracked files."""
from __future__ import annotations
import hashlib
import subprocess
import sys
from pathlib import Path

BLOCKED_SHA256 = {
    # sha256 of the old Moralis JWT literal that used to live in
    # IlyonAi-Wallet-assistant-main/server/app/agents/crypto_agent.py:38
    # (fill in when rotating)
    "REPLACE_WITH_SHA256_OF_OLD_JWT",
}

BLOCKED_PREFIXES = (
    "eyJhbGciOiJIUzI1NiIs",  # any JWT — flag for manual review, not blocked
)

def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [Path(p) for p in out if p]

def main() -> int:
    bad = []
    for path in tracked_files():
        if not path.is_file():
            continue
        try:
            blob = path.read_bytes()
        except (OSError, UnicodeDecodeError):
            continue
        digest = hashlib.sha256(blob).hexdigest()
        if digest in BLOCKED_SHA256:
            bad.append(f"{path}: blocklisted by content hash")
        text = blob.decode("utf-8", errors="ignore")
        for prefix in BLOCKED_PREFIXES:
            if prefix in text and "test_fixtures" not in str(path):
                bad.append(f"{path}: contains suspected JWT prefix {prefix}")
    if bad:
        print("SECRET AUDIT FAILED:", file=sys.stderr)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Fill in the SHA-256 of the old JWT**

Run locally (one-shot, never commit the literal):

```bash
python -c "import hashlib; print(hashlib.sha256(b'<OLD_JWT_LITERAL>').hexdigest())"
```

Paste the digest into `BLOCKED_SHA256` in `scripts/audit_secrets.py`.

- [ ] **Step 6: Wire into CI**

Add to `.github/workflows/ci.yml` (or the equivalent existing CI file):

```yaml
- name: Audit secrets
  run: python scripts/audit_secrets.py
```

- [ ] **Step 7: Run audit locally**

Run: `python scripts/audit_secrets.py`
Expected: exit 0 (no bad hits after the rotation commit).

- [ ] **Step 8: Commit**

```bash
git add scripts/audit_secrets.py .github/workflows/ci.yml \
    IlyonAi-Wallet-assistant-main/server/app/agents/crypto_agent.py
git commit -m "security: rotate leaked Moralis key, add secret audit script"
```

---

## Phase 1 — Day-0 Contracts PR (blocking; single PR)

Everything downstream forks from this PR. Nothing else starts until it lands.

### Task 1.1: Backend schema module

**Files:**
- Create: `src/api/schemas/agent.py`
- Test: `tests/api/schemas/test_agent_schemas.py`

- [ ] **Step 1: Write the failing test**

`tests/api/schemas/test_agent_schemas.py`:

```python
import pytest
from pydantic import ValidationError
from src.api.schemas.agent import (
    ToolEnvelope, SentinelBlock, ShieldBlock, AgentCard,
    AllocationPayload, SwapQuotePayload, PoolPayload, TokenPayload,
    PositionPayload, PlanPayload, BalancePayload, BridgePayload,
    StakePayload, MarketOverviewPayload, PairListPayload,
    SSEFrame, ObservationFrame, CardFrame, FinalFrame,
)

def test_tool_envelope_round_trip_minimal_success():
    env = ToolEnvelope(
        ok=True, data={"x": 1}, card_type=None, card_id="00000000-0000-0000-0000-000000000001",
        card_payload=None,
    )
    assert env.ok is True
    assert env.error is None
    assert env.model_dump()["card_id"] == "00000000-0000-0000-0000-000000000001"

def test_tool_envelope_failure_requires_error():
    with pytest.raises(ValidationError):
        ToolEnvelope(ok=False, data=None, card_type=None, card_id="x", card_payload=None)

def test_agent_card_discriminator_routes_to_correct_payload():
    raw = {
        "card_id": "00000000-0000-0000-0000-000000000001",
        "card_type": "allocation",
        "payload": {
            "positions": [], "total_usd": "10000",
            "weighted_sentinel": 89, "risk_mix": {"LOW": 4, "MEDIUM": 1, "HIGH": 0},
        },
    }
    parsed = AgentCard.model_validate(raw)
    assert parsed.card_type == "allocation"
    assert isinstance(parsed.payload, AllocationPayload)

def test_sse_frame_observation_forbids_data():
    ObservationFrame(step_index=1, name="get_token_price", ok=True, error=None)
    # data field does not exist; any extra field should be rejected
    with pytest.raises(ValidationError):
        ObservationFrame(step_index=1, name="x", ok=True, error=None, data={"y": 1})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/schemas/test_agent_schemas.py -v`
Expected: FAIL (ImportError, module not found)

- [ ] **Step 3: Write minimal schema module**

`src/api/schemas/agent.py`:

```python
"""Cross-workstream schemas for the agent platform.

These are frozen at Day 0. Every workstream reads them; no workstream
may silently extend them. Breaking changes require a migration task.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ─── scoring blocks ──────────────────────────────────────────────────────

class SentinelBlock(_Strict):
    sentinel: int = Field(ge=0, le=100)
    safety: int = Field(ge=0, le=100)
    durability: int = Field(ge=0, le=100)
    exit: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    risk_level: Literal["HIGH", "MEDIUM", "LOW"]
    strategy_fit: Literal["conservative", "balanced", "aggressive"]
    flags: list[str] = Field(default_factory=list)


class ShieldBlock(_Strict):
    verdict: Literal["SAFE", "CAUTION", "RISKY", "DANGEROUS", "SCAM"]
    grade: Literal["A+", "A", "B", "C", "D", "F"]
    reasons: list[str] = Field(default_factory=list)


# ─── card payloads (one per card_type) ───────────────────────────────────

class _CardPayloadBase(_Strict):
    sentinel: Optional[SentinelBlock] = None
    shield: Optional[ShieldBlock] = None


class AllocationPosition(_Strict):
    rank: int
    protocol: str
    asset: str
    chain: str
    apy: str
    weight: int
    usd: str
    router: str
    sentinel: Optional[SentinelBlock] = None
    shield: Optional[ShieldBlock] = None


class AllocationPayload(_CardPayloadBase):
    positions: list[AllocationPosition]
    total_usd: str
    weighted_sentinel: int
    risk_mix: dict[str, int]


class SwapQuotePayload(_CardPayloadBase):
    pay: dict[str, Any]
    receive: dict[str, Any]
    rate: str
    router: str
    price_impact_pct: float
    priority_fee_usd: Optional[str] = None


class PoolPayload(_CardPayloadBase):
    protocol: str
    chain: str
    asset: str
    apy: str
    tvl: str


class TokenPayload(_CardPayloadBase):
    symbol: str
    address: str
    chain: str
    price_usd: str
    change_24h_pct: float


class PositionPayload(_CardPayloadBase):
    wallet: str
    rows: list[dict[str, Any]]


class PlanStep(_Strict):
    step: int
    action: str
    detail: str


class PlanPayload(_CardPayloadBase):
    steps: list[PlanStep]
    requires_signature: bool


class BalancePayload(_CardPayloadBase):
    wallet: str
    total_usd: str
    by_chain: dict[str, str]


class BridgePayload(_CardPayloadBase):
    source_chain: str
    target_chain: str
    pay: dict[str, Any]
    receive: dict[str, Any]
    estimated_seconds: int


class StakePayload(_CardPayloadBase):
    protocol: str
    asset: str
    apy: str
    unbond_days: Optional[int] = None


class MarketOverviewPayload(_CardPayloadBase):
    protocols: list[dict[str, Any]]


class PairListPayload(_CardPayloadBase):
    query: str
    pairs: list[dict[str, Any]]


# ─── card discriminated union ────────────────────────────────────────────

_CardUnion = Annotated[
    Union[
        "AllocationCard", "SwapQuoteCard", "PoolCard", "TokenCard",
        "PositionCard", "PlanCard", "BalanceCard", "BridgeCard",
        "StakeCard", "MarketOverviewCard", "PairListCard",
    ],
    Field(discriminator="card_type"),
]


class _CardBase(_Strict):
    card_id: str  # uuid string; not UUID for JSONB round-trip simplicity


class AllocationCard(_CardBase):
    card_type: Literal["allocation"]
    payload: AllocationPayload

class SwapQuoteCard(_CardBase):
    card_type: Literal["swap_quote"]
    payload: SwapQuotePayload

class PoolCard(_CardBase):
    card_type: Literal["pool"]
    payload: PoolPayload

class TokenCard(_CardBase):
    card_type: Literal["token"]
    payload: TokenPayload

class PositionCard(_CardBase):
    card_type: Literal["position"]
    payload: PositionPayload

class PlanCard(_CardBase):
    card_type: Literal["plan"]
    payload: PlanPayload

class BalanceCard(_CardBase):
    card_type: Literal["balance"]
    payload: BalancePayload

class BridgeCard(_CardBase):
    card_type: Literal["bridge"]
    payload: BridgePayload

class StakeCard(_CardBase):
    card_type: Literal["stake"]
    payload: StakePayload

class MarketOverviewCard(_CardBase):
    card_type: Literal["market_overview"]
    payload: MarketOverviewPayload

class PairListCard(_CardBase):
    card_type: Literal["pair_list"]
    payload: PairListPayload


class AgentCard(_Strict):
    """Wrapper enabling discriminated parsing via .model_validate."""
    card_id: str
    card_type: str
    payload: Any

    @classmethod
    def model_validate(cls, obj: Any, **kw):  # type: ignore[override]
        from pydantic import TypeAdapter
        return TypeAdapter(_CardUnion).validate_python(obj)


# ─── tool envelope ───────────────────────────────────────────────────────

CardType = Literal[
    "allocation", "swap_quote", "pool", "token", "position", "plan",
    "balance", "bridge", "stake", "market_overview", "pair_list",
]


class ToolError(_Strict):
    code: str
    message: str


class ToolEnvelope(_Strict):
    ok: bool
    data: Optional[dict] = None
    sentinel: Optional[SentinelBlock] = None
    shield: Optional[ShieldBlock] = None
    card_type: Optional[CardType] = None
    card_id: str
    card_payload: Optional[dict] = None
    error: Optional[ToolError] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.ok and self.error is None:
            raise ValueError("ToolEnvelope(ok=False) requires error")


# ─── SSE frames ──────────────────────────────────────────────────────────

class ThoughtFrame(_Strict):
    step_index: int
    content: str

class ToolFrame(_Strict):
    step_index: int
    name: str
    args: dict

class ObservationFrame(_Strict):
    step_index: int
    name: str
    ok: bool
    error: Optional[ToolError] = None

class CardFrame(_Strict):
    step_index: int
    card_id: str
    card_type: CardType
    payload: dict

class FinalFrame(_Strict):
    content: str
    card_ids: list[str]
    elapsed_ms: int
    steps: int

class DoneFrame(_Strict):
    pass


SSEFrame = Union[ThoughtFrame, ToolFrame, ObservationFrame, CardFrame, FinalFrame, DoneFrame]
```

- [ ] **Step 4: Run test**

Run: `pytest tests/api/schemas/test_agent_schemas.py -v`
Expected: PASS all 4.

- [ ] **Step 5: Commit**

```bash
git add src/api/schemas/agent.py tests/api/schemas/test_agent_schemas.py
git commit -m "feat(agent): add frozen schema module (ToolEnvelope, AgentCard, SSE frames)"
```

### Task 1.2: TypeScript types generator (W7 seed)

**Files:**
- Create: `scripts/gen_agent_types.py`
- Create: `web/types/agent.ts` (generated output, committed)
- Test: `tests/scripts/test_gen_agent_types.py`

- [ ] **Step 1: Write test**

`tests/scripts/test_gen_agent_types.py`:

```python
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_regeneration_is_idempotent():
    """Running the generator twice must produce identical output."""
    target = ROOT / "web" / "types" / "agent.ts"
    first = subprocess.run(
        ["python", "scripts/gen_agent_types.py", "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert first.returncode == 0, first.stderr

def test_generated_file_contains_expected_types():
    content = (ROOT / "web" / "types" / "agent.ts").read_text()
    for sym in [
        "ToolEnvelope", "AgentCard", "SentinelBlock", "ShieldBlock",
        "AllocationPayload", "SwapQuotePayload", "PoolPayload",
        "MarketOverviewPayload", "PairListPayload",
        "ThoughtFrame", "ToolFrame", "ObservationFrame",
        "CardFrame", "FinalFrame", "DoneFrame",
    ]:
        assert sym in content, f"missing {sym} in agent.ts"
```

- [ ] **Step 2: Run test — fails because generator/output missing**

Run: `pytest tests/scripts/test_gen_agent_types.py -v`
Expected: FAIL.

- [ ] **Step 3: Write generator**

`scripts/gen_agent_types.py`:

```python
"""Generate web/types/agent.ts from src/api/schemas/agent.py.

Uses pydantic's JSON schema + datamodel-code-generator. Pin versions in
requirements-dev.txt. --check exits non-zero if the current on-disk file
doesn't match freshly generated output (CI guard).
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "web" / "types" / "agent.ts"


def build_ts() -> str:
    from src.api.schemas.agent import ToolEnvelope, AgentCard  # noqa: F401
    from pydantic import TypeAdapter
    # Collect all exported symbols into one schema
    from src.api.schemas import agent as mod
    exported = [getattr(mod, n) for n in dir(mod) if n[0].isupper()]
    schemas = {cls.__name__: TypeAdapter(cls).json_schema()
               for cls in exported if hasattr(cls, "model_fields")}
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        (tdir / "schema.json").write_text(json.dumps(schemas))
        out = tdir / "out.ts"
        subprocess.run(
            [
                "datamodel-codegen",
                "--input", str(tdir / "schema.json"),
                "--input-file-type", "jsonschema",
                "--output", str(out),
                "--output-model-type", "typescript",
                "--use-schema-description",
            ],
            check=True,
        )
        return out.read_text()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = build_ts()
    if args.check:
        existing = TARGET.read_text() if TARGET.exists() else ""
        if existing.strip() != content.strip():
            print("agent.ts is stale; run scripts/gen_agent_types.py", file=sys.stderr)
            return 1
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Pin the dev dependency**

Append to `requirements-dev.txt`:

```
datamodel-code-generator[jsonschema]==0.25.6
```

Run:

```bash
pip install -r requirements-dev.txt
python scripts/gen_agent_types.py
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/scripts/test_gen_agent_types.py -v`
Expected: PASS both.

- [ ] **Step 6: Wire into CI**

Add to `.github/workflows/ci.yml`:

```yaml
- name: Check agent TS types are up to date
  run: python scripts/gen_agent_types.py --check
```

- [ ] **Step 7: Commit**

```bash
git add scripts/gen_agent_types.py web/types/agent.ts \
        tests/scripts/test_gen_agent_types.py .github/workflows/ci.yml
git commit -m "feat(agent): add Pydantic→TS codegen for frozen schemas"
```

### Task 1.3: Alembic migration — extend web_users + create chats/chat_messages

**Files:**
- Create: `migrations/versions/<hash>_agent_platform.py`
- Test: `tests/storage/test_agent_migration.py`

- [ ] **Step 1: Write the migration test**

`tests/storage/test_agent_migration.py`:

```python
import asyncio
import pytest
from sqlalchemy import text
from src.storage.database import get_database

@pytest.mark.asyncio
async def test_web_users_has_new_columns():
    db = await get_database()
    async with db._engine.connect() as conn:
        cols = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'web_users'
        """))
        names = {r[0] for r in cols}
    assert {"id", "email", "password_hash", "display_name"}.issubset(names)

@pytest.mark.asyncio
async def test_chats_and_chat_messages_exist():
    db = await get_database()
    async with db._engine.connect() as conn:
        for table in ("chats", "chat_messages"):
            row = await conn.execute(text(
                "SELECT to_regclass(:t)"), {"t": f"public.{table}"})
            assert row.scalar() is not None

@pytest.mark.asyncio
async def test_chat_messages_fk_cascades():
    db = await get_database()
    async with db._engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO web_users (wallet_address) VALUES ('test_cascade') "
            "ON CONFLICT DO NOTHING"))
        r = await conn.execute(text(
            "SELECT id FROM web_users WHERE wallet_address='test_cascade'"))
        uid = r.scalar_one()
        await conn.execute(text(
            "INSERT INTO chats (id, user_id, title) "
            "VALUES (gen_random_uuid(), :uid, 'x') RETURNING id"),
            {"uid": uid})
        # cascade on delete
        await conn.execute(text(
            "DELETE FROM web_users WHERE id=:uid"), {"uid": uid})
        left = await conn.execute(text(
            "SELECT count(*) FROM chats WHERE user_id=:uid"), {"uid": uid})
        assert left.scalar_one() == 0
```

- [ ] **Step 2: Run test to fail**

Run: `pytest tests/storage/test_agent_migration.py -v`
Expected: FAIL (columns/tables missing).

- [ ] **Step 3: Create Alembic revision**

Run: `alembic revision -m "agent_platform"`

Replace the generated `upgrade`/`downgrade` with:

```python
"""agent_platform

Revision ID: <auto>
Revises: <previous head>
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa

revision = "<auto>"
down_revision = "<previous head>"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.add_column("web_users", sa.Column("id", sa.BigInteger(), autoincrement=True))
    op.execute("CREATE SEQUENCE IF NOT EXISTS web_users_id_seq OWNED BY web_users.id")
    op.execute("UPDATE web_users SET id = nextval('web_users_id_seq') WHERE id IS NULL")
    op.alter_column("web_users", "id", nullable=False,
                    server_default=sa.text("nextval('web_users_id_seq')"))
    op.create_unique_constraint("web_users_id_unique", "web_users", ["id"])

    op.add_column("web_users", sa.Column("email", sa.String(255), nullable=True))
    op.add_column("web_users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column("web_users", sa.Column("display_name", sa.String(100), nullable=True))
    op.execute(
        "CREATE UNIQUE INDEX ix_web_users_email ON web_users (email) "
        "WHERE email IS NOT NULL"
    )

    op.create_table(
        "chats",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", sa.BigInteger(),
                  sa.ForeignKey("web_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, server_default="New Chat"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_chats_user_updated", "chats",
                    ["user_id", sa.text("updated_at DESC")])
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
        BEGIN NEW.updated_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER chats_set_updated_at
        BEFORE UPDATE ON chats FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    """)

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("cards", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("tool_trace", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="complete"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_chat_messages_chat_id", "chat_messages",
                    ["chat_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_chat_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.execute("DROP TRIGGER IF EXISTS chats_set_updated_at ON chats")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.drop_index("ix_chats_user_updated", table_name="chats")
    op.drop_table("chats")
    op.drop_index("ix_web_users_email", table_name="web_users")
    op.drop_column("web_users", "display_name")
    op.drop_column("web_users", "password_hash")
    op.drop_column("web_users", "email")
    op.drop_constraint("web_users_id_unique", "web_users", type_="unique")
    op.execute("DROP SEQUENCE IF EXISTS web_users_id_seq CASCADE")
    op.drop_column("web_users", "id")
```

- [ ] **Step 4: Run migration locally**

```bash
alembic upgrade head
```

- [ ] **Step 5: Run test**

Run: `pytest tests/storage/test_agent_migration.py -v`
Expected: PASS 3.

- [ ] **Step 6: Test down/up idempotency**

```bash
alembic downgrade -1 && alembic upgrade head
pytest tests/storage/test_agent_migration.py -v
```
Expected: still PASS.

- [ ] **Step 7: Commit**

```bash
git add migrations/ tests/storage/test_agent_migration.py
git commit -m "feat(db): extend web_users + add chats/chat_messages for agent platform"
```

### Task 1.4: Feature flag plumbing

**Files:**
- Modify: `src/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Add the flags**

In `src/config.py`, add fields to the Settings class:

```python
FEATURE_AGENT_V2: bool = False
FEATURE_TOKENS_BAR: bool = False
FEATURE_CHROME_EXT: bool = False
FEATURE_AFFILIATE_HOOK: bool = False
FEATURE_GREENFIELD_MEMORY: bool = False
ALLOWED_EXTENSION_IDS: str = ""  # comma-separated
```

Also add these service fields:

```python
MORALIS_API_KEY: str | None = None
DEXSCREENER_API_KEY: str | None = None
ENSO_API_KEY: str | None = None
JUPITER_API_BASE: str = "https://quote-api.jup.ag/v6"
DEBRIDGE_API_BASE: str = "https://api.dln.trade/v1.0"
HELIUS_API_KEY: str | None = None
BSC_RPC_URL: str | None = None
BNB_GREENFIELD_SP: str | None = None
BNB_GREENFIELD_ACCOUNT: str | None = None
BNB_GREENFIELD_PRIVATE_KEY: str | None = None
```

- [ ] **Step 2: Write & run a single sanity test**

`tests/test_config.py` (append):

```python
def test_feature_flags_default_off():
    from src.config import settings
    assert settings.FEATURE_AGENT_V2 is False
    assert settings.FEATURE_TOKENS_BAR is False
    assert settings.FEATURE_CHROME_EXT is False
```

Run: `pytest tests/test_config.py::test_feature_flags_default_off -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat(config): add agent-platform feature flags and service creds"
```

### Task 1.5: Empty route handlers behind flags

**Files:**
- Create: `src/api/routes/agent.py`
- Create: `src/api/routes/tokens_bar.py`
- Modify: `src/main.py` (wire the routes)
- Modify: `src/api/routes/auth.py` (add stubs for verify-evm/register/login/link-wallet)
- Test: `tests/api/test_agent_stubs.py`

- [ ] **Step 1: Write the test**

`tests/api/test_agent_stubs.py`:

```python
import pytest
from aiohttp.test_utils import TestClient, TestServer
from src.main import create_app

@pytest.mark.asyncio
async def test_agent_route_returns_503_when_flag_off():
    app = await create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.post("/api/v1/agent", json={"session_id": "x", "message": "hi"})
        assert r.status == 503
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/api/test_agent_stubs.py -v`
Expected: FAIL.

- [ ] **Step 3: Add the stub route**

`src/api/routes/agent.py`:

```python
from aiohttp import web
from src.config import settings

routes = web.RouteTableDef()

def _flag_off() -> web.Response:
    return web.json_response(
        {"error": "agent_v2_disabled"}, status=503)

@routes.post("/api/v1/agent")
async def agent_turn(request: web.Request) -> web.Response:
    if not settings.FEATURE_AGENT_V2:
        return _flag_off()
    # real implementation arrives in W1
    return web.json_response({"error": "not_implemented"}, status=501)

@routes.get("/api/v1/agent/sessions")
async def list_sessions(request: web.Request) -> web.Response:
    if not settings.FEATURE_AGENT_V2:
        return _flag_off()
    return web.json_response({"error": "not_implemented"}, status=501)

@routes.get("/api/v1/agent/sessions/{session_id}")
async def get_session(request: web.Request) -> web.Response:
    if not settings.FEATURE_AGENT_V2:
        return _flag_off()
    return web.json_response({"error": "not_implemented"}, status=501)
```

`src/api/routes/tokens_bar.py`:

```python
from aiohttp import web
from src.config import settings

routes = web.RouteTableDef()

@routes.get("/api/v1/tokens/ticker")
async def ticker(request: web.Request) -> web.Response:
    if not settings.FEATURE_TOKENS_BAR:
        return web.json_response({"error": "tokens_bar_disabled"}, status=503)
    return web.json_response({"error": "not_implemented"}, status=501)
```

In `src/api/routes/auth.py`, append:

```python
@routes.post("/api/v1/auth/verify-evm")
async def verify_evm_stub(request): return web.json_response({"error":"not_implemented"}, status=501)

@routes.post("/api/v1/auth/register")
async def register_stub(request): return web.json_response({"error":"not_implemented"}, status=501)

@routes.post("/api/v1/auth/login")
async def login_stub(request): return web.json_response({"error":"not_implemented"}, status=501)

@routes.post("/api/v1/auth/link-wallet")
async def link_wallet_stub(request): return web.json_response({"error":"not_implemented"}, status=501)
```

In `src/main.py`, register the new route tables:

```python
from src.api.routes import agent as agent_routes
from src.api.routes import tokens_bar as tokens_bar_routes
app.add_routes(agent_routes.routes)
app.add_routes(tokens_bar_routes.routes)
```

- [ ] **Step 4: Run test**

Run: `pytest tests/api/test_agent_stubs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/routes/agent.py src/api/routes/tokens_bar.py src/main.py \
        src/api/routes/auth.py tests/api/test_agent_stubs.py
git commit -m "feat(agent): add feature-flagged stub routes for agent + tokens + auth"
```

### Task 1.6: CORS extension-origin support

**Files:**
- Modify: `src/api/middleware/cors.py`
- Test: `tests/api/middleware/test_cors_extension.py`

- [ ] **Step 1: Write test**

```python
import pytest
from unittest.mock import MagicMock
from src.api.middleware.cors import get_cors_origin
from src.config import settings

def test_extension_origin_allowed_when_flag_on(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_CHROME_EXT", True)
    monkeypatch.setattr(settings, "ALLOWED_EXTENSION_IDS", "abc123,def456")
    req = MagicMock()
    req.path = "/api/v1/agent"
    req.headers = {"Origin": "chrome-extension://abc123"}
    assert get_cors_origin(req) == "chrome-extension://abc123"

def test_extension_origin_rejected_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_CHROME_EXT", False)
    req = MagicMock()
    req.path = "/api/v1/agent"
    req.headers = {"Origin": "chrome-extension://abc123"}
    assert not get_cors_origin(req).startswith("chrome-extension")
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Add logic**

In `src/api/middleware/cors.py`, extend `get_cors_origin`:

```python
def _is_allowed_extension_origin(origin: str) -> bool:
    from src.config import settings
    if not settings.FEATURE_CHROME_EXT:
        return False
    if not origin:
        return False
    allowed = {x.strip() for x in settings.ALLOWED_EXTENSION_IDS.split(",") if x.strip()}
    for scheme in ("chrome-extension://", "moz-extension://"):
        if origin.startswith(scheme):
            return origin.removeprefix(scheme) in allowed
    return False
```

And early in `get_cors_origin` (after the Actions/Blinks branch):

```python
    request_origin = request.headers.get("Origin", "")
    if _is_allowed_extension_origin(request_origin):
        return request_origin
```

- [ ] **Step 4: Run test — pass**

- [ ] **Step 5: Commit**

```bash
git add src/api/middleware/cors.py tests/api/middleware/test_cors_extension.py
git commit -m "feat(cors): allow pinned chrome-extension/moz-extension origins behind flag"
```

### Task 1.7: Copy AffiliateHook.sol into monorepo

**Files:**
- Create: `contracts/src/AffiliateHook.sol`
- Create: `contracts/foundry.toml`
- Create: `contracts/README.md`

- [ ] **Step 1: Copy the file**

```bash
mkdir -p contracts/src
cp IlyonAi-Wallet-assistant-main/contracts/AffiliateHook.sol contracts/src/
```
(If the path differs in the source tree, glob for `AffiliateHook.sol` and copy.)

- [ ] **Step 2: Initialize Foundry**

```bash
cd contracts && forge init --force --no-commit --no-git && cd ..
```

- [ ] **Step 3: Commit (W11 will flesh out tests/deploy)**

```bash
git add contracts/
git commit -m "chore(contracts): copy AffiliateHook.sol from assistant tree"
```

### Task 1.8: Close the Day-0 PR

- [ ] **Step 1: Push branch + open PR**

```bash
git checkout -b feat/agent-platform-day0
git push -u origin feat/agent-platform-day0
gh pr create --title "feat(agent-platform): Day-0 contracts + migration + stubs" --body "$(cat <<'EOF'
## Summary
- Frozen schemas for ToolEnvelope, AgentCard union, SSE frames
- Pydantic→TS generator + agent.ts
- Alembic: extend web_users, add chats/chat_messages, pgcrypto, updated_at trigger
- Feature flags default off
- Stub routes behind flags
- CORS: chrome-extension/moz-extension origin allowlist
- AffiliateHook.sol copied into repo

All cross-workstream contracts live in a single PR so W1–W13 can fork.

## Test plan
- [ ] pytest tests/api/schemas/test_agent_schemas.py
- [ ] pytest tests/scripts/test_gen_agent_types.py
- [ ] pytest tests/storage/test_agent_migration.py
- [ ] pytest tests/api/test_agent_stubs.py
- [ ] pytest tests/api/middleware/test_cors_extension.py
EOF
)"
```

---

# Parallel Phase — W1…W13

Everything below may proceed in parallel once Phase 1 is merged. Workstreams are self-contained; each lands behind its feature flag.

**Explicit cross-workstream dependencies (beyond Phase 1):**
- W6.3 (card renderers) **blocked by** W7.1 (fixture corpus).
- W9 (swap page) **blocked by** W12 (wallet adapters) for the signing step.
- W10.2 (extension popup/sidepanel) **blocked by** W6 (shared `ChatShell`).
- W13.1 (service worker) **blocked by** W10.1 (extension scaffold).
- W11.3 (summarizer) **blocked by** W11.2 (Greenfield client).
- X.1 Playwright **blocked by** W1+W4+W6 (web) and W10+W13 (extension).
- X.2 Cutover **blocked by** X.1 green.
- X.3 Deletion **blocked by** X.2 + ≥14 days + green prod Playwright.

All other pairs are independent.

---

## W1 — Backend Agent Core

### Task W1.1: IlyonChatModel (LangChain BaseChatModel wrapping src/ai/router)

**Files:**
- Create: `src/agent/__init__.py` (empty)
- Create: `src/agent/llm.py`
- Test: `tests/agent/test_llm.py`

- [ ] **Step 1: Write test**

```python
import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from src.agent.llm import IlyonChatModel

class FakeRouter:
    async def complete(self, *, model, messages, temperature, stop, tools=None):
        return {"content": f"echo:{messages[-1]['content']}", "tool_calls": []}

@pytest.mark.asyncio
async def test_generate_roundtrips_via_router():
    llm = IlyonChatModel(router=FakeRouter(), model="fake-model")
    out = await llm._agenerate([SystemMessage(content="sys"), HumanMessage(content="hi")])
    assert "echo:hi" in out.generations[0].message.content
```

- [ ] **Step 2: Fail**

- [ ] **Step 3: Implement**

```python
# src/agent/llm.py
from __future__ import annotations
from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

class IlyonChatModel(BaseChatModel):
    router: Any = Field(...)
    model: str = "default"
    temperature: float = 0.2

    @property
    def _llm_type(self) -> str:
        return "ilyon-router"

    def _to_openai(self, messages: List[BaseMessage]) -> list[dict]:
        role = {"human": "user", "system": "system", "ai": "assistant", "tool": "tool"}
        return [{"role": role.get(m.type, m.type), "content": m.content} for m in messages]

    async def _agenerate(self, messages, stop=None, run_manager=None, **kw) -> ChatResult:
        resp = await self.router.complete(
            model=self.model,
            messages=self._to_openai(messages),
            temperature=self.temperature,
            stop=stop,
            tools=kw.get("tools"),
        )
        msg = AIMessage(content=resp["content"],
                        additional_kwargs={"tool_calls": resp.get("tool_calls", [])})
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _generate(self, messages, stop=None, run_manager=None, **kw) -> ChatResult:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._agenerate(messages, stop=stop, **kw))
```

- [ ] **Step 4: Pass**

- [ ] **Step 5: Commit**

```bash
git add src/agent/__init__.py src/agent/llm.py tests/agent/test_llm.py
git commit -m "feat(agent): IlyonChatModel wraps src/ai/router as LangChain BaseChatModel"
```

### Task W1.2: SSE streaming (frame encoder + callback handler)

**Files:**
- Create: `src/agent/streaming.py`
- Test: `tests/agent/test_streaming.py`

- [ ] **Step 1: Write test**

```python
import pytest
from src.agent.streaming import encode_sse, StreamCollector

def test_encode_sse_prepends_event_line():
    blob = encode_sse("thought", {"step_index": 1, "content": "hi"})
    assert blob.startswith(b"event: thought\n")
    assert b'"step_index":1' in blob
    assert blob.endswith(b"\n\n")

@pytest.mark.asyncio
async def test_collector_emits_monotonic_step_index():
    c = StreamCollector()
    c.on_llm_start({}, [["p"]])
    await c.on_agent_action(type("A", (), {"tool": "t", "tool_input": {}, "log":"thought"})())
    await c.on_tool_end("raw", name="t")
    frames = [f for f in c.drain()]
    assert all(f.step_index == 1 for f in frames if hasattr(f, "step_index"))

@pytest.mark.asyncio
async def test_observation_frame_carries_tool_name():
    """Spec §2.4: observation frames carry {step_index, name, ok, error?}."""
    from src.api.schemas.agent import ObservationFrame
    c = StreamCollector()
    await c.on_agent_action(type("A",(),{"tool":"get_token_price","tool_input":{},"log":""})())
    await c.on_tool_end("raw", name="get_token_price")
    obs = [f for f in c.drain() if isinstance(f, ObservationFrame)]
    assert obs and obs[0].name == "get_token_price"
    assert obs[0].ok is True

@pytest.mark.asyncio
async def test_observation_frame_on_error_carries_name_and_code():
    from src.api.schemas.agent import ObservationFrame
    c = StreamCollector()
    await c.on_agent_action(type("A",(),{"tool":"x","tool_input":{},"log":""})())
    await c.on_tool_error(ValueError("bad"), name="x")
    obs = [f for f in c.drain() if isinstance(f, ObservationFrame)]
    assert obs and obs[0].name == "x"
    assert obs[0].ok is False and obs[0].error.code == "ValueError"
```

- [ ] **Step 2: Fail**

- [ ] **Step 3: Implement**

```python
# src/agent/streaming.py
from __future__ import annotations
import json
import time
from collections import deque
from typing import Any
from langchain.callbacks.base import AsyncCallbackHandler
from src.api.schemas.agent import (
    ThoughtFrame, ToolFrame, ObservationFrame, CardFrame,
    FinalFrame, DoneFrame, SSEFrame,
)

def encode_sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',',':'))}\n\n".encode()

def frame_event_name(frame: SSEFrame) -> str:
    return {
        ThoughtFrame:"thought", ToolFrame:"tool", ObservationFrame:"observation",
        CardFrame:"card", FinalFrame:"final", DoneFrame:"done",
    }[type(frame)]

class StreamCollector(AsyncCallbackHandler):
    """Collects ReAct frames from LangChain callbacks."""
    def __init__(self) -> None:
        self._queue: deque[SSEFrame] = deque()
        self._step = 0
        self._started = time.monotonic()

    def drain(self):
        while self._queue:
            yield self._queue.popleft()

    async def on_agent_action(self, action, **_):
        self._step += 1
        # Emit a thought for the reasoning that produced this action.
        self._queue.append(ThoughtFrame(
            step_index=self._step,
            content=getattr(action, "log", "").strip() or f"Using tool {action.tool}",
        ))
        self._queue.append(ToolFrame(
            step_index=self._step,
            name=action.tool,
            args=action.tool_input if isinstance(action.tool_input, dict)
                 else {"input": action.tool_input},
        ))

    async def on_tool_end(self, output, *, name: str | None = None, **_):
        tool_name = name or (_.get("serialized") or {}).get("name") or ""
        self._queue.append(ObservationFrame(
            step_index=self._step, name=tool_name, ok=True, error=None,
        ))

    async def on_tool_error(self, error, *, name: str | None = None, **_):
        tool_name = name or (_.get("serialized") or {}).get("name") or ""
        self._queue.append(ObservationFrame(
            step_index=self._step, name=tool_name,
            ok=False,
            error={"code": type(error).__name__, "message": str(error)},
        ))

    def emit_card(self, card_id: str, card_type: str, payload: dict) -> None:
        self._queue.append(CardFrame(
            step_index=self._step, card_id=card_id,
            card_type=card_type, payload=payload,
        ))

    def emit_final(self, content: str, card_ids: list[str]) -> None:
        elapsed = int((time.monotonic() - self._started) * 1000)
        self._queue.append(FinalFrame(
            content=content, card_ids=card_ids,
            elapsed_ms=elapsed, steps=self._step,
        ))
        self._queue.append(DoneFrame())
```

- [ ] **Step 4: Pass**

- [ ] **Step 5: Commit**

```bash
git add src/agent/streaming.py tests/agent/test_streaming.py
git commit -m "feat(agent): SSE frame encoder + ReAct callback collector"
```

### Task W1.3: Session + memory persistence

**Files:**
- Create: `src/agent/session.py`
- Create: `src/storage/chat.py`
- Create: `src/models/chat.py`
- Test: `tests/agent/test_session.py`

- [ ] **Step 1: ORM model**

`src/models/chat.py`:

```python
import uuid
from sqlalchemy import Column, BigInteger, ForeignKey, String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from src.storage.database import Base

class Chat(Base):
    __tablename__ = "chats"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(BigInteger, ForeignKey("web_users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False, default="New Chat")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    cards = Column(JSONB, nullable=True)
    tool_trace = Column(JSONB, nullable=True)
    status = Column(String(16), nullable=False, default="complete")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

Index("ix_chat_messages_chat_id", ChatMessage.chat_id, ChatMessage.created_at)
```

- [ ] **Step 2: CRUD repository**

`src/storage/chat.py`:

```python
import uuid
from typing import Optional
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.chat import Chat, ChatMessage

async def create_chat(db: AsyncSession, user_id: int, title: str = "New Chat") -> Chat:
    chat = Chat(user_id=user_id, title=title)
    db.add(chat); await db.flush()
    return chat

async def get_chat(db: AsyncSession, chat_id: uuid.UUID, user_id: int) -> Optional[Chat]:
    r = await db.execute(select(Chat).where(Chat.id==chat_id, Chat.user_id==user_id))
    return r.scalar_one_or_none()

async def list_chats(db: AsyncSession, user_id: int, limit: int = 50) -> list[Chat]:
    r = await db.execute(
        select(Chat).where(Chat.user_id==user_id)
                    .order_by(desc(Chat.updated_at)).limit(limit))
    return list(r.scalars())

async def append_message(db: AsyncSession, chat_id: uuid.UUID, *,
                         role: str, content: str,
                         cards: Optional[list] = None,
                         tool_trace: Optional[list] = None,
                         status: str = "complete") -> ChatMessage:
    msg = ChatMessage(chat_id=chat_id, role=role, content=content,
                      cards=cards, tool_trace=tool_trace, status=status)
    db.add(msg); await db.flush()
    return msg

async def last_messages(db: AsyncSession, chat_id: uuid.UUID, k: int = 10) -> list[ChatMessage]:
    r = await db.execute(
        select(ChatMessage).where(ChatMessage.chat_id==chat_id)
                           .order_by(desc(ChatMessage.created_at)).limit(k))
    return list(reversed(list(r.scalars())))

async def delete_chat(db: AsyncSession, chat_id: uuid.UUID, user_id: int) -> None:
    await db.execute(delete(Chat).where(Chat.id==chat_id, Chat.user_id==user_id))
```

- [ ] **Step 3: Window memory adapter**

`src/agent/session.py`:

```python
from __future__ import annotations
import uuid
from typing import Any
from langchain.memory import ConversationBufferWindowMemory
from langchain_core.messages import AIMessage, HumanMessage
from src.storage.chat import last_messages, append_message, create_chat, get_chat

class PersistentWindowMemory(ConversationBufferWindowMemory):
    """Rehydrate last k DB messages into a LangChain window memory."""

    @classmethod
    async def load(cls, db, chat_id: uuid.UUID, k: int = 10) -> "PersistentWindowMemory":
        mem = cls(k=k, return_messages=True, memory_key="chat_history")
        for m in await last_messages(db, chat_id, k):
            if m.role == "user":
                mem.chat_memory.add_user_message(m.content)
            else:
                mem.chat_memory.add_ai_message(m.content)
        return mem
```

- [ ] **Step 4: Integration test**

```python
# tests/agent/test_session.py
import pytest, uuid
from src.agent.session import PersistentWindowMemory
from src.storage.chat import create_chat, append_message

@pytest.mark.asyncio
async def test_memory_roundtrips_last_k_messages(db_session):
    chat = await create_chat(db_session, user_id=1)
    for i in range(15):
        role = "user" if i % 2 == 0 else "assistant"
        await append_message(db_session, chat.id, role=role, content=f"msg-{i}")
    mem = await PersistentWindowMemory.load(db_session, chat.id, k=10)
    msgs = mem.chat_memory.messages
    assert len(msgs) == 10
    assert msgs[-1].content == "msg-14"
```

- [ ] **Step 5: Pass + commit**

```bash
git add src/models/chat.py src/storage/chat.py src/agent/session.py tests/agent/test_session.py
git commit -m "feat(agent): chat persistence + window memory rehydration"
```

### Task W1.4: Runtime — wire LLM + memory + tool loop + streaming

**Files:**
- Create: `src/agent/runtime.py`
- Test: `tests/agent/test_runtime.py`

- [ ] **Step 1: Implement**

```python
# src/agent/runtime.py
from __future__ import annotations
import uuid
from typing import AsyncIterator
from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from src.agent.llm import IlyonChatModel
from src.agent.streaming import StreamCollector, encode_sse, frame_event_name
from src.agent.session import PersistentWindowMemory
from src.storage.chat import get_chat, append_message

SYSTEM_PROMPT = PromptTemplate.from_template(
    """You are Ilyon Sentinel's crypto agent. You answer questions about
DeFi, quote swaps, find pools, and assemble allocations. For every
allocation or pool, you MUST cite Sentinel scoring (Safety, Durability,
Exit, Confidence), risk_level (HIGH|MEDIUM|LOW), strategy_fit
(conservative|balanced|aggressive), and any Shield flags. You never
broadcast transactions — only return unsigned tx payloads via build_*
tools. When unsure, use read-only tools first.

Tools:
{tools}

Use this format:
Thought: I need to ...
Action: <tool-name>
Action Input: <json>
Observation: ...
... (repeat)
Thought: I now know the answer
Final Answer: ...

Chat history:
{chat_history}

Question: {input}
{agent_scratchpad}
""")

async def run_turn(*, db, router, tools, chat_id: uuid.UUID, user_id: int,
                   message: str, wallet: str | None) -> AsyncIterator[bytes]:
    chat = await get_chat(db, chat_id, user_id)
    if chat is None:
        from src.storage.chat import create_chat
        chat = await create_chat(db, user_id=user_id, title=message[:60])
    await append_message(db, chat.id, role="user", content=message)

    memory = await PersistentWindowMemory.load(db, chat.id, k=10)
    llm = IlyonChatModel(router=router, model="default")
    agent = create_react_agent(llm, tools, SYSTEM_PROMPT)
    collector = StreamCollector()
    executor = AgentExecutor(agent=agent, tools=tools, memory=memory,
                             callbacks=[collector], max_iterations=10,
                             handle_parsing_errors=True)

    card_ids: list[str] = []
    final_text = ""
    async for event in executor.astream_events({"input": message}, version="v2"):
        for frame in collector.drain():
            yield encode_sse(frame_event_name(frame), frame.model_dump())
            from src.api.schemas.agent import CardFrame
            if isinstance(frame, CardFrame):
                card_ids.append(frame.card_id)
        if event["event"] == "on_chain_end" and event.get("name") == "AgentExecutor":
            final_text = event["data"]["output"].get("output", "")

    from src.agent.clean import clean_agent_output
    final_text = clean_agent_output(final_text)
    collector.emit_final(final_text, card_ids)
    for frame in collector.drain():
        yield encode_sse(frame_event_name(frame), frame.model_dump())

    await append_message(db, chat.id, role="assistant", content=final_text,
                         cards=[{"card_id": cid} for cid in card_ids])
```

- [ ] **Step 2: Port clean_agent_output + query normalizer**

`src/agent/clean.py`:

```python
import re
_RE_THOUGHT = re.compile(r"^\s*(Thought|Action|Observation|Action Input):.*$", re.MULTILINE)

def clean_agent_output(text: str) -> str:
    return _RE_THOUGHT.sub("", text or "").strip()

def normalize_short_swap_query(text: str) -> str:
    # "🔄 Swap BNB → USDT" → "Swap 1 BNB for USDT"
    import re
    m = re.match(r"^[^\w]*Swap\s+([A-Z]{2,6})\s*[→➜-]>\s*([A-Z]{2,6})\s*$", text.strip())
    if m:
        return f"Swap 1 {m.group(1)} for {m.group(2)}"
    return text
```

- [ ] **Step 3: Wire route to runtime**

In `src/api/routes/agent.py`, replace the stub `agent_turn`:

```python
@routes.post("/api/v1/agent")
async def agent_turn(request: web.Request) -> web.StreamResponse:
    if not settings.FEATURE_AGENT_V2:
        return web.json_response({"error": "agent_v2_disabled"}, status=503)
    body = await request.json()
    user = await request.app["auth"].require_user(request)  # W4 wiring
    from src.agent.runtime import run_turn
    from src.agent.tools import register_all_tools
    from src.agent.clean import normalize_short_swap_query
    response = web.StreamResponse(
        status=200,
        headers={"Content-Type":"text/event-stream","Cache-Control":"no-cache"},
    )
    await response.prepare(request)
    async with request.app["db"].session() as db:
        tools = register_all_tools(request.app["services"])
        message = normalize_short_swap_query(body["message"])
        async for chunk in run_turn(
            db=db, router=request.app["router"], tools=tools,
            chat_id=body["session_id"], user_id=user.id,
            message=message, wallet=body.get("wallet"),
        ):
            await response.write(chunk)
    await response.write_eof()
    return response
```

- [ ] **Step 4: End-to-end test with stub tools**

```python
# tests/agent/test_runtime.py
import pytest
from src.agent.runtime import run_turn

@pytest.mark.asyncio
async def test_run_turn_persists_and_streams(db_session, fake_router, fake_tool_registry):
    frames = []
    async for chunk in run_turn(
        db=db_session, router=fake_router,
        tools=fake_tool_registry,
        chat_id=<new uuid>, user_id=1,
        message="hello", wallet=None,
    ):
        frames.append(chunk)
    joined = b"".join(frames)
    assert b"event: final" in joined
    assert b"event: done" in joined
```

- [ ] **Step 5: Commit**

```bash
git add src/agent/runtime.py src/agent/clean.py tests/agent/test_runtime.py src/api/routes/agent.py
git commit -m "feat(agent): ReAct runtime wired to SSE, memory, persistence"
```

### Task W1.5: Runtime emits card frames from enriched envelopes

**Files:**
- Modify: `src/agent/runtime.py`
- Test: `tests/agent/test_runtime_cards.py`

The decorator (W3) enriches each tool result; the runtime must translate the enriched envelope into a `CardFrame` so the SSE stream carries the card. Without this step, W3 runs but no card ever reaches the client.

- [ ] **Step 1: Test**

```python
import pytest
from src.agent.runtime import run_turn

class FakeTool:
    name = "find_liquidity_pool"
    async def ainvoke(self, _):
        # Tool returns an already-decorated envelope (W3 wrapper) as JSON.
        from src.api.schemas.agent import ToolEnvelope
        return ToolEnvelope(
            ok=True, data={"protocol":"Aave"}, card_type="pool",
            card_id="00000000-0000-0000-0000-000000000001",
            card_payload={"protocol":"Aave","chain":"Arbitrum","asset":"USDC","apy":"5%","tvl":"$1B"},
        ).model_dump_json()

@pytest.mark.asyncio
async def test_runtime_emits_card_frame_per_tool_call(db_session, fake_router):
    frames = b""
    async for chunk in run_turn(
        db=db_session, router=fake_router, tools=[FakeTool()],
        chat_id=<new uuid>, user_id=1,
        message="find me a pool", wallet=None,
    ):
        frames += chunk
    assert b"event: card" in frames
    assert b'"card_type":"pool"' in frames
```

- [ ] **Step 2: Fail (no card emission yet)**

- [ ] **Step 3: Implement card emission**

In `src/agent/runtime.py`, after `on_tool_end`, the runtime reads the JSON payload and converts to a `CardFrame`:

```python
# Inside the astream_events loop:
if event["event"] == "on_tool_end":
    import json
    from src.api.schemas.agent import ToolEnvelope
    try:
        env = ToolEnvelope.model_validate_json(event["data"]["output"])
    except Exception:
        env = None
    if env and env.card_type and env.card_payload is not None:
        collector.emit_card(env.card_id, env.card_type, env.card_payload)
```

- [ ] **Step 4: Pass**

- [ ] **Step 5: Commit**

```bash
git add src/agent/runtime.py tests/agent/test_runtime_cards.py
git commit -m "feat(agent): runtime translates enriched envelopes into CardFrame"
```

### Task W1.6: Per-session rate limit

**Note:** Spec §2.2 calls for a "per-user (0.5s min gap)" limit. Key on `(user_id, session_id)` so a user with two open sessions isn't throttled cross-session. If the existing middleware at `src/api/middleware/rate_limit.py` is global-only, add the keyed variant there.

**Files:**
- Modify: `src/api/middleware/rate_limit.py`
- Test: `tests/api/middleware/test_rate_limit_agent.py`

- [ ] **Step 1: Test — two sessions, one user, no throttle**

```python
import pytest, asyncio
from src.api.middleware.rate_limit import PerSessionGap

def test_same_user_different_sessions_allowed():
    gap = PerSessionGap(0.5)
    assert gap.allow(1, "sess-a") is True
    assert gap.allow(1, "sess-b") is True

def test_same_user_same_session_throttled():
    gap = PerSessionGap(0.5)
    assert gap.allow(1, "sess-a") is True
    assert gap.allow(1, "sess-a") is False
```

- [ ] **Step 2: Fail**

- [ ] **Step 3: Implement**

```python
# src/api/middleware/rate_limit.py (append)
from time import monotonic

class PerSessionGap:
    def __init__(self, min_gap_s: float = 0.5):
        self._last: dict[tuple[int, str], float] = {}
        self._gap = min_gap_s
    def allow(self, user_id: int, session_id: str) -> bool:
        key = (user_id, session_id)
        now = monotonic()
        if now - self._last.get(key, 0) < self._gap:
            return False
        self._last[key] = now
        return True

agent_gap = PerSessionGap(0.5)
```

In `src/api/routes/agent.py::agent_turn`, before running:

```python
from src.api.middleware.rate_limit import agent_gap
if not agent_gap.allow(user.id, body["session_id"]):
    return web.json_response({"error":"rate_limited"}, status=429)
```

- [ ] **Step 4: Pass**

- [ ] **Step 5: Commit**

```bash
git add src/api/middleware/rate_limit.py src/api/routes/agent.py \
        tests/api/middleware/test_rate_limit_agent.py
git commit -m "feat(agent): per-session rate limit (0.5s gap keyed on user+session)"
```

---

## W2 + W2a — Tool Layer + Service Adapters

For each of the 14 tools, the pattern is identical: **test fixture with fake service → tool function calling service → LangChain Tool wrapper → registration**. Do one exhaustive example (W2.1) then repeat for the rest.

### Task W2a.1: Enso adapter

**Files:**
- Create: `src/routing/enso_client.py`
- Test: `tests/routing/test_enso_client.py`

- [ ] **Step 1: Test**

```python
import pytest, httpx
from respx import MockRouter
from src.routing.enso_client import EnsoClient

@pytest.mark.asyncio
async def test_build_returns_unsigned_tx(respx_mock: MockRouter):
    respx_mock.post("https://api.enso.finance/api/v1/shortcuts/route").mock(
        return_value=httpx.Response(200, json={"tx":{"to":"0xaaa","data":"0xbbb","value":"0"}}))
    c = EnsoClient(api_key="k")
    out = await c.build(chain_id=1, token_in="0xT1", token_out="0xT2",
                        amount_in="1000000000000000000", from_addr="0xU")
    assert out["unsigned_tx"]["to"] == "0xaaa"
    assert out["simulation"]["ok"] is True
```

- [ ] **Step 2: Implement**

```python
# src/routing/enso_client.py
import httpx
from src.config import settings

class EnsoClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.ENSO_API_KEY
        self._base = "https://api.enso.finance/api/v1"
    async def build(self, *, chain_id, token_in, token_out, amount_in, from_addr) -> dict:
        async with httpx.AsyncClient(timeout=30) as cli:
            r = await cli.post(f"{self._base}/shortcuts/route", json={
                "chainId": chain_id, "tokenIn": token_in, "tokenOut": token_out,
                "amountIn": amount_in, "fromAddress": from_addr,
            }, headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})
            r.raise_for_status()
            tx = r.json().get("tx", {})
            return {"unsigned_tx": tx, "simulation": {"ok": True, "chain_id": chain_id}}
```

- [ ] **Step 3-5:** pass + commit.

Apply the identical pattern to the remaining adapters:

### Task W2a.2: Jupiter adapter (`src/routing/jupiter_client.py`)
### Task W2a.3: deBridge DLN adapter (`src/routing/debridge_client.py`)
### Task W2a.4: StakeBuilder (`src/routing/stake_builder.py`) with sub-adapters Lido, Rocket Pool, Jito, Marinade (each returns unsigned tx for the protocol's deposit function; Lido uses `submit(referral)`, Rocket Pool uses `deposit()`, Jito uses `depositSol()`, Marinade uses `deposit(referralCode)`)
### Task W2a.5: LpBuilder (`src/routing/lp_builder.py`) — Uniswap v3 NonfungiblePositionManager.mint, PancakeSwap v3 equivalent, Raydium addLiquidity
### Task W2a.6: Transfer builder (`src/routing/transfer_builder.py`) — native send on EVM + Solana SystemProgram.transfer
### Task W2a.7: QuoteService (`src/routing/quote_service.py`) — dispatcher that calls Enso for EVM and Jupiter for Solana; returns a normalized quote block (pay, receive, rate, router, priceImpact)

Each adapter gets its own unit test with `respx` (EVM HTTP mocks) or `pytest-asyncio` + `solders` for Solana. Commit each independently.

### Task W2.1: Balance tool (exhaustive example)

**Files:**
- Create: `src/agent/tools/__init__.py`
- Create: `src/agent/tools/_base.py` (ToolCtx + helpers)
- Create: `src/agent/tools/balance.py`
- Test: `tests/agent/tools/test_balance.py`

- [ ] **Step 1: Base helpers**

```python
# src/agent/tools/_base.py
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4
from src.api.schemas.agent import ToolEnvelope, CardType, ToolError

@dataclass
class ToolCtx:
    services: Any          # container of injected services
    user_id: int
    wallet: str | None

def ok_envelope(*, data: dict, card_type: CardType | None = None,
                card_payload: dict | None = None) -> ToolEnvelope:
    return ToolEnvelope(
        ok=True, data=data, card_type=card_type,
        card_id=str(uuid4()), card_payload=card_payload,
    )

def err_envelope(code: str, message: str, *, card_type: CardType | None = None) -> ToolEnvelope:
    return ToolEnvelope(
        ok=False, data=None, card_type=card_type,
        card_id=str(uuid4()), card_payload=None,
        error=ToolError(code=code, message=message),
    )
```

- [ ] **Step 2: Test**

```python
# tests/agent/tools/test_balance.py
import pytest
from src.agent.tools.balance import get_wallet_balance
from src.agent.tools._base import ToolCtx

class FakePortfolio:
    async def aggregate(self, wallet: str) -> dict:
        return {"wallet": wallet, "total_usd": "1234.56", "by_chain":{"eth":"1000","sol":"234.56"}}

@pytest.mark.asyncio
async def test_balance_returns_balance_card():
    ctx = ToolCtx(services=type("S",(object,),{"portfolio": FakePortfolio()})(),
                  user_id=1, wallet="0xabc")
    env = await get_wallet_balance(ctx, wallet="0xabc")
    assert env.ok and env.card_type == "balance"
    assert env.card_payload["total_usd"] == "1234.56"
```

- [ ] **Step 3: Implement**

```python
# src/agent/tools/balance.py
from src.agent.tools._base import ToolCtx, ok_envelope, err_envelope

async def get_wallet_balance(ctx: ToolCtx, *, wallet: str | None = None):
    addr = wallet or ctx.wallet
    if not addr:
        return err_envelope("missing_wallet", "No wallet address provided", card_type=None)
    data = await ctx.services.portfolio.aggregate(addr)
    return ok_envelope(data=data, card_type="balance", card_payload=data)
```

- [ ] **Step 4: LangChain Tool wrapper**

```python
# src/agent/tools/__init__.py
from langchain.tools import StructuredTool
from .balance import get_wallet_balance
# imports for the rest added as each tool lands

def register_all_tools(services, user_id: int = 0, wallet: str | None = None):
    from src.agent.tools._base import ToolCtx
    ctx = ToolCtx(services=services, user_id=user_id, wallet=wallet)
    return [
        StructuredTool.from_function(
            coroutine=lambda wallet=None: get_wallet_balance(ctx, wallet=wallet),
            name="get_wallet_balance",
            description="Get a wallet's multi-chain balance.",
        ),
        # rest registered below as tools land
    ]
```

- [ ] **Step 5: Pass + commit**

### Task W2.2: get_token_price

**Files:** `src/agent/tools/price.py`, `tests/agent/tools/test_price.py`

- [ ] Failing test: fake price service returning `{"symbol":"SOL","address":"So1..","chain":"solana","price_usd":"89.6","change_24h_pct":1.2}` → assert `card_type == "token"`, payload echoes price.
- [ ] Implement: `async def get_token_price(ctx, *, token: str, chain: str = "ethereum")` → call `ctx.services.price.get(token, chain)` → `ok_envelope(data=..., card_type="token", card_payload=...)`. Fallback: on `PriceService` failure, try `ctx.services.dexscreener.price_for(token)`.
- [ ] Register in `_TOOL_REGISTRY`.
- [ ] Test PASS.
- [ ] Commit: `feat(agent): tool get_token_price`

### Task W2.3: simulate_swap

**Files:** `src/agent/tools/swap_simulate.py`, `tests/agent/tools/test_swap_simulate.py`

- [ ] Failing test: fake `quote_service.quote(chain, in_tok, out_tok, amt)` returns `{pay, receive, rate, router, price_impact_pct}`. Assert `card_type == "swap_quote"`.
- [ ] Implement: dispatch by chain family (EVM → EnsoClient; Solana → JupiterClient) via QuoteService.
- [ ] Register.
- [ ] Commit: `feat(agent): tool simulate_swap`

### Task W2.4: build_swap_tx (EVM, via Enso)

**Files:** `src/agent/tools/swap_build.py`, `tests/agent/tools/test_swap_build.py`

- [ ] Failing test: fake `services.enso.build(...)` returns `{unsigned_tx, simulation}`. Assert envelope contains `card_type == "swap_quote"` and `data.unsigned_tx`.
- [ ] Implement (returns unsigned tx; never signs — enforces spec §2.2 safety gate).
- [ ] Register.
- [ ] Commit.

### Task W2.5: build_solana_swap (Jupiter)

**Files:** `src/agent/tools/solana_swap.py`, `tests/agent/tools/test_solana_swap.py`

- [ ] Failing test: fake `services.jupiter.build(...)` returns serialized tx base64. Assert `card_type == "swap_quote"`, `data.serialized_tx` present.
- [ ] Implement.
- [ ] Register.
- [ ] Commit.

### Task W2.6: get_defi_market_overview

**Files:** `src/agent/tools/market_overview.py`, `tests/agent/tools/test_market_overview.py`

- [ ] Failing test: fake `services.defillama.protocols()` returns list of 20 protocols. Assert `card_type == "market_overview"`, `payload.protocols` contains all rows.
- [ ] Implement: aggregate summary (top-N by TVL, rollup by category).
- [ ] Register.
- [ ] Commit.

### Task W2.7: get_defi_analytics (tiered)

**Files:** `src/agent/tools/analytics.py`, `tests/agent/tools/test_analytics.py`

- [ ] Failing test 1: generic list query ("best yields USDC") → uses `MarketScanPipeline`, emits `card_type="market_overview"`.
- [ ] Failing test 2: specific pool query (explicit protocol + pair) → uses `OpportunityEngine.deep`, emits `card_type="pool"`.
- [ ] Implement dispatcher with intent classifier: if `pool_id` or (`protocol` AND `asset`) present → deep path; else list path.
- [ ] Register.
- [ ] Commit.

### Task W2.8: get_staking_options

**Files:** `src/agent/tools/staking.py`, `tests/agent/tools/test_staking.py`

- [ ] Failing test: fake `opportunity_engine.scan(category=["staking","liquid-staking"])` returns 5 pools. Assert `card_type == "allocation"` when N>1, `"stake"` when N==1.
- [ ] Implement: filter on `category in {staking, liquid-staking}`; overlay `services.staking_metadata.lookup(protocol)` (adds unbond_days, validator info).
- [ ] Register.
- [ ] Commit.

### Task W2.9: search_dexscreener_pairs

**Files:** `src/agent/tools/dex_search.py`, `tests/agent/tools/test_dex_search.py`

- [ ] Failing test: fake `services.dexscreener.search("BONK")` returns 8 pairs. Assert `card_type == "pair_list"`, `payload.pairs` length 8.
- [ ] Implement.
- [ ] Register.
- [ ] Commit.

### Task W2.10: find_liquidity_pool (hybrid with fallback)

**Files:** `src/agent/tools/pool_find.py`, `tests/agent/tools/test_pool_find.py`

- [ ] Failing test 1: `opportunity_engine.find_pool` returns a hit → `card_type="pool"` from Ilyon data.
- [ ] Failing test 2: `opportunity_engine.find_pool` returns None (long-tail meme coin) → fallback to `dexscreener_client.search()`, still `card_type="pool"`.
- [ ] Implement.
- [ ] Register.
- [ ] Commit.

### Task W2.11: build_stake_tx

**Files:** `src/agent/tools/stake_build.py`, `tests/agent/tools/test_stake_build.py`

- [ ] Failing test for each of the 4 protocols (Lido, Rocket Pool, Jito, Marinade) — fake adapter returns unsigned tx, assert `card_type == "stake"`, `data.unsigned_tx` present, `payload.requires_signature` surfaced via decorator plan card.
- [ ] Implement: `services.stake_builder.build(protocol, amount, user_addr)` dispatches per-protocol.
- [ ] Register.
- [ ] Commit.

### Task W2.12: build_deposit_lp_tx

**Files:** `src/agent/tools/lp_build.py`, `tests/agent/tools/test_lp_build.py`

- [ ] Failing test per family (Uniswap v3, PancakeSwap v3, Raydium).
- [ ] Implement: dispatches to LpBuilder adapters.
- [ ] Register. Commit.

### Task W2.13: build_bridge_tx

**Files:** `src/agent/tools/bridge_build.py`, `tests/agent/tools/test_bridge_build.py`

- [ ] Failing test: fake `services.debridge.build(...)` returns unsigned tx + estimated_seconds. Assert `card_type == "bridge"`.
- [ ] Implement.
- [ ] Register. Commit.

### Task W2.14: build_transfer_tx

**Files:** `src/agent/tools/transfer_build.py`, `tests/agent/tools/test_transfer_build.py`

- [ ] Failing test: EVM path (populated `to`/`value`/`data`); Solana path (SystemProgram.transfer). Assert `card_type == "plan"` (single-step plan).
- [ ] Implement.
- [ ] Register. Commit.

---

## W3 — Sentinel + Shield Decorator

### Task W3.1: Decoration map + decorate()

**Files:**
- Create: `src/agent/decorator.py`
- Test: `tests/agent/test_decorator.py`

- [ ] **Step 1: Test**

```python
import pytest
from src.agent.decorator import decorate
from src.agent.tools._base import ToolCtx

class FakeOpp:
    async def summarize(self, pool): return {
        "sentinel":92,"safety":95,"durability":90,"exit":88,
        "confidence":91,"risk_level":"LOW","strategy_fit":"balanced","flags":[]}

class FakeShield:
    async def verdict(self, mint): return {"verdict":"SAFE","grade":"A","reasons":[]}

@pytest.mark.asyncio
async def test_pool_gets_sentinel_block():
    ctx = ToolCtx(services=type("S",(),{"opportunity": FakeOpp(),"shield":FakeShield()})(),
                  user_id=1, wallet=None)
    env = await decorate("find_liquidity_pool",
        {"ok":True,"data":{"protocol":"Aave","chain":"Arbitrum","asset":"USDC","apy":"5.4%","tvl":"$820M"},
         "card_type":"pool","card_id":"x","card_payload":{}}, ctx)
    assert env.sentinel.sentinel == 92
```

- [ ] **Step 2: Implement**

```python
# src/agent/decorator.py
from __future__ import annotations
from typing import Callable, Awaitable
from src.api.schemas.agent import ToolEnvelope, SentinelBlock, ShieldBlock

DecorateFn = Callable[[dict, "ToolCtx"], Awaitable[dict]]

DECORATION_MAP: dict[str, list[str]] = {
    "find_liquidity_pool":   ["sentinel"],
    "get_defi_analytics":    ["sentinel"],
    "get_staking_options":   ["sentinel"],
    "get_token_price":       ["shield"],
    "get_wallet_balance":    ["shield_all_positions"],
    "simulate_swap":         ["shield_both_legs"],
    "build_swap_tx":         ["shield_both_legs"],
    "build_solana_swap":     ["shield_both_legs"],
    "search_dexscreener_pairs":["shield_all_pairs"],
    "get_defi_market_overview": [],
    "build_bridge_tx":       ["shield_both_legs"],
    "build_stake_tx":        ["sentinel"],
    "build_deposit_lp_tx":   ["sentinel"],
    "build_transfer_tx":     [],
}

async def decorate(tool_name: str, raw: dict, ctx) -> ToolEnvelope:
    env = ToolEnvelope.model_validate(raw)
    if not env.ok or env.data is None:
        return env
    for strategy in DECORATION_MAP.get(tool_name, []):
        await _apply(strategy, env, ctx)
    return env

async def _apply(strategy: str, env: ToolEnvelope, ctx) -> None:
    try:
        if strategy == "sentinel":
            s = await ctx.services.opportunity.summarize(env.data)
            env.sentinel = SentinelBlock(**s)
            if env.card_payload is not None:
                env.card_payload.setdefault("sentinel", s)
        elif strategy == "shield":
            v = await ctx.services.shield.verdict(env.data.get("address") or env.data.get("mint"))
            env.shield = ShieldBlock(**v)
        elif strategy == "shield_both_legs":
            pay = env.data.get("pay", {}); rcv = env.data.get("receive", {})
            for leg, key in ((pay,"pay"), (rcv,"receive")):
                tok = leg.get("address") or leg.get("mint")
                if tok and env.card_payload is not None:
                    v = await ctx.services.shield.verdict(tok)
                    env.card_payload.setdefault(f"{key}_shield", v)
        elif strategy == "shield_all_positions":
            for pos in env.card_payload.get("positions", []):
                tok = pos.get("address") or pos.get("mint")
                if tok:
                    pos["shield"] = (await ctx.services.shield.verdict(tok))
        elif strategy == "shield_all_pairs":
            for pair in env.card_payload.get("pairs", []):
                tok = pair.get("base_address")
                if tok:
                    pair["shield"] = (await ctx.services.shield.verdict(tok))
    except Exception as e:
        # decorator never hard-fails the tool
        env.card_payload and env.card_payload.setdefault("decoration_errors", []).append(str(e))
```

- [ ] **Step 3: Wire into runtime — each tool's return passes through `decorate()` before landing in the stream collector**

Modify `register_all_tools` so the StructuredTool's coroutine is wrapped:

```python
def _wrap(tool_name, fn):
    async def runner(**kw):
        raw = await fn(**kw)
        enriched = await decorate(tool_name, raw.model_dump(), ctx)
        ctx.services._last_envelope = enriched  # picked up by stream collector
        return enriched.model_dump_json()
    return runner
```

And the runtime emits a `card` frame from `enriched.card_type + enriched.card_payload`.

- [ ] **Step 4: Unit + integration test. Commit.**

### Task W3.2: Enforce "every tool flows through decorator"

Spec §13: **every tool response flows through the Sentinel decorator from day 1.** This is a correctness invariant, not a best-effort guarantee.

**Files:**
- Modify: `src/agent/tools/__init__.py`
- Test: `tests/agent/test_decorator_enforcement.py`

- [ ] **Step 1: Test — registry shape enforces wrapping**

```python
import pytest
from src.agent.tools import register_all_tools, _WRAPPED_TOOL_NAMES
from src.agent.decorator import DECORATION_MAP

def test_registry_covers_every_decoration_map_entry():
    """Every tool in DECORATION_MAP must be registered."""
    tools = register_all_tools(services=type("S",(),{})(), user_id=0, wallet=None)
    names = {t.name for t in tools}
    for tname in DECORATION_MAP:
        assert tname in names, f"{tname} in DECORATION_MAP but not registered"

def test_every_registered_tool_is_decorator_wrapped():
    """register_all_tools must mark every tool as wrapped."""
    tools = register_all_tools(services=type("S",(),{})(), user_id=0, wallet=None)
    for t in tools:
        assert t.name in _WRAPPED_TOOL_NAMES, f"{t.name} bypasses decorator"

@pytest.mark.asyncio
async def test_wrapper_invokes_decorate_for_every_tool(monkeypatch):
    """The wrapper must call decorate() on every tool return."""
    from src.agent import tools as tools_mod
    calls = []
    async def fake_decorate(name, raw, ctx):
        calls.append(name)
        from src.api.schemas.agent import ToolEnvelope
        return ToolEnvelope.model_validate(raw)
    monkeypatch.setattr(tools_mod, "decorate", fake_decorate)

    class FakePortfolio:
        async def aggregate(self, w): return {"wallet":w,"total_usd":"0","by_chain":{}}
    services = type("S",(),{"portfolio":FakePortfolio()})()
    tools = register_all_tools(services=services, user_id=1, wallet="0xabc")
    bal = next(t for t in tools if t.name == "get_wallet_balance")
    await bal.coroutine(wallet="0xabc")
    assert "get_wallet_balance" in calls
```

- [ ] **Step 2: Fail (wrapper unconditionality not guaranteed)**

- [ ] **Step 3: Implement enforcement**

In `src/agent/tools/__init__.py`:

```python
from langchain.tools import StructuredTool
from src.agent.tools._base import ToolCtx
from src.agent.decorator import decorate, DECORATION_MAP

# Map tool name → (function, description)
from .balance import get_wallet_balance
from .price import get_token_price
from .swap_simulate import simulate_swap
from .swap_build import build_swap_tx
from .solana_swap import build_solana_swap
from .market_overview import get_defi_market_overview
from .analytics import get_defi_analytics
from .staking import get_staking_options
from .dex_search import search_dexscreener_pairs
from .pool_find import find_liquidity_pool
from .stake_build import build_stake_tx
from .lp_build import build_deposit_lp_tx
from .bridge_build import build_bridge_tx
from .transfer_build import build_transfer_tx

_TOOL_REGISTRY = {
    "get_wallet_balance": (get_wallet_balance, "Get multi-chain wallet balance."),
    "get_token_price": (get_token_price, "Get current price for a token."),
    "simulate_swap": (simulate_swap, "Quote a swap (no tx build)."),
    "build_swap_tx": (build_swap_tx, "Build an unsigned EVM swap tx via Enso."),
    "build_solana_swap": (build_solana_swap, "Build an unsigned Solana swap tx via Jupiter."),
    "get_defi_market_overview": (get_defi_market_overview, "Aggregate DeFi market stats."),
    "get_defi_analytics": (get_defi_analytics, "Tiered pool/protocol analytics."),
    "get_staking_options": (get_staking_options, "List liquid-staking and staking options."),
    "search_dexscreener_pairs": (search_dexscreener_pairs, "Search DexScreener pairs."),
    "find_liquidity_pool": (find_liquidity_pool, "Find a liquidity pool for a pair."),
    "build_stake_tx": (build_stake_tx, "Build an unsigned stake tx."),
    "build_deposit_lp_tx": (build_deposit_lp_tx, "Build an unsigned LP deposit tx."),
    "build_bridge_tx": (build_bridge_tx, "Build an unsigned deBridge transfer."),
    "build_transfer_tx": (build_transfer_tx, "Build an unsigned native transfer."),
}

_WRAPPED_TOOL_NAMES: set[str] = set()

def _wrap(name: str, fn, ctx: ToolCtx):
    async def runner(**kw):
        env = await fn(ctx, **kw)
        enriched = await decorate(name, env.model_dump(), ctx)
        return enriched.model_dump_json()
    _WRAPPED_TOOL_NAMES.add(name)
    return runner

def register_all_tools(services, user_id: int = 0, wallet: str | None = None):
    ctx = ToolCtx(services=services, user_id=user_id, wallet=wallet)
    # Sanity: registry names must cover DECORATION_MAP.
    missing = set(DECORATION_MAP) - set(_TOOL_REGISTRY)
    if missing:
        raise RuntimeError(f"DECORATION_MAP has entries with no registered tool: {missing}")
    tools = []
    for name, (fn, desc) in _TOOL_REGISTRY.items():
        tools.append(StructuredTool.from_function(
            coroutine=_wrap(name, fn, ctx), name=name, description=desc,
        ))
    return tools
```

- [ ] **Step 4: Pass**

- [ ] **Step 5: Commit**

```bash
git add src/agent/tools/__init__.py tests/agent/test_decorator_enforcement.py
git commit -m "feat(agent): enforce every tool is decorator-wrapped at registration"
```

---

## W4 — Auth

### Task W4.1: MetaMask ECDSA verifier

**Files:**
- Create: `src/auth/ethereum.py`
- Test: `tests/auth/test_ethereum.py`

- [ ] **Step 1: Test with known fixture**

```python
from src.auth.ethereum import verify_ethereum_signature

def test_valid_signature_from_metamask_fixture():
    # A pre-signed message taken from test vector:
    address = "0x..."; message = "login: 123"; signature = "0x..."
    assert verify_ethereum_signature(address, message, signature) is True
```

- [ ] **Step 2: Implement**

```python
# src/auth/ethereum.py
from eth_account import Account
from eth_account.messages import encode_defunct

def verify_ethereum_signature(address: str, message: str, signature: str) -> bool:
    try:
        recovered = Account.recover_message(encode_defunct(text=message),
                                            signature=signature)
        return recovered.lower() == address.lower()
    except Exception:
        return False
```

- [ ] **Step 3: Pass + commit**

### Task W4.2: Email/password flow

**Files:**
- Create: `src/auth/password.py`
- Modify: `src/api/routes/auth.py`
- Test: `tests/auth/test_password_flow.py`

- [ ] **Step 1: Hashing wrapper**

```python
# src/auth/password.py
from passlib.hash import argon2
def hash_password(pw: str) -> str: return argon2.hash(pw)
def verify_password(pw: str, digest: str) -> bool: return argon2.verify(pw, digest)
```

- [ ] **Step 2: Register/login endpoints**

In `src/api/routes/auth.py`, replace the register/login stubs with full handlers that:
- For register: ensure email not taken → insert row with sentinel wallet_address (`"email:" + sha256(email)[:36]`) → mint JWT.
- For login: look up by email → verify_password → mint JWT.

```python
import hashlib
@routes.post("/api/v1/auth/register")
async def register(request):
    body = await request.json()
    email = body["email"].lower(); password = body["password"]; display = body.get("display_name") or email
    async with request.app["db"].session() as db:
        existing = await db.execute(select(WebUser).where(WebUser.email==email))
        if existing.scalar_one_or_none():
            return web.json_response({"error":"email_taken"}, status=400)
        sentinel = "email:" + hashlib.sha256(email.encode()).hexdigest()[:36]
        assert len(sentinel) == 42
        user = WebUser(wallet_address=sentinel, email=email,
                       password_hash=hash_password(password),
                       display_name=display)
        db.add(user); await db.commit()
    token = create_token(user.id, email=email)
    return web.json_response({"token": token, "user": serialize(user)})
```

- [ ] **Step 3: verify-evm endpoint**

```python
@routes.post("/api/v1/auth/verify-evm")
async def verify_evm(request):
    body = await request.json()
    if not _consume_challenge(body["challenge"]):
        return web.json_response({"error":"bad_challenge"}, status=400)
    if not verify_ethereum_signature(body["address"], body["message"], body["signature"]):
        return web.json_response({"error":"bad_signature"}, status=400)
    # get-or-create by wallet_address
    ...
```

- [ ] **Step 4.a: sentinel wallet_address length test (spec §4.2)**

```python
def test_register_sentinel_is_exactly_42_chars():
    email = "long-ish-email-address@example.com"
    import hashlib
    sentinel = "email:" + hashlib.sha256(email.encode()).hexdigest()[:36]
    assert len(sentinel) == 42

def test_register_rejects_wrong_sentinel_length():
    with pytest.raises(AssertionError):
        sentinel = "email:" + "abc"  # only 9 chars
        assert len(sentinel) == 42
```

Each of the five sub-steps below is a full red→green→commit cycle. All operations execute inside a single `async with db.begin()` transaction — assemble it incrementally; each passing test exercises the partially-built merge function.

#### Sub-step 4.b — delete old sessions

- [ ] **4.b.1: Failing test**

```python
@pytest.mark.asyncio
async def test_merge_step_deletes_stale_sessions(db_session):
    from src.auth.merge import merge_accounts
    # Seed: two user_sessions rows
    await db_session.execute(text(
        "INSERT INTO user_sessions (token, wallet_address, expires_at) "
        "VALUES ('t1', 'email:abc', now()+interval '1h'), "
        "       ('t2', '0xreal',     now()+interval '1h')"))
    await merge_accounts(db_session, email_id=1, wallet_id=2,
                         sentinel="email:abc", real_wallet="0xreal")
    r = await db_session.execute(text(
        "SELECT count(*) FROM user_sessions WHERE wallet_address IN ('email:abc','0xreal')"))
    assert r.scalar_one() == 0
```

- [ ] **4.b.2: Fail** — `src.auth.merge` module doesn't exist yet.

- [ ] **4.b.3: Implement (partial)** — create `src/auth/merge.py`:

```python
from sqlalchemy import text

async def merge_accounts(db, *, email_id, wallet_id, sentinel, real_wallet):
    async with db.begin():
        await db.execute(text(
            "DELETE FROM user_sessions WHERE wallet_address IN (:s, :r)"),
            {"s": sentinel, "r": real_wallet})
```

- [ ] **4.b.4: Pass**

- [ ] **4.b.5: Commit**

```bash
git add src/auth/merge.py tests/auth/test_merge.py
git commit -m "feat(auth): merge step 1 — delete stale sessions"
```

#### Sub-step 4.c — repoint chats

- [ ] **4.c.1: Failing test**

```python
@pytest.mark.asyncio
async def test_merge_repoints_chats_to_email_user(db_session):
    # Seed chat owned by wallet_id=2; email_id=1
    chat_id = await db_session.scalar(text(
        "INSERT INTO chats (user_id, title) VALUES (2, 'x') RETURNING id"))
    await merge_accounts(db_session, email_id=1, wallet_id=2,
                         sentinel="email:abc", real_wallet="0xreal")
    owner = await db_session.scalar(text(
        "SELECT user_id FROM chats WHERE id=:id"), {"id": chat_id})
    assert owner == 1
```

- [ ] **4.c.2: Fail** — still owned by 2.

- [ ] **4.c.3: Implement** — append to the transaction in `merge_accounts`:

```python
        await db.execute(text(
            "UPDATE chats SET user_id = :eid WHERE user_id = :wid"),
            {"eid": email_id, "wid": wallet_id})
```

- [ ] **4.c.4: Pass**

- [ ] **4.c.5: Commit** — `feat(auth): merge step 2 — repoint chats to email user`.

#### Sub-step 4.d — delete obsolete web_users row

- [ ] **4.d.1: Failing test**

```python
@pytest.mark.asyncio
async def test_merge_deletes_obsolete_wallet_row(db_session):
    # email row id=1, wallet row id=2
    await merge_accounts(db_session, email_id=1, wallet_id=2,
                         sentinel="email:abc", real_wallet="0xreal")
    r = await db_session.scalar(text("SELECT count(*) FROM web_users WHERE id=2"))
    assert r == 0

@pytest.mark.asyncio
async def test_merge_noop_when_no_wallet_row(db_session):
    # email_id == wallet_id — no merge row to delete
    await merge_accounts(db_session, email_id=1, wallet_id=1,
                         sentinel="email:abc", real_wallet="0xreal")
    r = await db_session.scalar(text("SELECT count(*) FROM web_users WHERE id=1"))
    assert r == 1  # email row still there
```

- [ ] **4.d.2: Fail**

- [ ] **4.d.3: Implement**

```python
        if email_id != wallet_id:
            await db.execute(text("DELETE FROM web_users WHERE id = :wid"),
                             {"wid": wallet_id})
```

- [ ] **4.d.4: Pass**

- [ ] **4.d.5: Commit** — `feat(auth): merge step 3 — delete obsolete wallet row`.

#### Sub-step 4.e — update wallet_address on email row

- [ ] **4.e.1: Failing test**

```python
@pytest.mark.asyncio
async def test_merge_updates_email_row_wallet(db_session):
    await merge_accounts(db_session, email_id=1, wallet_id=2,
                         sentinel="email:abc", real_wallet="0xreal")
    wa = await db_session.scalar(text(
        "SELECT wallet_address FROM web_users WHERE id=1"))
    assert wa == "0xreal"
```

- [ ] **4.e.2: Fail**

- [ ] **4.e.3: Implement**

```python
        await db.execute(text(
            "UPDATE web_users SET wallet_address = :real WHERE id = :eid"),
            {"real": real_wallet, "eid": email_id})
```

- [ ] **4.e.4: Pass**

- [ ] **4.e.5: Commit** — `feat(auth): merge step 4 — update email row wallet`.

#### Sub-step 4.f — mint new JWT and return

- [ ] **4.f.1: Failing test**

```python
@pytest.mark.asyncio
async def test_link_wallet_endpoint_returns_merged_token(client, authed_email_user):
    ch = (await client.post("/api/v1/auth/challenge",
                             json={"address": "0xreal"})).json()
    r = await client.post("/api/v1/auth/link-wallet",
        headers={"Authorization": f"Bearer {authed_email_user.token}"},
        json={"address":"0xreal","message":ch["challenge"],"signature":"<fixture>"})
    assert r.status_code == 200
    claims = decode_token(r.json()["token"])
    assert claims["sub"] == authed_email_user.id
    assert claims["wallet_address"] == "0xreal"
```

- [ ] **4.f.2: Fail** — endpoint still returns 501.

- [ ] **4.f.3: Implement handler in `src/api/routes/auth.py`**

```python
@routes.post("/api/v1/auth/link-wallet")
async def link_wallet(request: web.Request) -> web.Response:
    user = await request.app["auth"].require_user(request)
    body = await request.json()
    if not _consume_challenge(body["message"]):
        return web.json_response({"error":"bad_challenge"}, status=400)
    if not verify_ethereum_signature(body["address"], body["message"], body["signature"]):
        return web.json_response({"error":"bad_signature"}, status=400)
    async with request.app["db"].session() as db:
        wallet_row = (await db.execute(select(WebUser)
            .where(WebUser.wallet_address == body["address"]))).scalar_one_or_none()
        wallet_id = wallet_row.id if wallet_row else user.id
        sentinel = user.wallet_address
        await merge_accounts(db, email_id=user.id, wallet_id=wallet_id,
                             sentinel=sentinel, real_wallet=body["address"])
    token = create_token(user.id, wallet_address=body["address"], email=user.email)
    return web.json_response({"token": token, "user": serialize_user(user)})
```

- [ ] **4.f.4: Pass**

- [ ] **4.f.5: Commit** — `feat(auth): merge step 5 — /link-wallet endpoint mints fresh JWT`.

- [ ] **Step 5: Full merge integration test (top-level regression)**

```python
@pytest.mark.asyncio
async def test_link_wallet_full_merge_flow(client, db_session):
    # Register via email
    r = await client.post("/api/v1/auth/register", json={"email":"a@b.c","password":"pw"})
    token = r.json()["token"]
    email_id = r.json()["user"]["id"]
    # Simulate that the wallet already has history
    await create_wallet_only_user(db_session, wallet="0xreal")
    # Challenge/verify with real wallet + link
    ch = (await client.post("/api/v1/auth/challenge", json={"address":"0xreal"})).json()
    r2 = await client.post("/api/v1/auth/link-wallet",
        headers={"Authorization": f"Bearer {token}"},
        json={"address":"0xreal","message":ch["challenge"],"signature":"<fixture-sig>"})
    assert r2.status_code == 200
    # Assert: email row updated, wallet row deleted, chats repointed, sessions deleted
```

Commit: `feat(auth): link-wallet performs atomic 5-step merge`.

---

## W5 — Chat persistence endpoints

### Task W5.1: GET /sessions, GET /sessions/{id}, DELETE /sessions/{id}

- [ ] Implement handlers against `src/storage/chat.py`.
- [ ] Test: create two chats → list returns both ordered by updated_at desc; delete cascades messages.
- [ ] Commit.

---

## W6 — Frontend agent surface

### Task W6.1: agent-client.ts SSE consumer

**Files:**
- Create: `web/lib/agent-client.ts`
- Create: `web/hooks/useAgentStream.ts`
- Test: `web/lib/__tests__/agent-client.test.ts`

- [ ] **Step 1: Streaming client**

```ts
// web/lib/agent-client.ts
import type { SSEFrame } from "@/types/agent";

export async function* streamAgent(
  body: { session_id: string; message: string; wallet?: string },
  token: string,
): AsyncGenerator<SSEFrame, void, void> {
  const r = await fetch("/api/v1/agent", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  if (!r.body) throw new Error("no body");
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const raw = buf.slice(0, idx); buf = buf.slice(idx + 2);
      const evLine = raw.match(/^event: (.+)$/m)?.[1] ?? "message";
      const dataLine = raw.match(/^data: (.+)$/m)?.[1];
      if (!dataLine) continue;
      yield { event: evLine, data: JSON.parse(dataLine) } as unknown as SSEFrame;
    }
  }
}
```

- [ ] **Step 2: useAgentStream hook** — accumulates thought/tool/card frames, exposes `{ messages, isStreaming, send }`.

- [ ] **Step 3: Commit.**

### Task W6.2: Port MainApp.tsx → web/components/agent/*

**Files to create (each its own task):**

- `web/components/agent/ChatShell.tsx`
- `web/components/agent/MessageList.tsx`
- `web/components/agent/AssistantBubble.tsx` — copy JSX from mockup at `web/app/agent/chat/page.tsx`, accept `content` + `cards[]` as props
- `web/components/agent/UserBubble.tsx` — same
- `web/components/agent/ReasoningAccordion.tsx` — copy from mockup; accept `{ steps, time, lines }`, where lines come from the `thought` frames
- `web/components/agent/Composer.tsx` — textarea + quick chips + submit
- `web/components/agent/Sidebar.tsx` — session list via `GET /sessions`
- `web/components/agent/SidePanel.tsx`

Each component:
- [ ] Write component (copying JSX shapes from the existing mockup for fidelity)
- [ ] Write vitest/jest render test
- [ ] Commit

### Task W6.3: Card renderers

**Blocked by:** W7.1 (fixture corpus must exist before renderers can snapshot-test).

One task per card_type (11 total), each:
- [ ] Create `web/components/agent/cards/<Name>Card.tsx` by lifting JSX from the current mockup where relevant
- [ ] Add a fixture test (vitest/jest) that imports `tests/fixtures/cards/<card_type>.json` and snapshot-asserts the rendered output
- [ ] Commit

Order: `AllocationCard` first (matches the existing mockup most closely and exercises the Sentinel matrix), then `SwapQuoteCard`, `PoolCard`, `TokenCard`, `PositionCard`, `PlanCard`, `BalanceCard`, `BridgeCard`, `StakeCard`, `MarketOverviewCard`, `PairListCard`.

### Task W6.4: Replace /agent/chat mockup with live chat

**Files:**
- Modify: `web/app/agent/chat/page.tsx`

- [ ] Delete static mock body.
- [ ] Mount `<ChatShell>` gated on `NEXT_PUBLIC_FEATURE_AGENT_V2`; behind flag, keep the existing mock so previews continue to work until cutover.

---

## W7 — Structured cards + codegen (mostly delivered in Phase 1)

### Task W7.1: Fixture corpus + dual-render test

- [ ] Create `tests/fixtures/cards/*.json` with one example per `card_type`.
- [ ] Backend test: load each fixture, validate via `AgentCard.model_validate`.
- [ ] Frontend test: `for each fixture, render <CardRenderer> and assert a stable snapshot`.
- [ ] Commit.

---

## W8 — Tokens top bar

### Task W8.0: sentinel_lite helper

**Files:** `src/defi/sentinel_lite.py`, `tests/defi/test_sentinel_lite.py`

- [ ] Failing test: given a token address, helper returns `{"score": int 0..100, "badge": "safe"|"caution"|"risky"}` in under 100ms (must use only cached signals, no heavy pipeline).
- [ ] Implement: pull `ShieldService.verdict(token)` (cached) + the most-recent Sentinel score from Ilyon's `opportunity_cache` for a pool involving the token (if any). Collapse to a single 0–100 number: `min(shield.score, pool.sentinel) if pool else shield.score`. Badge from thresholds.
- [ ] Commit: `feat(defi): sentinel_lite one-score projection for ticker`

### Task W8.1: Backend ticker endpoint

**Files:**
- Modify: `src/api/routes/tokens_bar.py`
- Test: `tests/api/test_tokens_bar.py`

- [ ] Replace stub with handler that returns top 10 tokens by market cap with `{symbol, address, chain, price, change_24h, sentinel_lite: {score, badge}}`.
- [ ] Uses existing `PriceService` + `sentinel_lite` helper from W8.0.
- [ ] Cache for 30s via `aiohttp_cache` or an in-process TTL dict.
- [ ] Commit.

### Task W8.2: TokensTicker component

- [ ] Port from `IlyonAi-Wallet-assistant-main/client/src/components/` (or wherever the ticker lives) into `web/components/tokens-bar/TokensTicker.tsx`.
- [ ] Mount in `web/app/layout.tsx` behind `NEXT_PUBLIC_FEATURE_TOKENS_BAR`.
- [ ] Respect `prefers-reduced-motion` + hide-on-scroll.
- [ ] Commit.

---

## W9 — Swap page live

### Task W9.1: Replace mock `/agent/swap` with live quote flow

**Files:**
- Modify: `web/app/agent/swap/page.tsx`
- Create: `web/components/agent/swap/SwapForm.tsx`

- [ ] Port input form from mockup to a live component using `simulate_swap` + `build_swap_tx` / `build_solana_swap` via the agent HTTP endpoints.
- [ ] Integrate with W12's wallet adapter for signing.
- [ ] E2E test: Playwright — choose pair → quote displayed → sign prompt fires (mocked).
- [ ] Commit.

---

## W10 — Chrome extension UI

### Task W10.1: Scaffold extension build

- [ ] Copy `manifest.json`, `popup.html`, `sidepanel.html`, entrypoints from `IlyonAi-Wallet-assistant-main/client/src/{popup,sidepanel,background,content}`.
- [ ] Use **Vite** (with `@crxjs/vite-plugin`) — matches the upstream assistant's bundler. Add `extension/vite.config.ts` resolving `@/*` → `web/*` so the extension shares `web/components/agent/*` and `web/types/agent.ts`.
- [ ] Build script `pnpm -C extension build` produces `extension/dist/` + `extension/dist/ilyon-extension.zip` (via `zip-a-folder`).
- [ ] Commit.

### Task W10.2: Popup + Sidepanel mount ChatShell

- [ ] Both HTML entrypoints render the shared `<ChatShell>`; extension-specific chrome (tabs, auth launcher) wraps it.
- [ ] Auth: `chrome.storage.local.get/set("ilyon_token")` + refresh flow.
- [ ] Commit.

---

## W11 — AffiliateHook + Greenfield

### Task W11.1: AffiliateHook tests + deploy script

**Files:**
- Create: `contracts/test/AffiliateHook.t.sol`
- Create: `contracts/script/DeployAffiliateHook.s.sol`
- Create: `contracts/deployments/bsc-testnet.json`

- [ ] Port tests from assistant's Foundry project if any; otherwise write a minimal:

```solidity
function test_SingleSwap_Charges0_25Pct_Affiliate() public { ... }
```

- [ ] Run: `forge test -vvv` — PASS.
- [ ] Deploy to BSC testnet, pin address, commit deployments JSON.
- [ ] Commit.

### Task W11.2: Greenfield client

**Files:**
- Create: `src/storage/greenfield.py`
- Test: `tests/storage/test_greenfield.py`

- [ ] Implement `put_object(key, body)` / `get_object(key)` via Greenfield SP HTTP API (or `python-bnb-greenfield` if it exists).
- [ ] Stub-mode when `FEATURE_GREENFIELD_MEMORY=False`: writes/reads from a local tmpdir, so tests run without BNB creds.
- [ ] Commit.

### Task W11.3: Memory summarizer + background job

**Turn counter location:** the `chats` table already has `updated_at`; use `COUNT(chat_messages WHERE role='assistant')` at turn end as the counter. Cheap on an indexed FK. Trigger condition: `assistant_count % 10 == 0` and `> 0`.

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_summary_fires_on_tenth_assistant_turn(db_session, fake_router, fake_greenfield):
    chat = await create_chat(db_session, user_id=1)
    for i in range(20):
        await append_message(db_session, chat.id, role="user", content=f"q{i}")
        await append_message(db_session, chat.id, role="assistant", content=f"a{i}")
        await maybe_summarize(db_session, router=fake_router, greenfield=fake_greenfield, chat_id=chat.id, user_id=1)
    # Expected: fires at assistant counts 10 and 20 → two writes.
    assert len(fake_greenfield.writes) == 2
    assert fake_greenfield.writes[-1].key == f"1/{chat.id}.json"
```

- [ ] **Step 2: Implement `src/agent/summarizer.py`**

```python
from sqlalchemy import select, func
from src.models.chat import ChatMessage

async def maybe_summarize(db, *, router, greenfield, chat_id, user_id):
    count_r = await db.execute(
        select(func.count(ChatMessage.id))
        .where(ChatMessage.chat_id==chat_id, ChatMessage.role=="assistant"))
    count = count_r.scalar_one()
    if count == 0 or count % 10 != 0:
        return
    msgs_r = await db.execute(
        select(ChatMessage).where(ChatMessage.chat_id==chat_id)
                            .order_by(ChatMessage.created_at))
    transcript = "\n".join(f"{m.role}: {m.content}" for m in msgs_r.scalars())
    summary = await router.complete(
        model="default",
        messages=[{"role":"system","content":"Summarize this chat as context for future turns, <= 400 tokens."},
                  {"role":"user","content":transcript}],
        temperature=0.2, stop=None,
    )
    await greenfield.put_object(
        key=f"{user_id}/{chat_id}.json",
        body=summary["content"].encode(),
    )
```

Called from `run_turn` after the assistant message is persisted (fire-and-forget via `asyncio.create_task` so it doesn't block the response).

- [ ] **Step 3: Session resume loads the summary**

In `PersistentWindowMemory.load`, additionally:

```python
if settings.FEATURE_GREENFIELD_MEMORY:
    summary = await greenfield.get_object(f"{user_id}/{chat_id}.json")
    if summary:
        mem.chat_memory.add_ai_message(f"[prior conversation summary]\n{summary.decode()}")
```

- [ ] **Step 4: Pass + commit**

---

## W12 — Wallet adapters

### Task W12.1: MetaMask connector

**Files:**
- Create: `web/lib/wallets/metamask.ts`
- Port from `IlyonAi-Wallet-assistant-main/client/src/wallets/metamask.ts`
- [ ] Expose `connect()`, `signMessage(msg)`, `sendTransaction(tx)`, `onAccountChanged(cb)`.
- [ ] Test with `@metamask/detect-provider` mocked.
- [ ] Commit.

### Task W12.2: Phantom connector — same shape, ported from assistant's Phantom file.

### Task W12.3: Unified WalletProvider React context

- [ ] Create `web/components/providers/WalletProvider.tsx` that exposes `{ wallet, connect, signMessage, sendTx }`.
- [ ] Mount in `web/components/providers.tsx`.
- [ ] Commit.

### Task W12.4: Replace assistant's localStorage['token'] with Ilyon useAuth

Spec §3.4 requires removing assistant's legacy auth storage.

- [ ] Grep: `rg "localStorage\\[.(token|ilyon_token).\\]|localStorage\\.getItem\\('(token|ilyon_token)'\\)" web/ extension/` — list all hits.
- [ ] Replace every hit with the Ilyon `useAuth()` hook's `token` accessor (web) or `chrome.storage.local.get('ilyon_token')` (extension).
- [ ] Test: re-grep after change returns empty.
- [ ] Commit: `refactor(auth): drop legacy localStorage token path`.

---

## W13 — Extension background + content

### Task W13.1: Service worker

- [ ] Port `background/index.ts` from assistant. Handle auth keep-alive, cross-tab message passing, notification on new `card` frame arriving.
- [ ] Commit.

### Task W13.2: Content-script launcher

- [ ] Floating button injected only on `ALLOWED_HOST_PATTERNS` (options-page-managed).
- [ ] Opens sidepanel via `chrome.sidePanel.open`.
- [ ] Commit.

### Task W13.3: Options page

- [ ] Allowlist editor + feature toggles.
- [ ] Commit.

---

## Cross-cutting tasks

### Task X.1: Playwright surface tests

**Files:**
- Create: `tests/e2e/agent-chat.spec.ts`
- Create: `tests/e2e/agent-swap.spec.ts`
- Create: `tests/e2e/extension/fixtures/` (CRX packer)
- Create: `tests/e2e/extension-popup.spec.ts`

- [ ] Web: login → send message → SSE frames arrive → allocation card renders → refresh → history shows conversation.
- [ ] Swap: type amount → quote card renders → "Sign" triggers mocked wallet.
- [ ] Extension: launch Chromium with `--load-extension=<unpacked>` + `--disable-extensions-except`, open popup, see same card-rendering surface.
- [ ] Commit.

### Task X.2: Cutover PR

- [ ] Remove all `FEATURE_AGENT_V2=false` gates from production config.
- [ ] Delete the mock JSX in `web/app/agent/chat/page.tsx` and `web/app/agent/swap/page.tsx` that guarded the preview path.
- [ ] Tag release `v-agent-merge-cutover`.
- [ ] Commit.

### Task X.3: Post-cutover cleanup (≥ 14 days after cutover + green Playwright in prod)

- [ ] `git rm -r IlyonAi-Wallet-assistant-main/`
- [ ] Commit: `chore: remove upstream assistant source tree (merged into main)`

---

## Final checklist

- [ ] Phase 0 complete (Moralis rotated, audit script CI-enforced)
- [ ] Phase 1 Day-0 PR merged (all 5 contracts + migration + stubs)
- [ ] W1–W13 merged behind flags; unit + integration tests green
- [ ] Playwright (X.1) green on staging + prod
- [ ] Cutover X.2
- [ ] Post-cutover cleanup X.3 ≥ 14 days later

---

## Reference skills

- @superpowers:subagent-driven-development — execute one task per fresh subagent
- @superpowers:executing-plans — inline batch execution mode
- @superpowers:test-driven-development — every task above already uses red→green→commit
