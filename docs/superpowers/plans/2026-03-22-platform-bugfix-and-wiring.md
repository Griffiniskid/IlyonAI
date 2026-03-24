# Platform Bugfix and Feature Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every broken feature across Smart Money, Protect, Portfolio, and Settings so all shipped pages work end-to-end.

**Architecture:** Targeted fixes to existing backend route handlers and frontend components. No new frameworks, no architectural changes. Each task patches a specific broken surface by fixing constructor bugs, adding missing data fetches, wiring existing-but-unused services, or improving UI display logic.

**Tech Stack:** Python 3.11 / aiohttp (backend), Next.js 14 / React / TypeScript (frontend), pytest (backend tests), vitest (frontend tests)

**Spec:** `docs/superpowers/specs/2026-03-22-platform-bugfix-and-wiring-design.md`

**All file paths are relative to:** `.worktrees/main-local/`

---

### Task 1: Fix SolanaClient async context manager

**Files:**
- Modify: `src/data/solana.py:83-107`
- Test: `tests/test_solana_client_context.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_solana_client_context.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock

from src.data.solana import SolanaClient


@pytest.mark.asyncio
async def test_solana_client_async_context_manager():
    """SolanaClient must support async with and call close() on exit."""
    with patch.object(SolanaClient, "close", new_callable=AsyncMock) as mock_close:
        async with SolanaClient(rpc_url="https://example.com") as client:
            assert isinstance(client, SolanaClient)
        mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_solana_client_context_manager_calls_close_on_error():
    """SolanaClient must call close() even when body raises."""
    with patch.object(SolanaClient, "close", new_callable=AsyncMock) as mock_close:
        with pytest.raises(RuntimeError):
            async with SolanaClient(rpc_url="https://example.com"):
                raise RuntimeError("boom")
        mock_close.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .worktrees/main-local && python -m pytest tests/test_solana_client_context.py -v`
Expected: FAIL — `TypeError: 'SolanaClient' object does not support the asynchronous context manager protocol`

- [ ] **Step 3: Add `__aenter__` and `__aexit__` to SolanaClient**

In `src/data/solana.py`, add these methods to the `SolanaClient` class after the `close()` method (after line 107):

```python
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .worktrees/main-local && python -m pytest tests/test_solana_client_context.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd .worktrees/main-local && git add src/data/solana.py tests/test_solana_client_context.py && git commit -m "fix: add async context manager to SolanaClient"
```

---

### Task 2: Fix smart money overview route

**Files:**
- Modify: `src/api/routes/smart_money.py:1-79`
- Test: `tests/api/test_smart_money_routes.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_smart_money_routes.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.api.routes.smart_money import setup_smart_money_routes


@pytest.mark.asyncio
async def test_smart_money_overview_returns_data():
    """Overview should return flow data when SolanaClient works."""
    mock_transactions = [
        {"type": "buy", "amount_usd": 50000, "chain": "solana", "wallet_address": "Abc123", "wallet_label": "Whale A"},
        {"type": "sell", "amount_usd": 30000, "chain": "solana", "wallet_address": "Def456", "wallet_label": None},
    ]

    app = web.Application()
    setup_smart_money_routes(app)

    with patch("src.api.routes.smart_money.SolanaClient") as MockClient:
        instance = AsyncMock()
        instance.get_whale_transactions = AsyncMock(return_value=mock_transactions)
        instance.close = AsyncMock()
        MockClient.return_value = instance
        # Make it work as async context manager
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "ok"
            data = body["data"]
            assert data["inflow_usd"] == 50000
            assert data["outflow_usd"] == 30000
            assert data["net_flow_usd"] == 20000
            assert len(data["top_buyers"]) == 1
            assert len(data["top_sellers"]) == 1
        finally:
            await client.close()
            await server.close()


@pytest.mark.asyncio
async def test_smart_money_overview_error_returns_error_envelope():
    """Overview should return error envelope when SolanaClient fails, not silent zeros."""
    app = web.Application()
    setup_smart_money_routes(app)

    with patch("src.api.routes.smart_money.SolanaClient") as MockClient:
        MockClient.side_effect = Exception("RPC unavailable")

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/smart-money/overview")
            assert resp.status == 502
            body = await resp.json()
            assert body["status"] == "error"
        finally:
            await client.close()
            await server.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .worktrees/main-local && python -m pytest tests/api/test_smart_money_routes.py -v`
Expected: FAIL — SolanaClient called without args, no context manager

- [ ] **Step 3: Rewrite `get_smart_money_overview` with proper config and error handling**

Replace the full content of `src/api/routes/smart_money.py` with:

```python
"""Smart money API routes."""

import logging
from datetime import datetime

from aiohttp import web

from src.api.response_envelope import envelope_response, envelope_error_response
from src.api.schemas.responses import SmartMoneyOverviewResponse
from src.config import settings
from src.data.solana import SolanaClient

logger = logging.getLogger(__name__)


async def get_smart_money_overview(request: web.Request) -> web.Response:
    top_buyers = []
    top_sellers = []
    flows = []
    net_flow_usd = 0.0
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

                flow_item = {
                    "direction": direction,
                    "amount_usd": amount,
                    "chain": chain,
                }
                flows.append(flow_item)

                wallet = str(
                    tx.get("wallet_address")
                    or tx.get("wallet", "")
                    or tx.get("signer", "")
                    or ""
                )
                label = tx.get("wallet_label") or tx.get("label")

                if direction == "inflow":
                    inflow_usd += amount
                    if wallet:
                        top_buyers.append({
                            "wallet_address": wallet,
                            "label": label,
                            "amount_usd": amount,
                        })
                else:
                    outflow_usd += amount
                    if wallet:
                        top_sellers.append({
                            "wallet_address": wallet,
                            "label": label,
                            "amount_usd": amount,
                        })
    except Exception as e:
        logger.error(f"Smart money overview failed: {e}")
        return envelope_error_response(
            f"Failed to fetch smart money data: {e}",
            code="SMART_MONEY_FETCH_FAILED",
            http_status=502,
            meta={"surface": "smart_money_overview"},
        )

    top_buyers.sort(key=lambda x: x["amount_usd"], reverse=True)
    top_sellers.sort(key=lambda x: x["amount_usd"], reverse=True)
    net_flow_usd = inflow_usd - outflow_usd

    payload = SmartMoneyOverviewResponse(
        net_flow_usd=net_flow_usd,
        inflow_usd=inflow_usd,
        outflow_usd=outflow_usd,
        top_buyers=top_buyers[:10],
        top_sellers=top_sellers[:10],
        flows=flows[:50],
        updated_at=datetime.utcnow().isoformat(),
    ).model_dump(mode="json")

    return envelope_response(payload, meta={"surface": "smart_money_overview"})


def setup_smart_money_routes(app: web.Application):
    app.router.add_get("/api/v1/smart-money/overview", get_smart_money_overview)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .worktrees/main-local && python -m pytest tests/api/test_smart_money_routes.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd .worktrees/main-local && git add src/api/routes/smart_money.py tests/api/test_smart_money_routes.py && git commit -m "fix: wire SolanaClient with config in smart money route, add error envelope"
```

---

### Task 3: Add missing navigation items

**Files:**
- Modify: `web/components/layout/header.tsx:8-33`

- [ ] **Step 1: Update imports to include new icons**

In `web/components/layout/header.tsx`, replace the icon imports (lines 8-17):

```typescript
import {
  LayoutDashboard,
  TrendingUp,
  Wallet,
  Fish,
  Menu,
  X,
  Shield,
  Settings,
  DollarSign,
  Flame,
  Bell,
} from "lucide-react";
```

- [ ] **Step 2: Update the navItems array**

Replace the `navItems` array (lines 26-33) with:

```typescript
const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/trending", label: "Trending", icon: TrendingUp },
  { href: "/smart-money", label: "Smart Money", icon: DollarSign },
  { href: "/shield", label: "Shield", icon: Shield },
  { href: "/rekt", label: "Rekt", icon: Flame },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/portfolio", label: "Portfolio", icon: Wallet },
  { href: "/whales", label: "Whales", icon: Fish },
  { href: "/settings", label: "Settings", icon: Settings },
];
```

- [ ] **Step 3: Commit**

```bash
cd .worktrees/main-local && git add web/components/layout/header.tsx && git commit -m "feat: add Smart Money, Rekt, Alerts to navigation"
```

---

### Task 4: Shield graceful degradation for missing API keys

**Files:**
- Modify: `src/shield/approval_scanner.py:90-115`
- Modify: `src/api/routes/shield.py` (add status endpoint)
- Test: `tests/api/test_shield_status.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_shield_status.py`:

```python
import pytest
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.api.routes.shield import setup_shield_routes


@pytest.mark.asyncio
async def test_shield_status_shows_chain_availability():
    """Shield status endpoint should report which chains have API keys configured."""
    mock_settings = type("S", (), {
        "etherscan_api_key": "real-key",
        "bscscan_api_key": "",
        "polygonscan_api_key": None,
        "arbiscan_api_key": "real-key",
        "basescan_api_key": None,
        "optimism_etherscan_api_key": None,
        "snowtrace_api_key": None,
    })()

    with patch("src.api.routes.shield.settings", mock_settings):
        app = web.Application()
        setup_shield_routes(app)

        server = TestServer(app)
        client = TestClient(server)
        await server.start_server()

        try:
            resp = await client.get("/api/v1/shield/status")
            assert resp.status == 200
            body = await resp.json()
            chains = body["data"]["chains"]
            assert chains["ethereum"]["available"] is True
            assert chains["bsc"]["available"] is False
            assert chains["arbitrum"]["available"] is True
        finally:
            await client.close()
            await server.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .worktrees/main-local && python -m pytest tests/api/test_shield_status.py -v`
Expected: FAIL — no `/api/v1/shield/status` route exists

- [ ] **Step 3: Fix the API key fallback in `approval_scanner.py`**

In `src/shield/approval_scanner.py`, replace line 114:

```python
            "apikey": api_key or "YourApiKeyToken",
```

with:

```python
            "apikey": api_key,
```

And add a guard at the top of `get_evm_approvals` after line 98, add:

```python
        if not api_key:
            logger.info(f"No API key configured for {chain.display_name}, skipping scan")
            return []
```

- [ ] **Step 4: Add shield status endpoint**

First, ensure `src/api/routes/shield.py` has the required imports. Add these if not already present:

```python
from src.config import settings
from src.api.response_envelope import envelope_response
```

Then read `src/api/routes/shield.py` to find the `setup_shield_routes` function. Add a new handler and register it:

```python
async def get_shield_status(request: web.Request) -> web.Response:
    """GET /api/v1/shield/status — report per-chain API key availability."""
    chain_keys = {
        "ethereum": settings.etherscan_api_key,
        "bsc": settings.bscscan_api_key,
        "polygon": settings.polygonscan_api_key,
        "arbitrum": settings.arbiscan_api_key,
        "base": settings.basescan_api_key,
        "optimism": settings.optimism_etherscan_api_key,
        "avalanche": settings.snowtrace_api_key,
    }
    chains = {}
    for chain_name, key in chain_keys.items():
        available = bool(key and key.strip())
        chains[chain_name] = {
            "available": available,
            "reason": None if available else "API key not configured",
        }
    return envelope_response({"chains": chains}, meta={"surface": "shield_status"})
```

Register it in `setup_shield_routes`:

```python
    app.router.add_get("/api/v1/shield/status", get_shield_status)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd .worktrees/main-local && python -m pytest tests/api/test_shield_status.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd .worktrees/main-local && git add src/shield/approval_scanner.py src/api/routes/shield.py tests/api/test_shield_status.py && git commit -m "fix: shield graceful degradation for missing API keys, add status endpoint"
```

---

### Task 5: Audit database live fetch from DefiLlama

**Files:**
- Modify: `src/intel/rekt_database.py:303-365`
- Test: `tests/test_audit_database.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_audit_database.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.intel.rekt_database import AuditDatabase


@pytest.mark.asyncio
async def test_audit_database_fetches_from_defillama():
    """AuditDatabase should supplement seed data with DefiLlama protocol audits."""
    mock_protocols = [
        {
            "name": "Lido",
            "audits": "2",
            "audit_links": ["https://example.com/lido-audit.pdf"],
            "audit_note": "Audited by Quantstamp",
            "chains": ["Ethereum"],
            "category": "Liquid Staking",
        },
        {
            "name": "Uniswap V3",  # duplicate with seed data — should be deduplicated
            "audits": "3",
            "audit_links": ["https://example.com/uni-audit.pdf"],
            "chains": ["Ethereum"],
        },
    ]

    db = AuditDatabase()
    mock_session = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=mock_protocols)
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_session.get.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch.object(db, "_get_session", return_value=mock_session):
        audits = await db.get_audits()

    # Should have seed data (4) + 1 new from DefiLlama (Lido) — Uniswap V3 deduplicated
    protocol_names = [a["protocol"] for a in audits]
    assert "Lido" in protocol_names
    assert len(audits) > 4


@pytest.mark.asyncio
async def test_audit_database_cache_prevents_refetch():
    """AuditDatabase should cache DefiLlama results for 1 hour."""
    db = AuditDatabase()
    mock_session = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=[])
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_session.get.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch.object(db, "_get_session", return_value=mock_session):
        await db.get_audits()
        await db.get_audits()  # second call should use cache

    # get() should only be called once
    assert mock_session.get.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .worktrees/main-local && python -m pytest tests/test_audit_database.py -v`
Expected: FAIL — `AuditDatabase.get_audits` returns only seed data

- [ ] **Step 3: Add live fetch to AuditDatabase**

Replace the `AuditDatabase` class in `src/intel/rekt_database.py` (lines 303-365) with:

```python
class AuditDatabase:
    """
    Database of smart contract security audits.

    Combines curated seed data with live data from DefiLlama protocols endpoint.
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._live_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_ts: float = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self._session

    async def _fetch_defillama_audits(self) -> List[Dict[str, Any]]:
        """Fetch protocol audit metadata from DefiLlama."""
        import time
        now = time.time()
        if self._live_cache is not None and (now - self._cache_ts) < 3600:
            return self._live_cache

        try:
            session = await self._get_session()
            async with session.get("https://api.llama.fi/protocols") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    audited = []
                    if isinstance(data, list):
                        for proto in data:
                            audit_links = proto.get("audit_links") or []
                            audits_count = proto.get("audits")
                            if not audit_links and not audits_count:
                                continue
                            auditor = "Unknown"
                            audit_note = proto.get("audit_note") or ""
                            if audit_note:
                                # Try to extract auditor name from note
                                for firm in ["Trail of Bits", "OpenZeppelin", "PeckShield",
                                             "ChainSecurity", "Quantstamp", "CertiK", "Halborn",
                                             "Consensys Diligence", "Sherlock", "Code4rena",
                                             "Spearbit", "Cyfrin", "MixBytes"]:
                                    if firm.lower() in audit_note.lower():
                                        auditor = firm
                                        break
                            audited.append({
                                "id": f"llama-{proto.get('name', '').lower().replace(' ', '-')}",
                                "protocol": proto.get("name", "Unknown"),
                                "auditor": auditor,
                                "date": "",
                                "report_url": audit_links[0] if audit_links else "",
                                "severity_findings": {},
                                "verdict": "PASS" if audits_count and str(audits_count) != "0" else "UNKNOWN",
                                "chains": proto.get("chains") or [],
                                "source": "DefiLlama",
                            })
                    self._live_cache = audited
                    self._cache_ts = now
                    return self._live_cache
        except Exception as e:
            logger.warning(f"Failed to fetch DefiLlama audit data: {e}")

        return []

    async def get_audits(
        self,
        protocol: Optional[str] = None,
        auditor: Optional[str] = None,
        chain: Optional[str] = None,
        verdict: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query audit records with optional filters."""
        audits: List[Dict[str, Any]] = [dict(a) for a in KNOWN_AUDITS]

        # Supplement with live DefiLlama data
        live = await self._fetch_defillama_audits()
        seed_protocols = {a["protocol"].lower() for a in audits}
        for audit in live:
            if audit["protocol"].lower() not in seed_protocols:
                audits.append(audit)

        if protocol:
            audits = [
                a for a in audits
                if protocol.lower() in (a.get("protocol") or "").lower()
            ]
        if auditor:
            audits = [
                a for a in audits
                if auditor.lower() in (a.get("auditor") or "").lower()
            ]
        if chain:
            audits = [
                a for a in audits
                if any(chain.lower() in c.lower() for c in (a.get("chains") or []))
            ]
        if verdict:
            audits = [
                a for a in audits
                if (a.get("verdict") or "").upper() == verdict.upper()
            ]

        audits.sort(key=lambda a: a.get("date") or "", reverse=True)
        return audits[:limit]

    async def get_audit(self, audit_id: str) -> Optional[Dict[str, Any]]:
        """Get a single audit record by ID."""
        all_audits = await self.get_audits(limit=10000)
        for a in all_audits:
            if a.get("id") == audit_id:
                return a
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .worktrees/main-local && python -m pytest tests/test_audit_database.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd .worktrees/main-local && git add src/intel/rekt_database.py tests/test_audit_database.py && git commit -m "feat: add DefiLlama live fetch to AuditDatabase with 1hr cache"
```

---

### Task 6: Expand rekt seed data and improve severity classification

**Files:**
- Modify: `src/intel/rekt_database.py:19-137`

- [ ] **Step 1: Add more seed incidents to `KNOWN_REKT_INCIDENTS`**

After the existing 9 entries in `KNOWN_REKT_INCIDENTS` (before the closing `]` on line 137), add:

```python
    {
        "id": "ftx-2022",
        "name": "FTX Exchange",
        "date": "2022-11-11",
        "amount_usd": 477_000_000,
        "protocol": "FTX",
        "chains": ["Ethereum", "Solana", "BSC"],
        "attack_type": "Unauthorized Access / Key Compromise",
        "description": "Following FTX's bankruptcy filing, approximately $477M was drained from FTX wallets in what appeared to be unauthorized access to exchange wallets.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "multichain-2023",
        "name": "Multichain Bridge",
        "date": "2023-07-06",
        "amount_usd": 126_000_000,
        "protocol": "Multichain",
        "chains": ["Ethereum", "Fantom"],
        "attack_type": "Key Compromise / Insider",
        "description": "Assets were unexpectedly moved from Multichain bridge contracts after the CEO was reportedly detained, suggesting compromised admin keys.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "harmony-2022",
        "name": "Harmony Horizon Bridge",
        "date": "2022-06-23",
        "amount_usd": 100_000_000,
        "protocol": "Harmony",
        "chains": ["Ethereum"],
        "attack_type": "Private Key Compromise",
        "description": "Attackers compromised 2/5 multi-sig keys on the Horizon bridge to drain ~$100M in various tokens.",
        "post_mortem_url": "https://medium.com/harmony-one/harmonys-horizon-bridge-hack-1e8d283b6d66",
        "funds_recovered": False,
        "severity": "HIGH",
    },
    {
        "id": "wintermute-2022",
        "name": "Wintermute",
        "date": "2022-09-20",
        "amount_usd": 160_000_000,
        "protocol": "Wintermute",
        "chains": ["Ethereum"],
        "attack_type": "Vanity Address Exploit",
        "description": "DeFi operations wallet compromised through a Profanity vanity address generator vulnerability, allowing attacker to derive the private key.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "cream-2021",
        "name": "Cream Finance",
        "date": "2021-10-27",
        "amount_usd": 130_000_000,
        "protocol": "Cream Finance",
        "chains": ["Ethereum"],
        "attack_type": "Flash Loan / Oracle Manipulation",
        "description": "Third exploit of Cream Finance using flash loans to manipulate price oracle and drain lending pools.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "badger-2021",
        "name": "BadgerDAO",
        "date": "2021-12-02",
        "amount_usd": 120_000_000,
        "protocol": "BadgerDAO",
        "chains": ["Ethereum"],
        "attack_type": "Frontend / Supply Chain Attack",
        "description": "Attacker injected malicious scripts via a compromised Cloudflare API key, tricking users into approving token transfers.",
        "post_mortem_url": "https://badger.com/blog/technical-post-mortem",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "vulcan-2023",
        "name": "Vulcan Forged",
        "date": "2021-12-13",
        "amount_usd": 140_000_000,
        "protocol": "Vulcan Forged",
        "chains": ["Ethereum", "Polygon"],
        "attack_type": "Private Key Compromise",
        "description": "Attacker obtained private keys of 96 wallets from the platform's key management system and drained PYR tokens.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "cashio-2022",
        "name": "Cashio",
        "date": "2022-03-23",
        "amount_usd": 52_000_000,
        "protocol": "Cashio",
        "chains": ["Solana"],
        "attack_type": "Infinite Mint / Validation Bug",
        "description": "Attacker exploited missing collateral validation to mint unlimited CASH stablecoin and drain liquidity pools.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "HIGH",
    },
    {
        "id": "parity-2017",
        "name": "Parity Wallet",
        "date": "2017-11-06",
        "amount_usd": 280_000_000,
        "protocol": "Parity Technologies",
        "chains": ["Ethereum"],
        "attack_type": "Self-Destruct / Library Bug",
        "description": "A user accidentally triggered selfdestruct on the shared Parity multi-sig library contract, permanently freezing ~$280M in ETH across 587 wallets.",
        "post_mortem_url": "https://www.parity.io/blog/a-postmortem-on-the-parity-multi-sig-library-self-destruct",
        "funds_recovered": False,
        "severity": "CRITICAL",
    },
    {
        "id": "dao-2016",
        "name": "The DAO",
        "date": "2016-06-17",
        "amount_usd": 60_000_000,
        "protocol": "The DAO",
        "chains": ["Ethereum"],
        "attack_type": "Reentrancy",
        "description": "The original reentrancy exploit that drained ~$60M from The DAO's investment fund, leading to the Ethereum hard fork.",
        "post_mortem_url": "",
        "funds_recovered": True,
        "severity": "HIGH",
    },
    {
        "id": "kyberswap-2023",
        "name": "KyberSwap Elastic",
        "date": "2023-11-22",
        "amount_usd": 48_800_000,
        "protocol": "KyberSwap",
        "chains": ["Ethereum", "Arbitrum", "Optimism", "Polygon", "Base", "Avalanche", "BSC"],
        "attack_type": "Tick Manipulation / Precision Exploit",
        "description": "Attacker exploited a precision rounding issue in KyberSwap Elastic's concentrated liquidity math to drain pools across 7 chains simultaneously.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "HIGH",
    },
    {
        "id": "atomic-wallet-2023",
        "name": "Atomic Wallet",
        "date": "2023-06-03",
        "amount_usd": 100_000_000,
        "protocol": "Atomic Wallet",
        "chains": ["Ethereum", "Bitcoin", "BSC"],
        "attack_type": "Key Compromise / Supply Chain",
        "description": "Users' private keys were compromised, likely through a dependency vulnerability or server-side key storage breach, draining wallets across multiple chains.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "HIGH",
    },
    {
        "id": "level-finance-2023",
        "name": "Level Finance",
        "date": "2023-05-02",
        "amount_usd": 1_100_000,
        "protocol": "Level Finance",
        "chains": ["BSC"],
        "attack_type": "Referral Logic Bug",
        "description": "Attacker exploited a bug in the referral reward claiming function to repeatedly claim LVL token rewards.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "MEDIUM",
    },
    {
        "id": "platypus-2023",
        "name": "Platypus Finance",
        "date": "2023-02-16",
        "amount_usd": 8_500_000,
        "protocol": "Platypus Finance",
        "chains": ["Avalanche"],
        "attack_type": "Flash Loan / Logic Bug",
        "description": "Attacker used flash loans to exploit a solvency check flaw in the stablecoin USP minting mechanism.",
        "post_mortem_url": "",
        "funds_recovered": True,
        "severity": "MEDIUM",
    },
    {
        "id": "radiant-2024",
        "name": "Radiant Capital",
        "date": "2024-10-16",
        "amount_usd": 50_000_000,
        "protocol": "Radiant Capital",
        "chains": ["Arbitrum", "BSC"],
        "attack_type": "Multi-sig Compromise",
        "description": "Attackers compromised 3/11 multi-sig signers through malware and used the access to drain lending pools on two chains.",
        "post_mortem_url": "",
        "funds_recovered": False,
        "severity": "HIGH",
    },
```

- [ ] **Step 2: Update severity classification in `_normalize_llama_hack`**

In `src/intel/rekt_database.py`, update the severity line in `_normalize_llama_hack` (line 236) to use the 4-tier spec:

```python
            "severity": (
                "CRITICAL" if amount > 100_000_000
                else "HIGH" if amount > 10_000_000
                else "MEDIUM" if amount > 1_000_000
                else "LOW"
            ),
```

- [ ] **Step 3: Run existing tests to verify no regressions**

Run: `cd .worktrees/main-local && python -m pytest tests/ -v --timeout=30 -x`
Expected: All existing tests pass

- [ ] **Step 4: Commit**

```bash
cd .worktrees/main-local && git add src/intel/rekt_database.py && git commit -m "feat: expand rekt seed data to 24 incidents, improve severity heuristic"
```

---

### Task 7: Wire entity backend routes and frontend page

**Files:**
- Create: `src/api/routes/entity.py`
- Modify: `src/api/app.py` (register routes)
- Modify: `web/app/entity/[id]/page.tsx`
- Create: `web/app/entity/page.tsx` (entity list)
- Test: `tests/api/test_entity_routes.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_entity_routes.py`:

```python
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from src.smart_money.graph_store import GraphStore


@pytest.mark.asyncio
async def test_entity_list_returns_entities():
    """Entity list endpoint should return entities from graph store."""
    from src.api.routes.entity import setup_entity_routes, GRAPH_STORE_KEY

    app = web.Application()
    graph = GraphStore()
    entity_id = graph.link_wallets(["wallet1", "wallet2"], reason="co-funded")

    setup_entity_routes(app, graph_store=graph)

    server = TestServer(app)
    client = TestClient(server)
    await server.start_server()

    try:
        resp = await client.get("/api/v1/entities")
        assert resp.status == 200
        body = await resp.json()
        entities = body["data"]["entities"]
        assert len(entities) == 1
        assert entities[0]["id"] == entity_id
        assert set(entities[0]["wallets"]) == {"wallet1", "wallet2"}
    finally:
        await client.close()
        await server.close()


@pytest.mark.asyncio
async def test_entity_detail_returns_profile():
    """Entity detail endpoint should return entity profile."""
    from src.api.routes.entity import setup_entity_routes, GRAPH_STORE_KEY

    app = web.Application()
    graph = GraphStore()
    entity_id = graph.link_wallets(["walletA"], reason="whale-cluster")

    setup_entity_routes(app, graph_store=graph)

    server = TestServer(app)
    client = TestClient(server)
    await server.start_server()

    try:
        resp = await client.get(f"/api/v1/entities/{entity_id}")
        assert resp.status == 200
        body = await resp.json()
        assert body["data"]["id"] == entity_id
        assert body["data"]["reason"] == "whale-cluster"

        # 404 for unknown entity
        resp404 = await client.get("/api/v1/entities/entity-nonexistent")
        assert resp404.status == 404
    finally:
        await client.close()
        await server.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .worktrees/main-local && python -m pytest tests/api/test_entity_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.api.routes.entity'`

- [ ] **Step 3: Create `src/api/routes/entity.py`**

```python
"""Entity graph API routes."""

import logging

from aiohttp import web

from src.api.response_envelope import envelope_response, envelope_error_response
from src.smart_money.graph_store import GraphStore

logger = logging.getLogger(__name__)

GRAPH_STORE_KEY = web.AppKey("graph_store", GraphStore)


async def list_entities(request: web.Request) -> web.Response:
    """GET /api/v1/entities — list all known entities."""
    graph: GraphStore = request.app[GRAPH_STORE_KEY]
    entities = []
    for entity_id, record in graph.entities.items():
        wallets = graph.get_wallets_for_entity(entity_id)
        reason = graph.get_link_reason_for_entity(entity_id)
        entities.append({
            "id": entity_id,
            "wallets": wallets,
            "reason": reason,
            "wallet_count": len(wallets),
        })
    return envelope_response({"entities": entities}, meta={"surface": "entity_list"})


async def get_entity(request: web.Request) -> web.Response:
    """GET /api/v1/entities/{id} — get entity profile."""
    entity_id = request.match_info["id"]
    graph: GraphStore = request.app[GRAPH_STORE_KEY]

    wallets = graph.get_wallets_for_entity(entity_id)
    if not wallets:
        return envelope_error_response(
            f"Entity {entity_id} not found",
            code="ENTITY_NOT_FOUND",
            http_status=404,
        )

    reason = graph.get_link_reason_for_entity(entity_id)
    return envelope_response({
        "id": entity_id,
        "wallets": wallets,
        "reason": reason,
        "wallet_count": len(wallets),
    }, meta={"surface": "entity_profile"})


def setup_entity_routes(app: web.Application, graph_store: GraphStore | None = None):
    app[GRAPH_STORE_KEY] = graph_store or GraphStore()
    app.router.add_get("/api/v1/entities", list_entities)
    app.router.add_get("/api/v1/entities/{id}", get_entity)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .worktrees/main-local && python -m pytest tests/api/test_entity_routes.py -v`
Expected: 2 passed

- [ ] **Step 5: Register entity routes in `src/api/app.py`**

Add import at the top of `src/api/app.py` (near line 30):

```python
from src.api.routes.entity import setup_entity_routes
```

`app.py` has **two** route registration blocks (around lines 195 and 261). Add `setup_entity_routes(app)` after `setup_smart_money_routes(app)` in **both** blocks:

```python
    setup_smart_money_routes(app)
    setup_entity_routes(app)
```

- [ ] **Step 6: Rewrite `web/app/entity/[id]/page.tsx`**

Replace the stub with a functional page:

```typescript
"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { GlassCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loader2, AlertCircle, Users, ArrowRight, Copy } from "lucide-react";
import { useState } from "react";

async function fetchEntity(id: string) {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/entities/${id}`);
  const json = await res.json();
  if (json.status !== "ok") throw new Error(json.errors?.[0]?.message ?? "Entity not found");
  return json.data;
}

function truncateAddress(addr: string) {
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

export default function EntityPage() {
  const params = useParams();
  const id = Array.isArray(params.id) ? params.id[0] : params.id ?? "";
  const { data, isLoading, error } = useQuery({
    queryKey: ["entity", id],
    queryFn: () => fetchEntity(id),
    enabled: !!id,
  });
  const [copied, setCopied] = useState<string | null>(null);

  const handleCopy = async (addr: string) => {
    await navigator.clipboard.writeText(addr);
    setCopied(addr);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <section className="container mx-auto max-w-4xl px-4 py-8">
      <Link href="/entity" className="text-sm text-muted-foreground hover:text-foreground mb-2 inline-block">
        ← Back to Entities
      </Link>
      <div className="flex items-center gap-3 mt-2 mb-6">
        <Users className="h-8 w-8 text-emerald-500" />
        <h1 className="text-3xl font-bold">Entity Profile</h1>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
        </div>
      ) : error ? (
        <GlassCard className="text-center py-12">
          <AlertCircle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">Entity not found or unavailable.</p>
        </GlassCard>
      ) : data ? (
        <>
          <div className="grid gap-4 md:grid-cols-3 mb-8">
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Entity ID</p>
              <code className="text-sm font-mono">{data.id}</code>
            </GlassCard>
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Linked Wallets</p>
              <p className="text-2xl font-semibold">{data.wallet_count}</p>
            </GlassCard>
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Link Reason</p>
              <Badge variant="outline">{data.reason || "Unknown"}</Badge>
            </GlassCard>
          </div>

          <GlassCard className="p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3">Associated Wallets</h2>
            <div className="space-y-2">
              {(data.wallets ?? []).map((wallet: string) => (
                <div key={wallet} className="flex items-center justify-between text-sm">
                  <Link href={`/wallet/${wallet}`} className="font-mono text-primary hover:underline">
                    {truncateAddress(wallet)}
                  </Link>
                  <Button variant="ghost" size="sm" onClick={() => handleCopy(wallet)}>
                    <Copy className="h-3 w-3 mr-1" />
                    {copied === wallet ? "Copied" : "Copy"}
                  </Button>
                </div>
              ))}
            </div>
          </GlassCard>

          <div className="flex gap-3 mt-6">
            <Button asChild variant="outline" size="sm">
              <Link href="/smart-money">
                Smart Money Hub
                <ArrowRight className="h-4 w-4 ml-2" />
              </Link>
            </Button>
          </div>
        </>
      ) : null}
    </section>
  );
}
```

- [ ] **Step 7: Create `web/app/entity/page.tsx` entity list page**

```typescript
"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { GlassCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, AlertCircle, Users, ArrowRight } from "lucide-react";

async function fetchEntities() {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/entities`);
  const json = await res.json();
  if (json.status !== "ok") throw new Error("Failed to load entities");
  return json.data.entities ?? [];
}

function truncateAddress(addr: string) {
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

export default function EntityListPage() {
  const { data: entities, isLoading, error } = useQuery({
    queryKey: ["entities"],
    queryFn: fetchEntities,
  });

  return (
    <section className="container mx-auto max-w-6xl px-4 py-8">
      <div className="flex items-center gap-3 mb-6">
        <Users className="h-8 w-8 text-emerald-500" />
        <h1 className="text-3xl font-bold">Entity Explorer</h1>
      </div>
      <p className="text-sm text-muted-foreground mb-6">
        Wallet clusters identified through flow analysis and behavioral correlation.
      </p>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
        </div>
      ) : error ? (
        <GlassCard className="text-center py-12">
          <AlertCircle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">Unable to load entity data.</p>
        </GlassCard>
      ) : !entities || entities.length === 0 ? (
        <GlassCard className="text-center py-12">
          <Users className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">No entities discovered yet.</p>
          <p className="text-xs text-muted-foreground mt-2">
            Entities are built from smart money flow data. As flows are processed, wallet clusters will appear here.
          </p>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {entities.map((entity: any) => (
            <Link
              key={entity.id}
              href={`/entity/${entity.id}`}
              className="block rounded-xl border border-border/60 bg-card/40 p-4 hover:bg-card/60 transition"
            >
              <div className="flex items-center justify-between">
                <div>
                  <code className="text-sm font-mono">{entity.id}</code>
                  <div className="flex gap-2 mt-2">
                    <Badge variant="outline">{entity.wallet_count} wallets</Badge>
                    <Badge variant="secondary">{entity.reason || "Unknown"}</Badge>
                  </div>
                </div>
                <ArrowRight className="h-5 w-5 text-muted-foreground" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 8: Commit**

```bash
cd .worktrees/main-local && git add src/api/routes/entity.py src/api/app.py web/app/entity/page.tsx "web/app/entity/[id]/page.tsx" tests/api/test_entity_routes.py && git commit -m "feat: wire entity routes and frontend pages"
```

---

### Task 8: Fix portfolio capability display and PnL estimation

**Files:**
- Modify: `src/api/routes/portfolio.py:303-322` (capability overrides)
- Modify: `src/api/routes/portfolio.py:186-187,223-224,289-290` (PnL)
- Modify: `web/components/portfolio/risk-breakdown.tsx`
- Modify: `web/components/portfolio/chain-exposure-table.tsx`

- [ ] **Step 1: Fix the inline SolanaCapabilitiesProvider in portfolio.py**

In `src/api/routes/portfolio.py`, replace the `SolanaCapabilitiesProvider` class (lines 303-315) with one that reports `spot_holdings` as available:

```python
    class SolanaCapabilitiesProvider:
        def capability_overrides(self):
            return {
                "solana": {
                    "spot_holdings": {"supported": True, "reason": None},
                    "lp_positions": {"supported": False, "reason": "LP position tracking requires dedicated Solana DEX integrations"},
                    "lending_positions": {"supported": False, "reason": "Lending protocol integrations not yet available"},
                    "vault_positions": {"supported": False, "reason": "Vault integrations not yet available"},
                    "risk_decomposition": {"supported": False, "reason": "Requires position-level risk modeling"},
                    "alert_coverage": {"supported": False, "reason": "Alert system integration pending"},
                }
            }
```

- [ ] **Step 2: Improve MoralisClient capability reason strings**

`MoralisClient` at `src/data/moralis.py:80-93` already has a `capability_overrides()` method that correctly reports `spot_holdings: supported: True` for all 7 EVM chains. The aggregator at `portfolio.py:318` already passes `MoralisClient()` as a provider — no wrapper needed.

However, the generic reason string "Moralis wallet endpoint currently provides spot holdings only" is repeated for all 5 unsupported capabilities across all chains, which is what causes the 35x "degraded" spam. Update `src/data/moralis.py` to use specific reasons per capability:

```python
    def capability_overrides(self) -> Dict[str, Dict[str, Dict[str, object]]]:
        """Return parity matrix overrides for Moralis-backed EVM chains."""
        overrides: Dict[str, Dict[str, Dict[str, object]]] = {}
        for chain in SUPPORTED_EVM_CHAINS:
            overrides[chain] = {
                "spot_holdings": {"supported": True, "reason": None},
                "lp_positions": {"supported": False, "reason": "LP tracking requires protocol-specific integrations"},
                "lending_positions": {"supported": False, "reason": "Lending protocol integrations not yet available"},
                "vault_positions": {"supported": False, "reason": "Vault integrations not yet available"},
                "risk_decomposition": {"supported": False, "reason": "Requires position-level risk modeling"},
                "alert_coverage": {"supported": False, "reason": "Alert system integration pending"},
            }
        return overrides
```

The aggregator construction line stays as-is since `MoralisClient()` is already passed.

- [ ] **Step 3: Add PnL estimation from token price_change_24h**

In `src/api/routes/portfolio.py`, replace the hardcoded PnL values. Find each `total_pnl_usd=0` and `total_pnl_percent=0` pair and replace with computed values. After the token aggregation loops (after `total_value += value_usd`), add:

```python
    # Estimate 24h PnL from token price changes
    total_pnl_usd = sum(
        t.balance_usd * (t.price_change_24h / 100)
        for t in all_tokens
        if t.price_change_24h and t.balance_usd
    )
    total_pnl_percent = (total_pnl_usd / total_value * 100) if total_value > 0 else 0
```

Then use `total_pnl_usd` and `total_pnl_percent` in the `PortfolioResponse` construction instead of 0.

Apply this pattern to all three locations where PnL is hardcoded (the aggregate endpoint ~line 220, the single wallet endpoint ~line 286, and the early-return case ~line 184 can stay at 0 since there are no tokens).

- [ ] **Step 4: Improve the risk-breakdown component to use collapsible grouping**

Replace `web/components/portfolio/risk-breakdown.tsx`:

```typescript
"use client";

import { useState } from "react";
import type { PortfolioChainMatrixResponse } from "@/types";
import { Badge } from "@/components/ui/badge";

interface RiskBreakdownProps {
  matrix: PortfolioChainMatrixResponse | null | undefined;
}

export function RiskBreakdown({ matrix }: RiskBreakdownProps) {
  const [expanded, setExpanded] = useState(false);

  const available = Object.entries(matrix?.chains ?? {}).flatMap(([chain, capabilityMap]) =>
    (matrix?.capabilities ?? [])
      .filter((capability) => capabilityMap[capability]?.state === "available")
      .map((capability) => ({ chain, capability }))
  );

  const degraded = Object.entries(matrix?.chains ?? {}).flatMap(([chain, capabilityMap]) =>
    (matrix?.capabilities ?? [])
      .map((capability) => {
        const cell = capabilityMap[capability];
        if (!cell || cell.state !== "degraded") return null;
        return { chain, capability, reason: cell.reason ?? "unknown" };
      })
      .filter((item): item is { chain: string; capability: string; reason: string } => item !== null)
  );

  // Deduplicate degraded reasons
  const uniqueReasons = Array.from(new Set(degraded.map((d) => d.reason)));

  return (
    <div className="space-y-3">
      {available.length > 0 && (
        <div>
          <p className="text-sm font-medium text-emerald-400 mb-1">
            {available.length} capabilities available
          </p>
          <div className="flex flex-wrap gap-1">
            {available.map((item) => (
              <Badge key={`${item.chain}-${item.capability}`} variant="outline" className="text-xs text-emerald-400 border-emerald-500/40">
                {item.chain}: {item.capability.replaceAll("_", " ")}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {degraded.length > 0 && (
        <div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-sm font-medium text-yellow-400 hover:text-yellow-300 transition cursor-pointer"
          >
            {degraded.length} capabilities degraded {expanded ? "▾" : "▸"}
          </button>
          {expanded && (
            <div className="mt-2 space-y-1 pl-2 border-l-2 border-yellow-500/30">
              {uniqueReasons.map((reason) => (
                <p key={reason} className="text-xs text-muted-foreground">
                  • {reason}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {available.length === 0 && degraded.length === 0 && (
        <p className="text-sm text-muted-foreground">No capability data available.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Improve chain-exposure-table to show meaningful labels**

Replace `web/components/portfolio/chain-exposure-table.tsx`:

```typescript
import type { PortfolioChainMatrixResponse } from "@/types";
import { Badge } from "@/components/ui/badge";

interface ChainExposureTableProps {
  matrix: PortfolioChainMatrixResponse | null | undefined;
}

function toTitleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function ChainExposureTable({ matrix }: ChainExposureTableProps) {
  const chains = Object.entries(matrix?.chains ?? {});
  const capabilities = matrix?.capabilities ?? [];

  if (chains.length === 0) {
    return <p className="text-sm text-muted-foreground">Chain exposure is unavailable.</p>;
  }

  const totalChains = chains.length;
  const activeChains = chains.filter(([, caps]) =>
    capabilities.some((c) => caps[c]?.state === "available")
  ).length;

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <Badge variant="outline" className="text-emerald-400 border-emerald-500/40">
          {activeChains} of {totalChains} chains active
        </Badge>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="py-2 pr-4 font-medium">Chain</th>
              <th className="py-2 pr-4 font-medium">Status</th>
              <th className="py-2 font-medium">Capabilities</th>
            </tr>
          </thead>
          <tbody>
            {chains.map(([chain, chainCapabilities]) => {
              const available = capabilities.filter(
                (capability) => chainCapabilities[capability]?.state === "available"
              );
              const degradedCount = capabilities.length - available.length;

              return (
                <tr key={chain} className="border-b border-border/60 last:border-b-0">
                  <td className="py-3 pr-4 font-medium">{toTitleCase(chain)}</td>
                  <td className="py-3 pr-4">
                    {available.length > 0 ? (
                      <Badge variant="outline" className="text-xs text-emerald-400 border-emerald-500/40">Active</Badge>
                    ) : (
                      <Badge variant="outline" className="text-xs text-yellow-400 border-yellow-500/40">Limited</Badge>
                    )}
                  </td>
                  <td className="py-3 text-muted-foreground text-xs">
                    {available.length > 0 && (
                      <span className="text-emerald-400">{available.map((c) => c.replaceAll("_", " ")).join(", ")}</span>
                    )}
                    {degradedCount > 0 && (
                      <span className="text-yellow-400 ml-2">({degradedCount} pending)</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Commit**

```bash
cd .worktrees/main-local && git add src/api/routes/portfolio.py src/data/moralis.py web/components/portfolio/risk-breakdown.tsx web/components/portfolio/chain-exposure-table.tsx && git commit -m "fix: portfolio capabilities display, PnL estimation from 24h price changes"
```

---

### Task 9: Bootstrap alert producer

**Files:**
- Create: `src/alerts/producer.py`
- Modify: `src/api/routes/alerts.py` (wire producer at startup)
- Modify: `src/api/app.py` (start producer task)
- Test: `tests/test_alert_producer.py` (create)

- [ ] **Step 0: Create `src/alerts/__init__.py`**

The `src/alerts/` directory is missing its `__init__.py` (other `src/` packages have one). Create an empty file:

```bash
touch src/alerts/__init__.py
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_alert_producer.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.alerts.store import InMemoryAlertStore
from src.alerts.producer import AlertProducer


@pytest.mark.asyncio
async def test_alert_producer_generates_whale_alerts():
    """Producer should generate alerts from whale transactions above threshold."""
    store = InMemoryAlertStore()
    producer = AlertProducer(store=store, whale_threshold_usd=100_000)

    mock_transactions = [
        {"type": "buy", "amount_usd": 500_000, "wallet_address": "whale1", "chain": "solana"},
        {"type": "sell", "amount_usd": 50_000, "wallet_address": "small1", "chain": "solana"},
    ]

    with patch("src.alerts.producer.SolanaClient") as MockClient:
        instance = AsyncMock()
        instance.get_whale_transactions = AsyncMock(return_value=mock_transactions)
        instance.close = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        await producer.check_whale_flows()

    alerts = store.list_alerts()
    # Only the $500K transaction should generate an alert (above $100K threshold)
    assert len(alerts) == 1
    assert "500" in alerts[0].title
    assert alerts[0].severity == "high"


@pytest.mark.asyncio
async def test_alert_producer_generates_rekt_alerts():
    """Producer should generate alerts for new rekt incidents."""
    store = InMemoryAlertStore()
    producer = AlertProducer(store=store)

    mock_incidents = [
        {"id": "test-hack-1", "name": "TestProtocol", "amount_usd": 5_000_000, "severity": "HIGH"},
    ]

    with patch("src.alerts.producer.RektDatabase") as MockRekt:
        instance = AsyncMock()
        instance.get_incidents = AsyncMock(return_value=mock_incidents)
        instance.close = AsyncMock()
        MockRekt.return_value = instance

        await producer.check_rekt_incidents()

    alerts = store.list_alerts()
    assert len(alerts) == 1
    assert "TestProtocol" in alerts[0].title
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .worktrees/main-local && python -m pytest tests/test_alert_producer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.alerts.producer'`

- [ ] **Step 3: Create `src/alerts/producer.py`**

```python
"""Alert producer — generates alerts from existing data sources."""

import logging
from uuid import uuid4

from src.alerts.models import AlertRecord
from src.alerts.store import InMemoryAlertStore
from src.config import settings
from src.data.solana import SolanaClient
from src.intel.rekt_database import RektDatabase

logger = logging.getLogger(__name__)


class AlertProducer:
    """Generates alerts by polling existing data sources."""

    def __init__(
        self,
        store: InMemoryAlertStore,
        whale_threshold_usd: float = 100_000,
    ):
        self.store = store
        self.whale_threshold_usd = whale_threshold_usd
        self._seen_whale_keys: set[str] = set()
        self._seen_rekt_ids: set[str] = set()

    async def check_whale_flows(self) -> None:
        """Generate alerts for whale transactions above threshold."""
        try:
            async with SolanaClient(
                rpc_url=settings.solana_rpc_url,
                helius_api_key=settings.helius_api_key,
            ) as client:
                txs = await client.get_whale_transactions(limit=20)
        except Exception as e:
            logger.warning(f"Alert producer: failed to fetch whale txs: {e}")
            return

        for tx in txs:
            amount = float(tx.get("amount_usd", 0) or 0)
            if amount < self.whale_threshold_usd:
                continue
            wallet = tx.get("wallet_address") or tx.get("wallet") or "unknown"
            tx_type = str(tx.get("type", "")).lower()
            dedup_key = f"{wallet}-{amount}-{tx_type}"
            if dedup_key in self._seen_whale_keys:
                continue
            self._seen_whale_keys.add(dedup_key)

            direction = "inflow" if tx_type == "buy" else "outflow"
            self.store.add_alert(AlertRecord(
                id=f"whale-{uuid4().hex[:8]}",
                state="new",
                severity="high" if amount >= 500_000 else "medium",
                title=f"Large {direction} detected: ${amount:,.0f} by {wallet[:12]}...",
                kind="whale_flow",
                subject_id=wallet,
            ))

    async def check_rekt_incidents(self) -> None:
        """Generate alerts for new rekt incidents."""
        rekt_db = RektDatabase()
        try:
            incidents = await rekt_db.get_incidents(limit=10)
        except Exception as e:
            logger.warning(f"Alert producer: failed to fetch rekt incidents: {e}")
            return
        finally:
            await rekt_db.close()

        for incident in incidents:
            incident_id = incident.get("id", "")
            if incident_id in self._seen_rekt_ids:
                continue
            self._seen_rekt_ids.add(incident_id)

            amount = incident.get("amount_usd", 0)
            name = incident.get("name", "Unknown")
            self.store.add_alert(AlertRecord(
                id=f"rekt-{uuid4().hex[:8]}",
                state="new",
                severity=incident.get("severity", "medium").lower(),
                title=f"Security incident: {name} (${amount:,.0f} affected)",
                kind="rekt_incident",
                subject_id=incident_id,
            ))

    async def run_cycle(self) -> None:
        """Run one full producer cycle."""
        await self.check_whale_flows()
        await self.check_rekt_incidents()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .worktrees/main-local && python -m pytest tests/test_alert_producer.py -v`
Expected: 2 passed

- [ ] **Step 5: Wire the producer into app startup**

In `src/api/routes/alerts.py`, add a background task launcher. Add this import at the top:

```python
import asyncio
from src.alerts.producer import AlertProducer
```

Add this function:

```python
async def _run_alert_producer(app: web.Application):
    """Background task that runs the alert producer every 5 minutes."""
    store = app[ALERT_STORE_KEY]
    producer = AlertProducer(store=store)
    while True:
        try:
            await producer.run_cycle()
        except Exception as e:
            logging.getLogger(__name__).warning(f"Alert producer cycle failed: {e}")
        await asyncio.sleep(300)  # 5 minutes
```

In `setup_alert_routes`, add the background task after route registration:

```python
    async def start_producer(app_ref: web.Application):
        app_ref["_alert_producer_task"] = asyncio.create_task(_run_alert_producer(app_ref))

    async def stop_producer(app_ref: web.Application):
        task = app_ref.get("_alert_producer_task")
        if task:
            task.cancel()

    app.on_startup.append(start_producer)
    app.on_cleanup.append(stop_producer)
```

- [ ] **Step 6: Commit**

```bash
cd .worktrees/main-local && git add src/alerts/__init__.py src/alerts/producer.py src/api/routes/alerts.py tests/test_alert_producer.py && git commit -m "feat: bootstrap alert producer with whale flow and rekt incident checks"
```

---

### Task 10: Add settings integrations section

**Files:**
- Modify: `web/app/settings/page.tsx:242-266`

- [ ] **Step 1: Add integrations section above the Resources section**

In `web/app/settings/page.tsx`, replace the section with id="integrations" (lines 242-266) with a real integrations section followed by the resources:

```typescript
      {/* API Integrations */}
      <section id="integrations">
        <GlassCard className="mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Shield className="h-5 w-5 text-emerald-500" />
            <h2 className="font-semibold">API Integrations</h2>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            Configure API keys to enable full functionality. Keys are stored locally in your browser.
          </p>
          <IntegrationKeys />
        </GlassCard>
      </section>

      {/* Links */}
      <section>
        <GlassCard>
        <h2 className="font-semibold mb-4">Resources</h2>

        <div className="space-y-2">
          {[
            { label: "Documentation", href: "/docs" },
            { label: "Twitter", href: "https://x.com/ilyonProtocol" },
            { label: "Telegram", href: "https://t.me/ilyonProtocol" },
          ].map((link) => (
            <a
              key={link.label}
              href={link.href}
              target={link.href.startsWith("http") ? "_blank" : undefined}
              rel={link.href.startsWith("http") ? "noopener noreferrer" : undefined}
              className="flex items-center justify-between p-3 rounded-lg hover:bg-card/50 transition"
            >
              <span>{link.label}</span>
              <ExternalLink className="h-4 w-4 text-muted-foreground" />
            </a>
          ))}
        </div>
        </GlassCard>
      </section>
```

- [ ] **Step 2: Add the `IntegrationKeys` component**

Add this component definition inside `web/app/settings/page.tsx`, before the default export:

```typescript
const INTEGRATION_KEYS = [
  { key: "helius_api_key", label: "Helius API Key", description: "Solana RPC and DAS API" },
  { key: "moralis_api_key", label: "Moralis API Key", description: "EVM token and NFT data" },
  { key: "etherscan_api_key", label: "Etherscan API Key", description: "Ethereum explorer" },
  { key: "bscscan_api_key", label: "BscScan API Key", description: "BSC explorer" },
  { key: "polygonscan_api_key", label: "PolygonScan API Key", description: "Polygon explorer" },
  { key: "arbiscan_api_key", label: "Arbiscan API Key", description: "Arbitrum explorer" },
  { key: "basescan_api_key", label: "BaseScan API Key", description: "Base explorer" },
] as const;

function IntegrationKeys() {
  const [keys, setKeys] = useState<Record<string, string>>(() => {
    if (typeof window === "undefined") return {};
    try {
      return JSON.parse(localStorage.getItem("ilyon_api_keys") || "{}");
    } catch {
      return {};
    }
  });

  const handleChange = (key: string, value: string) => {
    const updated = { ...keys, [key]: value };
    setKeys(updated);
    localStorage.setItem("ilyon_api_keys", JSON.stringify(updated));
  };

  return (
    <div className="space-y-3">
      {INTEGRATION_KEYS.map((item) => (
        <div key={item.key}>
          <label className="text-sm font-medium block mb-1">{item.label}</label>
          <p className="text-xs text-muted-foreground mb-1">{item.description}</p>
          <div className="flex gap-2">
            <Input
              type="password"
              value={keys[item.key] || ""}
              onChange={(e) => handleChange(item.key, e.target.value)}
              placeholder="Enter API key..."
              className="font-mono text-sm"
            />
            {keys[item.key] ? (
              <Badge variant="safe" className="shrink-0 self-center">
                <Check className="h-3 w-3 mr-1" />
                Set
              </Badge>
            ) : (
              <Badge variant="outline" className="shrink-0 self-center text-muted-foreground">
                Not set
              </Badge>
            )}
          </div>
        </div>
      ))}
      <div className="mt-3 p-3 bg-yellow-500/10 rounded-lg border border-yellow-500/20">
        <p className="text-xs text-yellow-400">
          Keys are stored in your browser only. Server-side key management will be available in a future update.
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
cd .worktrees/main-local && git add web/app/settings/page.tsx && git commit -m "feat: add API integrations section to settings page"
```

---

### Deferred Items

These spec items are intentionally deferred from this plan:

- **Spec Section 3 — Moralis as Shield fallback**: The spec suggests using Moralis token approval data as a fallback for chains without Etherscan keys. This requires research into whether Moralis exposes approval data (it may not). Deferred to a follow-up task.
- **Spec Section 9 — API key header wiring**: The spec says localStorage keys should be sent via `X-Api-Key-*` headers and the backend should read them. Task 10 implements the UI for storing keys but does not wire the header-sending or backend-reading logic. This is deferred because it requires touching every `fetchAPI` call and every route handler, which is a cross-cutting change better done as a separate task.

---

### Task 11: Final integration verification

- [ ] **Step 1: Run all backend tests**

Run: `cd .worktrees/main-local && python -m pytest tests/ -v --timeout=60`
Expected: All tests pass

- [ ] **Step 2: Run all frontend tests**

Run: `cd .worktrees/main-local && cd web && npx vitest run`
Expected: All tests pass

- [ ] **Step 3: Type-check frontend**

Run: `cd .worktrees/main-local/web && npx tsc --noEmit`
Expected: No type errors (or only pre-existing ones)

- [ ] **Step 4: Verify frontend builds**

Run: `cd .worktrees/main-local/web && npx next build`
Expected: Build succeeds

- [ ] **Step 5: Create verification checklist commit**

```bash
cd .worktrees/main-local && git add -A && git status
```

Review any uncommitted changes and commit if needed:

```bash
git commit -m "chore: final integration verification pass"
```
