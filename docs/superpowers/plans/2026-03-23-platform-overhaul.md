# Platform Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform every Smart Money page from vague labels into a real intelligence tool, fix audit findings visibility, enhance rekt live data, and polish remaining pages.

**Architecture:** Backend enrichments expose existing data that the frontend ignores (wallet addresses, transaction details, behavior signals). New wallet profile + forensics endpoints aggregate data from existing services. Audit findings estimation fills gaps where DefiLlama doesn't provide severity data. Frontend rewrites surface all available context.

**Tech Stack:** Python aiohttp (backend), Next.js/React/TypeScript (frontend), TanStack Query, Pydantic, Helius API, DefiLlama API

**Specs:**
- `docs/superpowers/specs/2026-03-23-smart-money-overhaul-design.md`
- `docs/superpowers/specs/2026-03-23-intel-enrichment-design.md`
- `docs/superpowers/specs/2026-03-23-platform-polish-design.md`

**Working directory:** `/home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local`

---

## File Structure

### Backend — Modified
| File | Responsibility |
|------|---------------|
| `src/api/routes/smart_money.py` | Enrich overview response with full transaction fields per buyer/seller/flow |
| `src/api/routes/whale.py:415-453` | Implement real whale profile (currently stub returning zeros) |
| `src/api/schemas/responses.py:385-399` | Update SmartMoneyOverviewResponse model |
| `src/intel/rekt_database.py:520-566` | Add estimated severity findings for DefiLlama audits |
| `src/intel/rekt_database.py:379-500` | Expand RektDatabase live fetch, reduce cache TTL |

### Backend — New
| File | Responsibility |
|------|---------------|
| `src/api/routes/wallet_intel.py` | New wallet profile + forensics endpoints |
| `tests/api/test_wallet_intel.py` | Tests for wallet intel endpoints |
| `tests/api/test_smart_money_enriched.py` | Tests for enriched overview response |
| `tests/test_audit_findings_estimation.py` | Tests for estimated findings generation |

### Frontend — Modified
| File | Responsibility |
|------|---------------|
| `web/types/index.ts:322-349` | Enrich SmartMoneyFlow, SmartMoneyParticipant types |
| `web/lib/api.ts:424-450` | Update normalizers for enriched response |
| `web/lib/hooks.ts` | Add useWalletProfile, useWalletForensics hooks |
| `web/app/smart-money/page.tsx` | Full rewrite — wallet addresses, labels, transaction feed |
| `web/app/flows/page.tsx` | Full rewrite — rich transaction cards |
| `web/app/whales/page.tsx` | Add labels, chain badges |
| `web/app/wallet/[address]/page.tsx` | Full rewrite — profile, forensics, transactions |
| `web/app/audits/page.tsx` | Show estimated badge, all audits have findings |
| `web/app/rekt/page.tsx` | Sort controls, stats header, timestamp |
| `web/app/rekt/[id]/page.tsx` | Post-mortem button, recovery badge |

---

## Task 1: Enrich Smart Money Overview Backend

**Files:**
- Modify: `src/api/routes/smart_money.py` (full file, 95 lines)
- Modify: `src/api/schemas/responses.py:385-399`
- Test: `tests/api/test_smart_money_enriched.py` (create)

- [ ] **Step 1: Write failing test for enriched overview response**

Create `tests/api/test_smart_money_enriched.py`:

```python
"""Tests for enriched smart money overview response."""
import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from unittest.mock import AsyncMock, patch, MagicMock

from src.api.routes.smart_money import get_smart_money_overview, setup_smart_money_routes


@pytest.mark.asyncio
async def test_overview_returns_enriched_buyer_fields(aiohttp_client):
    """Top buyers include wallet_address, token_symbol, dex_name, timestamp, tx_count."""
    fake_txs = [
        {
            "type": "buy",
            "wallet_address": "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9",
            "wallet_label": "Alameda",
            "amount_usd": 44300,
            "token_symbol": "BONK",
            "token_name": "Bonk",
            "token_address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "dex_name": "Jupiter",
            "signature": "sig1",
            "timestamp": "2026-03-23T10:00:00Z",
            "chain": "solana",
        },
        {
            "type": "buy",
            "wallet_address": "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9",
            "wallet_label": "Alameda",
            "amount_usd": 22600,
            "token_symbol": "JUP",
            "token_name": "Jupiter",
            "token_address": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
            "dex_name": "Jupiter",
            "signature": "sig2",
            "timestamp": "2026-03-23T09:50:00Z",
            "chain": "solana",
        },
    ]

    app = web.Application()
    setup_smart_money_routes(app)

    with patch("src.api.routes.smart_money.SolanaClient") as MockClient:
        instance = AsyncMock()
        instance.get_whale_transactions = AsyncMock(return_value=fake_txs)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        client = await aiohttp_client(app)
        resp = await client.get("/api/v1/smart-money/overview")
        assert resp.status == 200
        body = await resp.json()
        data = body["data"]

        buyer = data["top_buyers"][0]
        assert buyer["wallet_address"] == "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9"
        assert buyer["label"] == "Alameda"
        assert buyer["token_symbol"] == "BONK"
        assert buyer["dex_name"] == "Jupiter"
        assert buyer["tx_count"] == 2
        assert buyer["amount_usd"] == 44300 + 22600

        # Flows should include full transaction details
        flow = data["recent_transactions"][0]
        assert "wallet_address" in flow
        assert "token_symbol" in flow
        assert "signature" in flow
        assert "timestamp" in flow

        # Flow direction derived
        assert data["flow_direction"] in ("accumulating", "distributing", "mixed", "neutral")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/api/test_smart_money_enriched.py -v`

Expected: FAIL — response lacks enriched fields.

- [ ] **Step 3: Update Pydantic response model**

In `src/api/schemas/responses.py`, update `SmartMoneyOverviewResponse` (around line 385):

```python
class SmartMoneyOverviewResponse(BaseModel):
    """Smart money overview response with flow metrics and participant data."""
    net_flow_usd: float = 0
    inflow_usd: float = 0
    outflow_usd: float = 0
    flow_direction: str = "neutral"
    sell_volume_percent: float = 0
    top_buyers: List[Dict[str, Any]] = Field(default_factory=list)
    top_sellers: List[Dict[str, Any]] = Field(default_factory=list)
    recent_transactions: List[Dict[str, Any]] = Field(default_factory=list)
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    flows: List[Dict[str, Any]] = Field(default_factory=list)
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
```

- [ ] **Step 4: Rewrite smart_money.py handler to aggregate per-wallet and include full tx details**

Rewrite `src/api/routes/smart_money.py` — the handler should:

1. Group transactions by wallet_address.
2. Per wallet: aggregate total amount_usd, count transactions, pick the largest tx for token_symbol/dex_name, record the most recent timestamp.
3. Build `recent_transactions` list with all raw transaction fields (wallet_address, wallet_label, token_symbol, token_name, token_address, amount_tokens, amount_usd, dex_name, signature, timestamp, chain, direction).
4. Derive `flow_direction`: "accumulating" if inflow > outflow, "distributing" if outflow > inflow, "neutral" if no volume.
5. Compute `sell_volume_percent`: outflow / (inflow + outflow) * 100.

```python
"""Smart money API routes."""

import logging
from collections import defaultdict
from datetime import datetime

from aiohttp import web

from src.api.response_envelope import envelope_response, envelope_error_response
from src.api.schemas.responses import SmartMoneyOverviewResponse
from src.config import settings
from src.data.solana import SolanaClient

logger = logging.getLogger(__name__)


async def get_smart_money_overview(request: web.Request) -> web.Response:
    buyer_agg: dict = defaultdict(lambda: {
        "wallet_address": "", "label": None, "amount_usd": 0.0,
        "tx_count": 0, "last_seen": "", "token_symbol": "", "dex_name": "",
        "largest_tx_amount": 0.0,
    })
    seller_agg: dict = defaultdict(lambda: {
        "wallet_address": "", "label": None, "amount_usd": 0.0,
        "tx_count": 0, "last_seen": "", "token_symbol": "", "dex_name": "",
        "largest_tx_amount": 0.0,
    })
    recent_transactions = []
    inflow_usd = 0.0
    outflow_usd = 0.0

    try:
        async with SolanaClient(
            rpc_url=settings.solana_rpc_url,
            helius_api_key=settings.helius_api_key,
        ) as client:
            activity = await client.get_whale_transactions(limit=50)
            for tx in activity:
                tx_type = str(tx.get("type", "")).lower()
                direction = "inflow" if tx_type == "buy" else "outflow"
                amount = float(tx.get("amount_usd", 0) or 0)
                chain = str(tx.get("chain", "solana")).lower()
                wallet = str(
                    tx.get("wallet_address")
                    or tx.get("wallet", "")
                    or tx.get("signer", "")
                    or ""
                )
                label = tx.get("wallet_label") or tx.get("label")
                token_symbol = str(tx.get("token_symbol", "") or "")
                token_name = str(tx.get("token_name", "") or "")
                token_address = str(tx.get("token_address", "") or "")
                dex_name = str(tx.get("dex_name", "") or "")
                signature = str(tx.get("signature", "") or "")
                timestamp = str(tx.get("timestamp", "") or "")
                amount_tokens = float(tx.get("amount_tokens", 0) or 0)

                recent_transactions.append({
                    "direction": direction,
                    "wallet_address": wallet,
                    "wallet_label": label,
                    "token_symbol": token_symbol,
                    "token_name": token_name,
                    "token_address": token_address,
                    "amount_tokens": amount_tokens,
                    "amount_usd": amount,
                    "dex_name": dex_name,
                    "signature": signature,
                    "timestamp": timestamp,
                    "chain": chain,
                })

                agg = buyer_agg if direction == "inflow" else seller_agg
                if wallet:
                    entry = agg[wallet]
                    entry["wallet_address"] = wallet
                    entry["label"] = entry["label"] or label
                    entry["amount_usd"] += amount
                    entry["tx_count"] += 1
                    if not entry["last_seen"] or timestamp > entry["last_seen"]:
                        entry["last_seen"] = timestamp
                    if amount > entry["largest_tx_amount"]:
                        entry["largest_tx_amount"] = amount
                        entry["token_symbol"] = token_symbol
                        entry["dex_name"] = dex_name

                if direction == "inflow":
                    inflow_usd += amount
                else:
                    outflow_usd += amount

    except Exception as e:
        logger.error(f"Smart money overview failed: {e}")
        return envelope_error_response(
            f"Failed to fetch smart money data: {e}",
            code="SMART_MONEY_FETCH_FAILED",
            http_status=502,
            meta={"surface": "smart_money_overview"},
        )

    top_buyers = sorted(buyer_agg.values(), key=lambda x: x["amount_usd"], reverse=True)
    top_sellers = sorted(seller_agg.values(), key=lambda x: x["amount_usd"], reverse=True)
    net_flow_usd = inflow_usd - outflow_usd
    total_volume = inflow_usd + outflow_usd

    if total_volume == 0:
        flow_direction = "neutral"
    elif inflow_usd > outflow_usd:
        flow_direction = "accumulating"
    else:
        flow_direction = "distributing"

    sell_pct = (outflow_usd / total_volume * 100) if total_volume > 0 else 0

    # Strip internal aggregation fields before response
    for b in top_buyers:
        b.pop("largest_tx_amount", None)
    for s in top_sellers:
        s.pop("largest_tx_amount", None)

    payload = SmartMoneyOverviewResponse(
        net_flow_usd=net_flow_usd,
        inflow_usd=inflow_usd,
        outflow_usd=outflow_usd,
        flow_direction=flow_direction,
        sell_volume_percent=round(sell_pct, 1),
        top_buyers=top_buyers[:10],
        top_sellers=top_sellers[:10],
        recent_transactions=recent_transactions[:50],
        updated_at=datetime.utcnow().isoformat(),
    ).model_dump(mode="json")

    return envelope_response(payload, meta={"surface": "smart_money_overview"})


def setup_smart_money_routes(app: web.Application):
    app.router.add_get("/api/v1/smart-money/overview", get_smart_money_overview)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/api/test_smart_money_enriched.py tests/api/test_smart_money_routes.py -v`

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/smart_money.py src/api/schemas/responses.py tests/api/test_smart_money_enriched.py
git commit -m "feat: enrich smart money overview with full transaction context"
```

---

## Task 2: Wallet Profile & Forensics Backend Endpoints

**Files:**
- Create: `src/api/routes/wallet_intel.py`
- Modify: `src/api/app.py` (add route registration)
- Modify: `src/api/routes/whale.py:415-453` (implement real profile)
- Test: `tests/api/test_wallet_intel.py` (create)

- [ ] **Step 1: Write failing test for wallet profile endpoint**

Create `tests/api/test_wallet_intel.py`:

```python
"""Tests for wallet intelligence endpoints."""
import pytest
from aiohttp import web
from unittest.mock import AsyncMock, patch, MagicMock

from src.api.routes.wallet_intel import setup_wallet_intel_routes


@pytest.mark.asyncio
async def test_wallet_profile_returns_basic_info(aiohttp_client):
    """GET /api/v1/wallets/{address}/profile returns wallet profile."""
    app = web.Application()
    setup_wallet_intel_routes(app)

    client = await aiohttp_client(app)
    resp = await client.get("/api/v1/wallets/5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9/profile")
    assert resp.status == 200
    body = await resp.json()
    data = body["data"]
    assert data["wallet"] == "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9"
    assert "label" in data
    assert "recent_transactions" in data


@pytest.mark.asyncio
async def test_wallet_forensics_returns_risk_data(aiohttp_client):
    """GET /api/v1/wallets/{address}/forensics returns risk analysis."""
    app = web.Application()
    setup_wallet_intel_routes(app)

    client = await aiohttp_client(app)
    resp = await client.get("/api/v1/wallets/5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9/forensics")
    assert resp.status == 200
    body = await resp.json()
    data = body["data"]
    assert "risk_level" in data
    assert "reputation_score" in data
    assert "tokens_deployed" in data
    assert "patterns_detected" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_wallet_intel.py -v`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement wallet_intel.py**

Create `src/api/routes/wallet_intel.py`:

```python
"""Wallet intelligence API routes — profile and forensics."""

import logging

from aiohttp import web

from src.api.response_envelope import envelope_response, envelope_error_response
from src.config import settings
from src.data.solana import SolanaClient

logger = logging.getLogger(__name__)

# Known whale labels (shared with whale.py)
KNOWN_WHALES = {
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9": "Alameda",
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM": "Jump Trading",
    "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH": "Wintermute",
    "2AQdpHJ2JpcEgPiATUXjQxA8QmafFegfQwSLWSprPicm": "Circle",
}


async def get_wallet_profile(request: web.Request) -> web.Response:
    """
    GET /api/v1/wallets/{address}/profile

    Aggregates wallet info from whale transactions, known labels, and entity graph.
    """
    address = request.match_info.get("address", "")
    if not address:
        return envelope_error_response("Wallet address required", code="MISSING_ADDRESS", http_status=400)

    label = KNOWN_WHALES.get(address)
    recent_transactions = []
    volume_usd = 0.0
    tx_count = 0

    try:
        async with SolanaClient(
            rpc_url=settings.solana_rpc_url,
            helius_api_key=settings.helius_api_key,
        ) as client:
            activity = await client.get_whale_transactions(limit=100)
            for tx in activity:
                wallet = str(tx.get("wallet_address") or tx.get("wallet", "") or "")
                if wallet != address:
                    continue
                amount = float(tx.get("amount_usd", 0) or 0)
                volume_usd += amount
                tx_count += 1
                if not label:
                    label = tx.get("wallet_label") or tx.get("label")
                recent_transactions.append({
                    "direction": "inflow" if str(tx.get("type", "")).lower() == "buy" else "outflow",
                    "token_symbol": str(tx.get("token_symbol", "") or ""),
                    "token_address": str(tx.get("token_address", "") or ""),
                    "amount_usd": amount,
                    "amount_tokens": float(tx.get("amount_tokens", 0) or 0),
                    "dex_name": str(tx.get("dex_name", "") or ""),
                    "signature": str(tx.get("signature", "") or ""),
                    "timestamp": str(tx.get("timestamp", "") or ""),
                    "chain": str(tx.get("chain", "solana")).lower(),
                })
    except Exception as e:
        logger.warning(f"Wallet profile fetch error: {e}")

    # Entity lookup (if graph store is initialized)
    entity_id = None
    linked_wallets = []
    link_reason = None
    try:
        from src.api.routes.entity import GRAPH_STORE_KEY
        graph_store = request.app.get(GRAPH_STORE_KEY)
        if graph_store:
            entity_id = graph_store.get_entity_id_for_wallet(address)
            if entity_id:
                linked_wallets = [w for w in graph_store.get_wallets_for_entity(entity_id) if w != address]
                link_reason = graph_store.get_link_reason_for_entity(entity_id)
    except Exception:
        pass

    return envelope_response({
        "wallet": address,
        "label": label,
        "volume_usd": volume_usd,
        "transaction_count": tx_count,
        "entity_id": entity_id,
        "linked_wallets": linked_wallets,
        "link_reason": link_reason,
        "recent_transactions": recent_transactions,
    })


async def get_wallet_forensics(request: web.Request) -> web.Response:
    """
    GET /api/v1/wallets/{address}/forensics

    Returns risk analysis from WalletForensicsEngine.
    """
    address = request.match_info.get("address", "")
    if not address:
        return envelope_error_response("Wallet address required", code="MISSING_ADDRESS", http_status=400)

    try:
        from src.analytics.wallet_forensics import WalletForensicsEngine
        engine = WalletForensicsEngine()
        result = await engine.analyze_wallet(address)

        return envelope_response({
            "wallet": address,
            "risk_level": result.risk_level.value if hasattr(result.risk_level, 'value') else str(result.risk_level),
            "reputation_score": result.reputation_score,
            "tokens_deployed": result.tokens_deployed,
            "rugged_tokens": result.rugged_tokens,
            "active_tokens": result.active_tokens,
            "rug_percentage": result.rug_percentage,
            "patterns_detected": result.patterns_detected,
            "pattern_severity": result.pattern_severity,
            "funding_risk": result.funding_risk,
            "confidence": result.confidence,
            "evidence_summary": result.evidence_summary,
        })
    except Exception as e:
        logger.error(f"Wallet forensics error: {e}")
        return envelope_response({
            "wallet": address,
            "risk_level": "UNKNOWN",
            "reputation_score": 0,
            "tokens_deployed": 0,
            "rugged_tokens": 0,
            "active_tokens": 0,
            "rug_percentage": 0,
            "patterns_detected": [],
            "pattern_severity": "NONE",
            "funding_risk": 0,
            "confidence": 0,
            "evidence_summary": "Forensics analysis unavailable",
        })


def setup_wallet_intel_routes(app: web.Application):
    app.router.add_get("/api/v1/wallets/{address}/profile", get_wallet_profile)
    app.router.add_get("/api/v1/wallets/{address}/forensics", get_wallet_forensics)
```

- [ ] **Step 4: Register routes in app.py**

Add `from src.api.routes.wallet_intel import setup_wallet_intel_routes` import and call `setup_wallet_intel_routes(app)` in each route registration block in `src/api/app.py` (after `setup_smart_money_routes`).

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/api/test_wallet_intel.py tests/api/test_smart_money_routes.py -v`

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/wallet_intel.py src/api/app.py tests/api/test_wallet_intel.py
git commit -m "feat: add wallet profile and forensics API endpoints"
```

---

## Task 3: Audit Findings Estimation

**Files:**
- Modify: `src/intel/rekt_database.py:520-566` (AuditDatabase._fetch_defillama_audits)
- Test: `tests/test_audit_findings_estimation.py` (create)

- [ ] **Step 1: Write failing test**

Create `tests/test_audit_findings_estimation.py`:

```python
"""Tests for deterministic audit findings estimation."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.intel.rekt_database import AuditDatabase


def _mock_aiohttp_session(json_data, status=200):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.get.return_value = mock_cm
    return mock_session


@pytest.mark.asyncio
async def test_defillama_audits_get_estimated_findings():
    """Audits from DefiLlama should have non-empty severity_findings."""
    db = AuditDatabase()
    db._session = _mock_aiohttp_session([
        {
            "name": "TestProtocol",
            "audits": "2",
            "audit_links": ["https://example.com/audit.pdf"],
            "audit_note": "Audited by Trail of Bits",
            "chains": ["Ethereum"],
        }
    ])

    audits = await db._fetch_defillama_audits()
    assert len(audits) > 0
    audit = audits[0]
    sf = audit["severity_findings"]
    assert sf, "severity_findings should not be empty"
    assert "critical" in sf
    assert "high" in sf
    assert "medium" in sf
    assert "low" in sf
    assert "informational" in sf
    assert audit["findings_source"] == "estimated"
    # Total findings should be > 0
    assert sum(sf.values()) > 0


@pytest.mark.asyncio
async def test_estimated_findings_are_deterministic():
    """Same protocol+auditor should produce same findings on repeated calls."""
    db = AuditDatabase()
    proto_data = [{
        "name": "StableProto",
        "audits": "1",
        "audit_links": [],
        "audit_note": "PeckShield",
        "chains": ["Ethereum"],
    }]
    db._session = _mock_aiohttp_session(proto_data)
    first = await db._fetch_defillama_audits()

    # Reset cache to force re-fetch
    db._live_cache = None
    db._cache_ts = 0
    db._session = _mock_aiohttp_session(proto_data)
    second = await db._fetch_defillama_audits()

    assert first[0]["severity_findings"] == second[0]["severity_findings"]


@pytest.mark.asyncio
async def test_seed_audits_have_verified_source():
    """Seed audits should have findings_source='verified'."""
    db = AuditDatabase()
    db._session = _mock_aiohttp_session([])  # No DefiLlama data
    audits = await db.get_audits(limit=100)
    for a in audits:
        if a["id"].startswith("llama-"):
            continue
        assert a.get("findings_source", "verified") == "verified"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_audit_findings_estimation.py -v`

Expected: FAIL — severity_findings is empty, no findings_source field.

- [ ] **Step 3: Implement estimated findings in AuditDatabase._fetch_defillama_audits**

In `src/intel/rekt_database.py`, modify `_fetch_defillama_audits()` (around line 549-558). Replace the empty `severity_findings: {}` with deterministic estimation:

```python
import hashlib
import random as _random

# Inside _fetch_defillama_audits, replace lines 549-558 with:
                            # Generate deterministic estimated findings
                            proto_name = proto.get("name", "")
                            seed_str = f"{proto_name}:{auditor}"
                            seed_val = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
                            rng = _random.Random(seed_val)

                            has_audits = audits_count and str(audits_count) != "0"
                            if has_audits:
                                # Passed audit: conservative findings
                                est_findings = {
                                    "critical": 0,
                                    "high": rng.randint(0, 1),
                                    "medium": rng.randint(1, 3),
                                    "low": rng.randint(2, 6),
                                    "informational": rng.randint(3, 10),
                                }
                            else:
                                est_findings = {
                                    "critical": 0,
                                    "high": 0,
                                    "medium": 0,
                                    "low": 0,
                                    "informational": 0,
                                }

                            audited.append({
                                "id": f"llama-{proto_name.lower().replace(' ', '-')}",
                                "protocol": proto_name,
                                "auditor": auditor,
                                "date": "",
                                "report_url": audit_links[0] if audit_links else "",
                                "severity_findings": est_findings,
                                "verdict": "PASS" if has_audits else "UNKNOWN",
                                "chains": proto.get("chains") or [],
                                "source": "DefiLlama",
                                "findings_source": "estimated",
                            })
```

Also, in `get_audits()`, add `findings_source: "verified"` to seed audits (around line 577):

```python
        audits: List[Dict[str, Any]] = [dict(a, findings_source="verified") for a in KNOWN_AUDITS]
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_audit_findings_estimation.py tests/test_audit_database.py -v`

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/intel/rekt_database.py tests/test_audit_findings_estimation.py
git commit -m "feat: generate deterministic estimated findings for DefiLlama audits"
```

---

## Task 4: Rekt Database Enhancement

**Files:**
- Modify: `src/intel/rekt_database.py:379-500` (RektDatabase class)
- Modify: `web/app/rekt/page.tsx`
- Modify: `web/app/rekt/[id]/page.tsx`

- [ ] **Step 1: Reduce DefiLlama hacks cache TTL from 1 hour to 30 minutes**

In `src/intel/rekt_database.py`, find the RektDatabase `_fetch_llama_hacks` method cache check (should be `if ... < 3600`). Change `3600` to `1800`.

- [ ] **Step 2: Enhance rekt list page with sort controls and stats header**

In `web/app/rekt/page.tsx`, add:
- Total incidents count and total stolen amount in the header.
- Sort dropdown: by amount (largest first), by date (newest first), by severity.
- "Last refreshed" timestamp.

Read the current file first, then add sort state and stats computation.

- [ ] **Step 3: Enhance rekt detail page**

In `web/app/rekt/[id]/page.tsx`, add:
- Prominent "View Post-Mortem" button (linked to `post_mortem_url`).
- "Funds Recovered" / "Funds Not Recovered" badge.
- Better layout for attack type, chains, severity.

- [ ] **Step 4: Run frontend tests to verify nothing breaks**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local/web && npx vitest run`

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/intel/rekt_database.py web/app/rekt/page.tsx web/app/rekt/[id]/page.tsx
git commit -m "feat: enhance rekt database with faster refresh and improved UI"
```

---

## Task 5: Frontend Types & API Layer for Smart Money

**Files:**
- Modify: `web/types/index.ts:322-349`
- Modify: `web/lib/api.ts:424-450`
- Modify: `web/lib/hooks.ts`

- [ ] **Step 1: Update TypeScript types**

In `web/types/index.ts`, update the Smart Money types:

```typescript
export interface SmartMoneyParticipant {
  wallet_address: string;
  label: string | null;
  amount_usd: number;
  tx_count: number;
  last_seen: string;
  token_symbol: string;
  dex_name: string;
}

export interface SmartMoneyFlow {
  direction: string;
  wallet_address: string;
  wallet_label: string | null;
  token_symbol: string;
  token_name: string;
  token_address: string;
  amount_tokens: number;
  amount_usd: number;
  dex_name: string;
  signature: string;
  timestamp: string;
  chain: string;
}

export interface SmartMoneyOverviewResponse {
  net_flow_usd: number;
  inflow_usd: number;
  outflow_usd: number;
  flow_direction: string;
  sell_volume_percent: number;
  top_buyers: SmartMoneyParticipant[];
  top_sellers: SmartMoneyParticipant[];
  recent_transactions: SmartMoneyFlow[];
  entities?: SmartMoneyEntity[];
  flows?: SmartMoneyFlow[];
  updated_at: string;
}

export interface WalletProfileResponse {
  wallet: string;
  label: string | null;
  volume_usd: number;
  transaction_count: number;
  entity_id: string | null;
  linked_wallets: string[];
  link_reason: string | null;
  recent_transactions: SmartMoneyFlow[];
}

export interface WalletForensicsResponse {
  wallet: string;
  risk_level: string;
  reputation_score: number;
  tokens_deployed: number;
  rugged_tokens: number;
  active_tokens: number;
  rug_percentage: number;
  patterns_detected: string[];
  pattern_severity: string;
  funding_risk: number;
  confidence: number;
  evidence_summary: string;
}
```

- [ ] **Step 2: Update API normalizers and add new API functions**

In `web/lib/api.ts`, update `normalizeSmartMoneyOverviewResponse` to handle new fields, and add:

```typescript
export async function getWalletProfile(address: string): Promise<WalletProfileResponse> {
  const raw = await fetchAPI<any>(`/api/v1/wallets/${address}/profile`);
  const data = unwrapEnvelope<any>(raw, {});
  return {
    wallet: data.wallet ?? address,
    label: data.label ?? null,
    volume_usd: Number(data.volume_usd ?? 0),
    transaction_count: Number(data.transaction_count ?? 0),
    entity_id: data.entity_id ?? null,
    linked_wallets: Array.isArray(data.linked_wallets) ? data.linked_wallets : [],
    link_reason: data.link_reason ?? null,
    recent_transactions: Array.isArray(data.recent_transactions) ? data.recent_transactions : [],
  };
}

export async function getWalletForensics(address: string): Promise<WalletForensicsResponse> {
  const raw = await fetchAPI<any>(`/api/v1/wallets/${address}/forensics`);
  const data = unwrapEnvelope<any>(raw, {});
  return {
    wallet: data.wallet ?? address,
    risk_level: data.risk_level ?? "UNKNOWN",
    reputation_score: Number(data.reputation_score ?? 0),
    tokens_deployed: Number(data.tokens_deployed ?? 0),
    rugged_tokens: Number(data.rugged_tokens ?? 0),
    active_tokens: Number(data.active_tokens ?? 0),
    rug_percentage: Number(data.rug_percentage ?? 0),
    patterns_detected: Array.isArray(data.patterns_detected) ? data.patterns_detected : [],
    pattern_severity: data.pattern_severity ?? "NONE",
    funding_risk: Number(data.funding_risk ?? 0),
    confidence: Number(data.confidence ?? 0),
    evidence_summary: data.evidence_summary ?? "",
  };
}
```

- [ ] **Step 3: Add hooks**

In `web/lib/hooks.ts`, add:

```typescript
export function useWalletProfile(address: string | null) {
  return useQuery({
    queryKey: ["wallet-profile", address],
    queryFn: () => api.getWalletProfile(address!),
    enabled: !!address,
    staleTime: 60_000,
  });
}

export function useWalletForensics(address: string | null) {
  return useQuery({
    queryKey: ["wallet-forensics", address],
    queryFn: () => api.getWalletForensics(address!),
    enabled: !!address,
    staleTime: 5 * 60_000,
  });
}
```

- [ ] **Step 4: Commit**

```bash
git add web/types/index.ts web/lib/api.ts web/lib/hooks.ts
git commit -m "feat: add wallet profile/forensics types, API functions, and hooks"
```

---

## Task 6: Smart Money Hub Frontend Rewrite

**Files:**
- Modify: `web/app/smart-money/page.tsx` (full rewrite)

- [ ] **Step 1: Rewrite Smart Money Hub page**

The page should display:
- Metrics row: Net Flow, Inflow, Outflow, Flow Direction (with accumulating/distributing indicator)
- Top Buyers table: wallet address (truncated, clickable), label badge, total amount, tx count, token symbol, dex, last seen
- Top Sellers table: same format
- Recent Transactions feed: direction icon, wallet (truncated, clickable), token, amount, dex, chain badge, timestamp, explorer link
- Auto-refresh every 60 seconds
- Links to Flows, Entity Explorer, Wallet Lookup

Read the current `web/app/smart-money/page.tsx` first, then rewrite it keeping the same hook (`useSmartMoneyOverview`) but rendering the new enriched fields.

Key UI patterns:
- Use `truncateAddress(wallet, 4)` for address display
- Link wallets to `/wallet/{address}`
- Use `formatUSD()`, `formatCompact()`, `formatRelativeTime()` from `@/lib/utils`
- Green for buys/inflow, red for sells/outflow
- Badge for known labels (Alameda, Jump, etc.)

- [ ] **Step 2: Run frontend tests**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local/web && npx vitest run tests/app/smart-money.page.test.tsx`

Fix any test failures caused by the rewrite (update mock data and assertions to match new field structure).

- [ ] **Step 3: Commit**

```bash
git add web/app/smart-money/page.tsx web/tests/app/smart-money.page.test.tsx
git commit -m "feat: rewrite Smart Money Hub with wallet addresses and transaction context"
```

---

## Task 7: Flows Page Frontend Rewrite

**Files:**
- Modify: `web/app/flows/page.tsx` (full rewrite)

- [ ] **Step 1: Rewrite Flows page**

Replace the current minimal flow cards with rich transaction cards showing:
- Direction icon (green buy / red sell)
- Wallet address (truncated, clickable → `/wallet/{address}`) with label badge
- Token symbol → amount in tokens and USD
- DEX name, chain badge, Solscan explorer link
- Relative timestamp
- Summary bar at top: X buys ($Y) • Z sells ($W) • Net ±$V
- Filters: buy/sell type, minimum amount
- Remove non-functional chain filters (keep only Solana indicator for now)

Use `recent_transactions` from the smart money overview response (which now has full fields).

- [ ] **Step 2: Run frontend tests**

Run: `npx vitest run`

Expected: All pass (flows page tests may need updating).

- [ ] **Step 3: Commit**

```bash
git add web/app/flows/page.tsx
git commit -m "feat: rewrite Flows page with rich transaction cards"
```

---

## Task 8: Wallet Lookup Frontend Rewrite

**Files:**
- Modify: `web/app/wallet/[address]/page.tsx` (full rewrite)

- [ ] **Step 1: Rewrite Wallet Lookup page**

Replace the current stub with a full wallet intelligence page:
- Header: wallet address (full, with copy button and explorer link), label badge
- Metrics row: Risk Level (color-coded), Volume, Transaction Count, Entity ID
- Recent Transactions section: same rich card format as Flows
- Forensics section: risk score, deployment stats, patterns detected, funding risk, confidence
- Linked Wallets section: other wallets in same entity, link reason
- Use `useWalletProfile(address)` and `useWalletForensics(address)` hooks

Handle states:
- Loading: skeleton cards
- No data: "No whale activity found for this wallet. Try a known whale address."
- Forensics error: show degraded state with "Forensics unavailable" message

- [ ] **Step 2: Run tests**

Run: `npx vitest run`

Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add web/app/wallet/[address]/page.tsx
git commit -m "feat: rewrite Wallet Lookup with profile, forensics, and entity links"
```

---

## Task 9: Whales Page Enhancement

**Files:**
- Modify: `web/app/whales/page.tsx`

- [ ] **Step 1: Enhance Whales page**

Read `web/app/whales/page.tsx` and add:
- Wallet label badges (if `wallet_label` is set, show as a colored badge next to the address)
- Chain badge per transaction (instead of hardcoded Solscan link, use chain field to pick correct explorer)
- Make wallet addresses clickable → `/wallet/{address}`
- Token logo display if available

Keep existing filter UI (min amount, chain, buy/sell type).

- [ ] **Step 2: Run tests**

Run: `npx vitest run`

Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add web/app/whales/page.tsx
git commit -m "feat: enhance Whales page with labels and chain badges"
```

---

## Task 10: Audits Page Enhancement

**Files:**
- Modify: `web/app/audits/page.tsx`

- [ ] **Step 1: Enhance Audits page**

Read `web/app/audits/page.tsx` and add:
- Small "Estimated" badge on audit cards where `findings_source === "estimated"`.
- Use a subtle color (e.g., `text-muted-foreground`) for estimated badges vs no badge for verified.
- All audits should now show severity finding bars (not just the 4 seed ones).
- Update the type for audit records to include optional `findings_source` field.

- [ ] **Step 2: Run frontend tests**

Run: `npx vitest run`

Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add web/app/audits/page.tsx web/types/index.ts
git commit -m "feat: show estimated findings badge on audit records"
```

---

## Task 11: Platform Polish — Dashboard, DeFi, Remaining Pages

**Files:**
- Modify: `web/app/dashboard/page.tsx`
- Modify: `web/app/rekt/page.tsx` (if not done in Task 4)
- Modify: `web/app/alerts/page.tsx`

- [ ] **Step 1: Dashboard polish**

Read `web/app/dashboard/page.tsx` and add:
- Make trending token cards clickable → `/token/{address}?chain={chain}`.
- Make whale activity items clickable → `/wallet/{address}`.
- Add "Last updated" timestamp at the bottom.

- [ ] **Step 2: Alerts polish**

Read `web/app/alerts/page.tsx` and add:
- Show alert count per severity in filter buttons: "Critical (2)", "High (5)", etc.
- Better empty state: "No alerts yet. Alerts are generated automatically when whale activity or rekt incidents match your watchlist."

- [ ] **Step 3: Run all frontend tests**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local/web && npx vitest run`

Expected: All pass.

- [ ] **Step 4: Run all backend tests**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/ -v`

Expected: All pass (218+ tests).

- [ ] **Step 5: Commit**

```bash
git add web/app/dashboard/page.tsx web/app/alerts/page.tsx
git commit -m "feat: polish Dashboard and Alerts pages"
```

---

## Summary

| Task | Description | Backend | Frontend |
|------|-------------|---------|----------|
| 1 | Enrich Smart Money overview | ✅ | |
| 2 | Wallet profile + forensics endpoints | ✅ | |
| 3 | Audit findings estimation | ✅ | |
| 4 | Rekt database enhancement | ✅ | ✅ |
| 5 | Frontend types, API, hooks | | ✅ |
| 6 | Smart Money Hub rewrite | | ✅ |
| 7 | Flows page rewrite | | ✅ |
| 8 | Wallet Lookup rewrite | | ✅ |
| 9 | Whales page enhancement | | ✅ |
| 10 | Audits page enhancement | | ✅ |
| 11 | Dashboard + Alerts polish | | ✅ |
