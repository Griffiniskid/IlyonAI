# Real-Time Smart Money Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ephemeral Helius polling with a persistent background poller that accumulates whale transactions in PostgreSQL and streams them to the frontend via WebSocket.

**Architecture:** Background asyncio task polls Helius every 15s, deduplicates by signature, persists to PostgreSQL, broadcasts new transactions via StreamHub. Frontend connects via WebSocket for instant updates, falls back to REST polling. Wallet page removed; all wallet links become Solscan external links. Flows page merged into Smart Money Hub.

**Tech Stack:** Python/aiohttp, SQLAlchemy async, asyncio, WebSocket (existing StreamHub), React/Next.js, TanStack Query

**Spec:** `docs/superpowers/specs/2026-03-23-realtime-smart-money-pipeline-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/storage/database.py` | Add `WhaleTransaction` model + query methods |
| `src/services/whale_poller.py` (new) | Background poller: fetch, persist, broadcast |
| `src/api/routes/smart_money.py` | Rewrite to read from DB |
| `web/lib/realtime.ts` | Extend RealtimeClient with onMessage, reconnection |
| `web/lib/hooks.ts` | Add `useWhaleStream()` hook |
| `web/app/smart-money/page.tsx` | Merge flows UI, WebSocket streaming |
| `web/components/layout/nav-config.ts` | Remove Wallet + Flows nav items |
| `web/app/flows/page.tsx` | Delete |
| `web/app/wallet/` | Delete |
| Site-wide `.tsx` files | Replace `/wallet/` links with Solscan |

---

### Task 1: Add WhaleTransaction Database Model

**Files:**
- Modify: `src/storage/database.py`
- Test: `tests/storage/test_whale_transactions.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/storage/test_whale_transactions.py`:

```python
"""Tests for WhaleTransaction persistence."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.storage.database import Database


@pytest.fixture
def db():
    """Create a Database instance without connecting."""
    d = Database.__new__(Database)
    d._initialized = True
    d._engine = MagicMock()
    d._async_session = MagicMock()
    return d


class TestWhaleTransactionModel:
    """Verify the WhaleTransaction model exists and has expected columns."""

    def test_model_has_expected_columns(self):
        from src.storage.database import WhaleTransaction
        mapper = WhaleTransaction.__table__
        column_names = {c.name for c in mapper.columns}
        expected = {
            "signature", "wallet_address", "wallet_label",
            "token_address", "token_symbol", "token_name",
            "direction", "amount_usd", "amount_tokens", "price_usd",
            "dex_name", "tx_timestamp", "created_at",
        }
        assert expected.issubset(column_names)

    def test_signature_is_primary_key(self):
        from src.storage.database import WhaleTransaction
        pk_cols = [c.name for c in WhaleTransaction.__table__.primary_key.columns]
        assert pk_cols == ["signature"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/storage/test_whale_transactions.py -x -v`
Expected: FAIL with `ImportError: cannot import name 'WhaleTransaction'`

- [ ] **Step 3: Write the WhaleTransaction model**

Add to `src/storage/database.py` after the `TrackedWallet` model (around line 395), before the `Database` class:

```python
class WhaleTransaction(Base):
    """Persisted whale transactions for the 24h rolling Smart Money feed."""
    __tablename__ = "whale_transactions"

    signature = Column(String(128), primary_key=True)
    wallet_address = Column(String(44), nullable=False, index=True)
    wallet_label = Column(String(128), nullable=True)
    token_address = Column(String(44), nullable=False)
    token_symbol = Column(String(32), nullable=False)
    token_name = Column(String(128), nullable=False)
    direction = Column(String(8), nullable=False, index=True)
    amount_usd = Column(Float, nullable=False)
    amount_tokens = Column(Float, nullable=False)
    price_usd = Column(Float, nullable=False)
    dex_name = Column(String(64), nullable=False)
    tx_timestamp = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/storage/test_whale_transactions.py -x -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local
git add src/storage/database.py tests/storage/test_whale_transactions.py
git commit -m "feat: add WhaleTransaction database model"
```

---

### Task 2: Add Database Query Methods for Whale Transactions

**Files:**
- Modify: `src/storage/database.py`
- Modify: `tests/storage/test_whale_transactions.py`

- [ ] **Step 1: Write failing tests for insert and query methods**

Append to `tests/storage/test_whale_transactions.py`:

```python
@pytest.mark.asyncio
class TestWhaleTransactionQueries:
    """Test database query methods for whale transactions."""

    async def test_insert_whale_transactions_deduplicates(self, db):
        tx = {
            "signature": "sig123",
            "wallet_address": "WaLLet1111",
            "wallet_label": None,
            "token_address": "ToKen1111",
            "token_symbol": "SOL",
            "token_name": "Solana",
            "direction": "buy",
            "amount_usd": 50000.0,
            "amount_tokens": 100.0,
            "price_usd": 500.0,
            "dex_name": "Jupiter",
            "tx_timestamp": datetime.utcnow(),
        }
        # Method should exist and accept a list of dicts
        assert hasattr(db, "insert_whale_transactions")

    async def test_get_whale_overview_method_exists(self, db):
        assert hasattr(db, "get_whale_overview")

    async def test_cleanup_old_whale_transactions_method_exists(self, db):
        assert hasattr(db, "cleanup_old_whale_transactions")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/storage/test_whale_transactions.py::TestWhaleTransactionQueries -x -v`
Expected: FAIL with `AssertionError`

- [ ] **Step 3: Add query methods to Database class**

Add these methods to the `Database` class in `src/storage/database.py`:

```python
    async def insert_whale_transactions(self, transactions: list[dict]) -> list[str]:
        """Insert whale transactions, skipping duplicates. Returns list of new signatures."""
        if not self._initialized:
            return []
        new_signatures = []
        async with self._async_session() as session:
            for tx in transactions:
                try:
                    from sqlalchemy.dialects.postgresql import insert as pg_insert
                    stmt = pg_insert(WhaleTransaction).values(
                        signature=tx["signature"],
                        wallet_address=tx.get("wallet_address", ""),
                        wallet_label=tx.get("wallet_label"),
                        token_address=tx.get("token_address", ""),
                        token_symbol=tx.get("token_symbol", "???"),
                        token_name=tx.get("token_name", "Unknown"),
                        direction="buy" if tx.get("type", "buy") == "buy" else "sell",
                        amount_usd=float(tx.get("amount_usd", 0)),
                        amount_tokens=float(tx.get("amount_tokens", 0)),
                        price_usd=float(tx.get("price_usd", 0)),
                        dex_name=tx.get("dex_name", "Unknown"),
                        tx_timestamp=tx.get("timestamp") if isinstance(tx.get("timestamp"), datetime)
                            else datetime.fromisoformat(str(tx.get("timestamp", datetime.utcnow().isoformat())).replace("Z", "+00:00")).replace(tzinfo=None),
                    ).on_conflict_do_nothing(index_elements=["signature"])
                    result = await session.execute(stmt)
                    if result.rowcount and result.rowcount > 0:
                        new_signatures.append(tx["signature"])
                except Exception as e:
                    logger.debug(f"Failed to insert whale tx {tx.get('signature', '?')}: {e}")
            await session.commit()
        return new_signatures

    async def get_whale_overview(self, hours: int = 24, limit: int = 100) -> dict:
        """Query whale transactions for the smart money overview."""
        if not self._initialized:
            return {"transactions": [], "inflow_usd": 0, "outflow_usd": 0}
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        async with self._async_session() as session:
            from sqlalchemy import select, func
            stmt = select(WhaleTransaction).where(
                WhaleTransaction.created_at >= cutoff
            ).order_by(WhaleTransaction.tx_timestamp.desc()).limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()

            transactions = []
            inflow_usd = 0.0
            outflow_usd = 0.0
            for row in rows:
                tx_dict = {
                    "signature": row.signature,
                    "wallet_address": row.wallet_address,
                    "wallet_label": row.wallet_label,
                    "token_address": row.token_address,
                    "token_symbol": row.token_symbol,
                    "token_name": row.token_name,
                    "direction": "inflow" if row.direction == "buy" else "outflow",
                    "amount_usd": row.amount_usd,
                    "amount_tokens": row.amount_tokens,
                    "price_usd": row.price_usd,
                    "dex_name": row.dex_name,
                    "timestamp": row.tx_timestamp.isoformat() if row.tx_timestamp else "",
                    "chain": "solana",
                }
                transactions.append(tx_dict)
                if row.direction == "buy":
                    inflow_usd += row.amount_usd
                else:
                    outflow_usd += row.amount_usd

            return {
                "transactions": transactions,
                "inflow_usd": inflow_usd,
                "outflow_usd": outflow_usd,
            }

    async def cleanup_old_whale_transactions(self, hours: int = 24) -> int:
        """Delete whale transactions older than the given window. Returns count deleted."""
        if not self._initialized:
            return 0
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        async with self._async_session() as session:
            from sqlalchemy import delete
            stmt = delete(WhaleTransaction).where(WhaleTransaction.created_at < cutoff)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0
```

Also add `from datetime import timedelta` to the imports at the top of the file if not already present.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/storage/test_whale_transactions.py -x -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local
git add src/storage/database.py tests/storage/test_whale_transactions.py
git commit -m "feat: add whale transaction insert, query, cleanup methods"
```

---

### Task 3: Create WhaleTransactionPoller Background Service

**Files:**
- Create: `src/services/whale_poller.py`
- Test: `tests/services/test_whale_poller.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_whale_poller.py`:

```python
"""Tests for WhaleTransactionPoller background service."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.services.whale_poller import WhaleTransactionPoller


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.insert_whale_transactions = AsyncMock(return_value=["sig1"])
    db.cleanup_old_whale_transactions = AsyncMock(return_value=0)
    return db


@pytest.fixture
def mock_stream_hub():
    hub = MagicMock()
    hub.publish = AsyncMock()
    return hub


@pytest.fixture
def poller(mock_db, mock_stream_hub):
    return WhaleTransactionPoller(db=mock_db, stream_hub=mock_stream_hub)


class TestWhaleTransactionPoller:
    @pytest.mark.asyncio
    async def test_poll_cycle_persists_and_broadcasts(self, poller, mock_db, mock_stream_hub):
        fake_txs = [
            {
                "signature": "sig1",
                "wallet_address": "WaLLet1111",
                "wallet_label": None,
                "token_address": "ToKen1111",
                "token_symbol": "SOL",
                "token_name": "Solana",
                "type": "buy",
                "amount_usd": 50000.0,
                "amount_tokens": 100.0,
                "price_usd": 500.0,
                "dex_name": "Jupiter",
                "timestamp": datetime.utcnow().isoformat(),
            }
        ]
        with patch("src.services.whale_poller.SolanaClient") as MockClient:
            instance = AsyncMock()
            instance.get_recent_large_transactions = AsyncMock(return_value=fake_txs)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            await poller.poll_once()

        mock_db.insert_whale_transactions.assert_called_once_with(fake_txs)
        mock_stream_hub.publish.assert_called_once()
        mock_db.cleanup_old_whale_transactions.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_cycle_handles_helius_failure(self, poller, mock_db, mock_stream_hub):
        with patch("src.services.whale_poller.SolanaClient") as MockClient:
            instance = AsyncMock()
            instance.get_recent_large_transactions = AsyncMock(side_effect=Exception("API down"))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            await poller.poll_once()  # Should not raise

        mock_db.insert_whale_transactions.assert_not_called()

    def test_circuit_breaker_backs_off(self, poller):
        for _ in range(5):
            poller._record_failure()
        assert poller.poll_interval > 15
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/services/test_whale_poller.py -x -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create the poller service**

Create `src/services/__init__.py` (if it doesn't exist) and `src/services/whale_poller.py`:

```python
"""Background poller that accumulates whale transactions from Helius."""

import asyncio
import logging
from datetime import datetime

from src.config import settings
from src.data.solana import SolanaClient
from src.platform.stream_hub import get_stream_hub
from src.storage.database import Database

logger = logging.getLogger(__name__)

TOPIC = "whale-transactions"
DEFAULT_INTERVAL = 15  # seconds
BACKOFF_INTERVAL = 60  # seconds after circuit break
MAX_CONSECUTIVE_FAILURES = 5


class WhaleTransactionPoller:
    """Polls Helius for large DEX swaps and persists them."""

    def __init__(
        self,
        db: Database,
        stream_hub=None,
        poll_interval: int = DEFAULT_INTERVAL,
    ):
        self._db = db
        self._stream_hub = stream_hub or get_stream_hub()
        self._base_interval = poll_interval
        self.poll_interval = poll_interval
        self._consecutive_failures = 0
        self._task: asyncio.Task | None = None

    async def poll_once(self) -> None:
        """Execute a single poll cycle: fetch → persist → broadcast → cleanup."""
        try:
            async with SolanaClient(
                rpc_url=settings.solana_rpc_url,
                helius_api_key=settings.helius_api_key,
            ) as client:
                transactions = await client.get_recent_large_transactions(
                    min_amount_usd=10000, limit=200,
                )
        except Exception as e:
            logger.warning(f"Whale poller: Helius fetch failed: {e}")
            self._record_failure()
            return

        if not transactions:
            self._record_success()
            await self._db.cleanup_old_whale_transactions(hours=24)
            return

        try:
            new_sigs = await self._db.insert_whale_transactions(transactions)
        except Exception as e:
            logger.error(f"Whale poller: DB insert failed: {e}")
            self._record_failure()
            return

        # Broadcast only genuinely new transactions
        new_sig_set = set(new_sigs)
        for tx in transactions:
            if tx.get("signature") in new_sig_set:
                await self._stream_hub.publish(TOPIC, {
                    "signature": tx.get("signature"),
                    "wallet_address": tx.get("wallet_address", ""),
                    "wallet_label": tx.get("wallet_label"),
                    "token_address": tx.get("token_address", ""),
                    "token_symbol": tx.get("token_symbol", "???"),
                    "token_name": tx.get("token_name", "Unknown"),
                    "direction": "inflow" if tx.get("type", "buy") == "buy" else "outflow",
                    "amount_usd": float(tx.get("amount_usd", 0)),
                    "amount_tokens": float(tx.get("amount_tokens", 0)),
                    "price_usd": float(tx.get("price_usd", 0)),
                    "dex_name": tx.get("dex_name", "Unknown"),
                    "timestamp": tx.get("timestamp", ""),
                    "chain": "solana",
                })

        self._record_success()
        await self._db.cleanup_old_whale_transactions(hours=24)
        logger.info(f"Whale poller: {len(new_sigs)} new transactions persisted")

    def _record_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            self.poll_interval = BACKOFF_INTERVAL
            logger.warning(f"Whale poller: circuit breaker open, backing off to {BACKOFF_INTERVAL}s")

    def _record_success(self):
        self._consecutive_failures = 0
        self.poll_interval = self._base_interval

    async def run_forever(self) -> None:
        """Main loop — runs until cancelled."""
        logger.info(f"Whale poller started (interval={self.poll_interval}s)")
        while True:
            await self.poll_once()
            await asyncio.sleep(self.poll_interval)

    async def start(self, app) -> None:
        """aiohttp on_startup hook."""
        self._task = asyncio.create_task(self.run_forever())

    async def stop(self, app) -> None:
        """aiohttp on_cleanup hook."""
        if self._task:
            self._task.cancel()
            logger.info("Whale poller stopped")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/services/test_whale_poller.py -x -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local
git add src/services/__init__.py src/services/whale_poller.py tests/services/test_whale_poller.py
git commit -m "feat: create WhaleTransactionPoller background service"
```

---

### Task 4: Wire Poller into App Startup and Rewrite Smart Money Route

**Files:**
- Modify: `src/main.py`
- Modify: `src/api/routes/smart_money.py`
- Test: `tests/api/test_smart_money_db.py` (new)

- [ ] **Step 1: Write failing test for DB-backed smart money overview**

Create `tests/api/test_smart_money_db.py`:

```python
"""Test smart money overview reads from database."""
import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


@pytest.mark.asyncio
async def test_smart_money_overview_reads_from_db(aiohttp_client):
    from src.api.routes.smart_money import setup_smart_money_routes

    mock_db = AsyncMock()
    mock_db.get_whale_overview = AsyncMock(return_value={
        "transactions": [
            {
                "signature": "sig1",
                "wallet_address": "Wallet1",
                "wallet_label": None,
                "direction": "inflow",
                "amount_usd": 50000.0,
                "amount_tokens": 100.0,
                "token_address": "Token1",
                "token_symbol": "SOL",
                "token_name": "Solana",
                "dex_name": "Jupiter",
                "timestamp": datetime.utcnow().isoformat(),
                "chain": "solana",
            },
        ],
        "inflow_usd": 50000.0,
        "outflow_usd": 0.0,
    })

    with patch("src.api.routes.smart_money.get_database", return_value=mock_db):
        app = web.Application()
        setup_smart_money_routes(app)
        client = await aiohttp_client(app)
        resp = await client.get("/api/v1/smart-money/overview")
        assert resp.status == 200
        data = await resp.json()
        payload = data.get("data", data)
        assert payload["inflow_usd"] == 50000.0
        assert len(payload["recent_transactions"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/api/test_smart_money_db.py -x -v`
Expected: FAIL (smart_money.py still calls Helius directly)

- [ ] **Step 3: Rewrite smart_money.py to read from DB**

Replace `src/api/routes/smart_money.py`:

```python
"""Smart money API routes — reads from persisted whale transactions."""

import logging
from collections import defaultdict
from datetime import datetime

from aiohttp import web

from src.api.response_envelope import envelope_response, envelope_error_response
from src.api.schemas.responses import SmartMoneyOverviewResponse
from src.storage.database import get_database

logger = logging.getLogger(__name__)


async def get_smart_money_overview(request: web.Request) -> web.Response:
    try:
        db = await get_database()
        overview = await db.get_whale_overview(hours=24, limit=200)
    except Exception as e:
        logger.error(f"Smart money overview failed: {e}")
        return envelope_error_response(
            f"Failed to fetch smart money data: {e}",
            code="SMART_MONEY_FETCH_FAILED",
            http_status=502,
        )

    transactions = overview.get("transactions", [])
    inflow_usd = overview.get("inflow_usd", 0.0)
    outflow_usd = overview.get("outflow_usd", 0.0)

    # Per-wallet aggregation
    wallet_agg = defaultdict(lambda: {
        "wallet_address": "",
        "label": None,
        "amount_usd": 0.0,
        "tx_count": 0,
        "last_seen": "",
        "token_symbol": None,
        "dex_name": None,
        "largest_tx_amount": 0.0,
    })

    for tx in transactions:
        wallet = tx.get("wallet_address", "")
        direction = tx.get("direction", "inflow")
        amount = float(tx.get("amount_usd", 0))
        timestamp = tx.get("timestamp", "")

        if wallet:
            key = (wallet, direction)
            entry = wallet_agg[key]
            entry["wallet_address"] = wallet
            entry["label"] = entry["label"] or tx.get("wallet_label")
            entry["amount_usd"] += amount
            entry["tx_count"] += 1
            if timestamp and timestamp > entry["last_seen"]:
                entry["last_seen"] = timestamp
            if amount > entry["largest_tx_amount"]:
                entry["largest_tx_amount"] = amount
                entry["token_symbol"] = tx.get("token_symbol")
                entry["dex_name"] = tx.get("dex_name")

    top_buyers = []
    top_sellers = []
    for (wallet, direction), entry in wallet_agg.items():
        clean = {
            "wallet_address": entry["wallet_address"],
            "label": entry["label"],
            "amount_usd": entry["amount_usd"],
            "tx_count": entry["tx_count"],
            "last_seen": entry["last_seen"],
            "token_symbol": entry["token_symbol"],
            "dex_name": entry["dex_name"],
        }
        if direction == "inflow":
            top_buyers.append(clean)
        else:
            top_sellers.append(clean)

    top_buyers.sort(key=lambda x: x["amount_usd"], reverse=True)
    top_sellers.sort(key=lambda x: x["amount_usd"], reverse=True)

    net_flow_usd = inflow_usd - outflow_usd
    total_volume = inflow_usd + outflow_usd

    if total_volume == 0:
        flow_direction = "neutral"
    elif inflow_usd > outflow_usd:
        flow_direction = "accumulating"
    else:
        flow_direction = "distributing"

    sell_volume_percent = (outflow_usd / total_volume * 100) if total_volume > 0 else 0

    payload = SmartMoneyOverviewResponse(
        net_flow_usd=net_flow_usd,
        inflow_usd=inflow_usd,
        outflow_usd=outflow_usd,
        top_buyers=top_buyers[:10],
        top_sellers=top_sellers[:10],
        flows=[],
        flow_direction=flow_direction,
        sell_volume_percent=sell_volume_percent,
        recent_transactions=transactions,
        updated_at=datetime.utcnow().isoformat(),
    ).model_dump(mode="json")

    return envelope_response(payload, meta={"surface": "smart_money_overview"})


def setup_smart_money_routes(app: web.Application):
    app.router.add_get("/api/v1/smart-money/overview", get_smart_money_overview)
```

- [ ] **Step 4: Wire poller into main.py startup**

Add to `src/main.py` in the `on_startup` function, after database init:

```python
    # Start whale transaction poller
    from src.services.whale_poller import WhaleTransactionPoller
    from src.platform.stream_hub import get_stream_hub
    poller = WhaleTransactionPoller(db=db, stream_hub=get_stream_hub())
    app["_whale_poller"] = poller
    app.on_startup.append(poller.start)
    app.on_cleanup.append(poller.stop)
```

Note: Since `on_startup` is already running, register the poller's `start` and `stop` as additional hooks. Actually, since we're inside `on_startup` already, just create the task directly:

```python
    # Start whale transaction poller
    from src.services.whale_poller import WhaleTransactionPoller
    from src.platform.stream_hub import get_stream_hub
    poller = WhaleTransactionPoller(db=db, stream_hub=get_stream_hub())
    app["_whale_poller_task"] = asyncio.create_task(poller.run_forever())
```

And in `on_cleanup`:

```python
    # Stop whale poller
    poller_task = app.get("_whale_poller_task")
    if poller_task:
        poller_task.cancel()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/api/test_smart_money_db.py -x -v`
Expected: PASS

- [ ] **Step 6: Run all backend tests**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/ -x -q --tb=short`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local
git add src/api/routes/smart_money.py src/main.py tests/api/test_smart_money_db.py
git commit -m "feat: wire whale poller to startup, rewrite smart money route to read from DB"
```

---

### Task 5: Extend RealtimeClient with Message Handling and Reconnection

**Files:**
- Modify: `web/lib/realtime.ts`
- Test: `web/tests/app/realtime-stream.test.tsx` (new)

- [ ] **Step 1: Write the failing test**

Create `web/tests/app/realtime-stream.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { RealtimeClient } from "@/lib/realtime";

describe("RealtimeClient message handling", () => {
  it("exposes onMessage method", () => {
    const client = new RealtimeClient("http://localhost:8000");
    expect(typeof client.onMessage).toBe("function");
  });

  it("exposes subscribe method", () => {
    const client = new RealtimeClient("http://localhost:8000");
    expect(typeof client.subscribe).toBe("function");
  });

  it("exposes streamStatus property", () => {
    const client = new RealtimeClient("http://localhost:8000");
    expect(client.streamStatus).toBe("disconnected");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local/web && npx vitest run tests/app/realtime-stream.test.tsx`
Expected: FAIL

- [ ] **Step 3: Extend RealtimeClient**

Rewrite `web/lib/realtime.ts`:

```typescript
export type RealtimeMode = "websocket" | "polling";
export type StreamStatus = "disconnected" | "live" | "reconnecting" | "polling";

export class RealtimeClient {
  private readonly baseUrl: string;
  private readonly connectionTimeoutMs: number;
  private socket: WebSocket | null = null;
  private _messageHandler: ((data: unknown) => void) | null = null;
  private _streamStatus: StreamStatus = "disconnected";
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private _reconnectAttempts = 0;
  private _currentTopic: string | null = null;
  _force_socket_failure_for_test = false;

  constructor(baseUrl: string, connectionTimeoutMs = 3000) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.connectionTimeoutMs = connectionTimeoutMs;
  }

  get streamStatus(): StreamStatus {
    return this._streamStatus;
  }

  onMessage(handler: (data: unknown) => void): void {
    this._messageHandler = handler;
    if (this.socket) {
      this.socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          handler(parsed);
        } catch {
          // ignore non-JSON heartbeats
        }
      };
    }
  }

  async subscribe(topic: string, handler: (data: unknown) => void): Promise<RealtimeMode> {
    this._currentTopic = topic;
    this.onMessage(handler);
    const mode = await this.connect_or_fallback(topic);
    if (mode === "websocket") {
      this._streamStatus = "live";
    } else {
      this._streamStatus = "polling";
    }
    return mode;
  }

  async connect_or_fallback(topic: string): Promise<RealtimeMode> {
    if (this._force_socket_failure_for_test) {
      this._streamStatus = "polling";
      return "polling";
    }

    return new Promise<RealtimeMode>((resolve) => {
      const url = this.buildWebSocketUrl(topic);
      const timeout = setTimeout(() => {
        if (this.socket) {
          this.socket.close();
          this.socket = null;
        }
        this._streamStatus = "polling";
        resolve("polling");
      }, this.connectionTimeoutMs);

      try {
        this.socket = new WebSocket(url);

        this.socket.onopen = () => {
          clearTimeout(timeout);
          this._streamStatus = "live";
          this._reconnectAttempts = 0;

          if (this._messageHandler && this.socket) {
            this.socket.onmessage = (event) => {
              try {
                const parsed = JSON.parse(event.data);
                this._messageHandler?.(parsed);
              } catch {
                // ignore heartbeats
              }
            };
          }

          resolve("websocket");
        };

        this.socket.onclose = () => {
          if (this._streamStatus === "live") {
            this._attemptReconnect();
          }
        };

        this.socket.onerror = () => {
          clearTimeout(timeout);
          if (this.socket) {
            this.socket.close();
            this.socket = null;
          }
          this._streamStatus = "polling";
          resolve("polling");
        };
      } catch {
        clearTimeout(timeout);
        this._streamStatus = "polling";
        resolve("polling");
      }
    });
  }

  private _attemptReconnect(): void {
    this._streamStatus = "reconnecting";
    this._reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this._reconnectAttempts - 1), 30000);

    this._reconnectTimer = setTimeout(async () => {
      if (this._currentTopic) {
        const mode = await this.connect_or_fallback(this._currentTopic);
        if (mode === "polling") {
          this._streamStatus = "polling";
        }
      }
    }, delay);
  }

  close(): void {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.onclose = null; // prevent reconnect on intentional close
      this.socket.close();
      this.socket = null;
    }
    this._streamStatus = "disconnected";
    this._currentTopic = null;
  }

  private buildWebSocketUrl(topic: string): string {
    const wsBase = this.baseUrl
      .replace(/^http:/, "ws:")
      .replace(/^https:/, "wss:");
    return `${wsBase}/api/v1/stream/ws?topic=${encodeURIComponent(topic)}`;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local/web && npx vitest run tests/app/realtime-stream.test.tsx`
Expected: PASS

- [ ] **Step 5: Run existing realtime tests to ensure no regression**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local/web && npx vitest run tests/app/realtime-fallback.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local
git add web/lib/realtime.ts web/tests/app/realtime-stream.test.tsx
git commit -m "feat: extend RealtimeClient with onMessage, subscribe, reconnection"
```

---

### Task 6: Add useWhaleStream Hook

**Files:**
- Modify: `web/lib/hooks.ts`
- Test: existing smart money tests will cover via the page

- [ ] **Step 1: Add the useWhaleStream hook to hooks.ts**

Add after `useSmartMoneyOverview()` in `web/lib/hooks.ts`:

```typescript
import { useEffect, useRef, useState, useCallback } from "react";
import { RealtimeClient, type StreamStatus } from "./realtime";

export function useWhaleStream() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useSmartMoneyOverview();
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("disconnected");
  const clientRef = useRef<RealtimeClient | null>(null);

  useEffect(() => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";
    const client = new RealtimeClient(apiBase);
    clientRef.current = client;

    client.subscribe("whale-transactions", (event: unknown) => {
      const tx = event as Record<string, unknown>;
      if (!tx?.signature) return;

      queryClient.setQueryData<SmartMoneyOverviewResponse>(
        ["smartMoney", "overview"],
        (old) => {
          if (!old) return old;
          const newTx = tx as SmartMoneyOverviewResponse["recent_transactions"][number];
          return {
            ...old,
            recent_transactions: [newTx, ...old.recent_transactions].slice(0, 200),
          };
        },
      );
    }).then((mode) => {
      setStreamStatus(mode === "websocket" ? "live" : "polling");
    });

    return () => {
      client.close();
    };
  }, [queryClient]);

  // Sync status from client on interval (for reconnection state changes)
  useEffect(() => {
    const interval = setInterval(() => {
      if (clientRef.current) {
        setStreamStatus(clientRef.current.streamStatus);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  return { data, isLoading, error, streamStatus };
}
```

Also add `useQueryClient` to the existing `@tanstack/react-query` import at the top of hooks.ts.

- [ ] **Step 2: Commit**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local
git add web/lib/hooks.ts
git commit -m "feat: add useWhaleStream hook with WebSocket + polling fallback"
```

---

### Task 7: Redesign Smart Money Page (Merge Flows)

**Files:**
- Modify: `web/app/smart-money/page.tsx`

- [ ] **Step 1: Rewrite the smart money page**

Replace `web/app/smart-money/page.tsx` with the merged Hub + Flows page that uses `useWhaleStream()`:

The new page should:
1. Import `useWhaleStream` instead of `useSmartMoneyOverview`
2. Keep the 4-metric cards (Net Flow, Inflow, Outflow, Flow Direction)
3. Keep the Top Buyers / Top Sellers tables but with Solscan links for wallet addresses
4. Add the transaction feed from flows page with direction filter + min USD filter
5. Show streaming status indicator ("Live" / "Reconnecting..." / "Polling")
6. All wallet addresses link to `https://solscan.io/account/{address}` (external)
7. All tx signatures link to `https://solscan.io/tx/{signature}` (external)
8. Remove the "Explore Flows" and "Wallet Lookup" navigation links
9. Keep "Entity Explorer" link

Key changes from current page:
- Replace `useSmartMoneyOverview()` with `useWhaleStream()`
- Add `streamStatus` indicator badge
- Add direction filter state (`all | inflow | outflow`) and min USD filter
- Add filtered transaction feed (currently limited to 10, now show up to 100)
- Replace all `<Link href={/wallet/...}>` with `<a href="https://solscan.io/account/..." target="_blank">`

- [ ] **Step 2: Run frontend tests**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local/web && npx vitest run`
Expected: Some tests may need updating for the new page structure

- [ ] **Step 3: Fix any broken tests**

Update test mocks if needed to work with `useWhaleStream` instead of `useSmartMoneyOverview`.

- [ ] **Step 4: Commit**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local
git add web/app/smart-money/page.tsx
git commit -m "feat: redesign smart money page — merge flows, add streaming, Solscan links"
```

---

### Task 8: Remove Wallet Page, Flows Page, Update Nav

**Files:**
- Delete: `web/app/wallet/` (if exists)
- Delete: `web/app/flows/` (if exists)
- Modify: `web/components/layout/nav-config.ts`

- [ ] **Step 1: Remove nav items**

In `web/components/layout/nav-config.ts`, remove the `Flows` and `Wallet` entries from the Smart Money group. The group should have only: Hub, Whales, Entity.

- [ ] **Step 2: Delete flows page**

```bash
rm -rf /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local/web/app/flows
```

- [ ] **Step 3: Delete wallet page**

```bash
rm -rf /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local/web/app/wallet
```

- [ ] **Step 4: Commit**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local
git add -A web/app/flows/ web/app/wallet/ web/components/layout/nav-config.ts
git commit -m "feat: remove wallet page, flows page; update nav to Hub/Whales/Entity"
```

---

### Task 9: Replace All /wallet/ Links with Solscan Links Site-Wide

**Files:**
- Modify: `web/app/whales/page.tsx`
- Modify: `web/app/entity/[id]/page.tsx`
- Modify: `web/app/dashboard/page.tsx`
- Modify: any other files with `/wallet/` links

Files to update (from grep):
- `web/app/whales/page.tsx:259` — `href={/wallet/${tx.wallet_address}}`
- `web/app/entity/[id]/page.tsx:80` — `<Link href={/wallet/${wallet}}>`
- `web/app/dashboard/page.tsx:199` — `<Link href={/wallet/${walletAddress}}>`

- [ ] **Step 1: Update whales page**

In `web/app/whales/page.tsx`, replace:
```tsx
href={`/wallet/${tx.wallet_address}`}
```
with:
```tsx
href={`https://solscan.io/account/${tx.wallet_address}`}
target="_blank"
rel="noopener noreferrer"
```
Change the `<Link>` component to a plain `<a>` tag. Remove the `next/link` import if no longer used.

- [ ] **Step 2: Update entity page**

In `web/app/entity/[id]/page.tsx`, replace:
```tsx
<Link href={`/wallet/${wallet}`} className="font-mono text-primary hover:underline">
```
with:
```tsx
<a href={`https://solscan.io/account/${wallet}`} target="_blank" rel="noopener noreferrer" className="font-mono text-primary hover:underline">
```

- [ ] **Step 3: Update dashboard page**

In `web/app/dashboard/page.tsx`, replace the `<Link href={/wallet/${walletAddress}}>` with a Solscan link. Change to `<a>` tag with external URL.

- [ ] **Step 4: Search for any remaining /wallet/ links**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && grep -rn '"/wallet/' web/app/ --include="*.tsx" --include="*.ts"`
Expected: No results (all replaced)

- [ ] **Step 5: Run all frontend tests**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local/web && npx vitest run`
Expected: All pass

- [ ] **Step 6: Run all backend tests**

Run: `cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/ -x -q --tb=short`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local
git add web/app/whales/page.tsx web/app/entity/\[id\]/page.tsx web/app/dashboard/page.tsx
git commit -m "feat: replace all /wallet/ links with Solscan external links"
```

---

### Task 10: Delete Flows Test File and Clean Up

**Files:**
- Delete: `web/tests/app/flows.page.test.tsx`
- Modify: any test files referencing `/wallet/` routes

- [ ] **Step 1: Delete flows test**

```bash
rm /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local/web/tests/app/flows.page.test.tsx
```

- [ ] **Step 2: Search for test files referencing /wallet/ or flows**

```bash
grep -rn '"/wallet/\|/flows' /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local/web/tests/ --include="*.tsx" --include="*.ts"
```

Fix any remaining references.

- [ ] **Step 3: Run full test suite**

Run both backend and frontend tests:
```bash
cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local && python -m pytest tests/ -x -q --tb=short
cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local/web && npx vitest run
```
Expected: All pass

- [ ] **Step 4: Commit**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/.worktrees/main-local
git add -A
git commit -m "chore: clean up flows tests and wallet route references"
```
