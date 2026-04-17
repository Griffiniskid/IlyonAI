# Whale Page Leaderboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the chronological whale tx feed at `/whales` with a ranked token leaderboard + Top Whales sidebar, fed by two new aggregation endpoints reading from the existing `whale_transactions` table.

**Architecture:** Backend computes per-window aggregations on demand in Python (no new DB migration, no new background job). Frontend drives everything off two TanStack queries keyed by `(window, sort)`. Old per-token `/whales/token/{address}` route is untouched.

**Tech Stack:** aiohttp, SQLAlchemy async, Pydantic v2, Next.js 14 App Router, TanStack Query, Tailwind, Vitest.

**Spec:** `docs/superpowers/specs/2026-04-17-whale-page-leaderboard-design.md`

---

## File Structure

**Create:**
- `src/api/routes/whale_leaderboard.py` — new route handlers (leaderboard + top-wallets)
- `src/api/schemas/whale_leaderboard.py` — Pydantic response models
- `tests/api/test_whale_leaderboard.py` — route + aggregation tests
- `web/app/whales/_components/window-sort-controls.tsx`
- `web/app/whales/_components/leaderboard-row.tsx`
- `web/app/whales/_components/top-whales-panel.tsx`
- `web/app/whales/_components/empty-state.tsx`

**Modify:**
- `src/storage/database.py` — add `get_whale_aggregations(hours)`
- `src/api/app.py` — register new routes
- `web/lib/api.ts` — add `getWhaleLeaderboard`, `getTopWhales`
- `web/lib/hooks.ts` — add `useWhaleLeaderboard`, `useTopWhales`
- `web/types/index.ts` — add leaderboard types
- `web/app/whales/page.tsx` — full rewrite

**Replace (full rewrite):**
- `web/tests/app/whales.page.test.tsx`

---

## Task 1: Database aggregation method

**Files:**
- Modify: `src/storage/database.py` (append after `get_whale_overview`)

- [ ] **Step 1: Add method**

```python
async def get_whale_aggregations(self, hours: int) -> dict:
    """Return window rows and prior-window token set for leaderboard.

    Returns:
        {
            "rows": [ {signature, wallet_address, wallet_label, token_address,
                       token_symbol, token_name, direction, amount_usd,
                       tx_timestamp}, ... ],
            "prior_token_addresses": set[str]  # tokens active in (2*window..window) ago
        }
    """
    if not self._initialized:
        return {"rows": [], "prior_token_addresses": set()}
    now = datetime.utcnow()
    window_cutoff = now - timedelta(hours=hours)
    prior_cutoff = now - timedelta(hours=hours * 2)
    async with self.async_session() as session:
        stmt_window = select(WhaleTransaction).where(
            WhaleTransaction.tx_timestamp >= window_cutoff
        ).order_by(WhaleTransaction.tx_timestamp.desc())
        result = await session.execute(stmt_window)
        window_rows = result.scalars().all()

        stmt_prior = select(WhaleTransaction.token_address).where(
            WhaleTransaction.tx_timestamp >= prior_cutoff,
            WhaleTransaction.tx_timestamp < window_cutoff,
        ).distinct()
        prior_result = await session.execute(stmt_prior)
        prior_tokens = {row[0] for row in prior_result.all()}

        rows = [{
            "signature": r.signature,
            "wallet_address": r.wallet_address,
            "wallet_label": r.wallet_label,
            "token_address": r.token_address,
            "token_symbol": r.token_symbol,
            "token_name": r.token_name,
            "direction": r.direction,
            "amount_usd": float(r.amount_usd),
            "tx_timestamp": r.tx_timestamp,
        } for r in window_rows]

        return {"rows": rows, "prior_token_addresses": prior_tokens}
```

- [ ] **Step 2: Commit**

```
git add src/storage/database.py
git commit -m "feat(db): add whale aggregation query for leaderboard"
```

---

## Task 2: Aggregation logic (pure function, unit tested)

**Files:**
- Create: `src/api/routes/whale_leaderboard.py` (aggregation helpers only in this task)
- Create: `tests/api/test_whale_leaderboard.py`

- [ ] **Step 1: Write failing tests for aggregation**

```python
# tests/api/test_whale_leaderboard.py
from datetime import datetime, timedelta
from src.api.routes.whale_leaderboard import (
    aggregate_by_token, aggregate_top_wallets, compute_composite_scores,
)

NOW = datetime(2026, 4, 17, 12, 0, 0)

def _tx(token, wallet, direction, amount, minutes_ago=30, label=None):
    return {
        "signature": f"sig-{token}-{wallet}-{minutes_ago}",
        "wallet_address": wallet,
        "wallet_label": label,
        "token_address": token,
        "token_symbol": token.upper(),
        "token_name": f"Token {token}",
        "direction": direction,
        "amount_usd": amount,
        "tx_timestamp": NOW - timedelta(minutes=minutes_ago),
    }


def test_aggregate_by_token_sums_flows():
    rows = [
        _tx("wif", "w1", "buy", 100_000),
        _tx("wif", "w2", "buy", 200_000),
        _tx("wif", "w1", "sell", 50_000),
        _tx("bonk", "w3", "buy", 500_000),
    ]
    result = aggregate_by_token(rows, window_hours=6, now=NOW, prior_tokens=set())
    by_token = {r["token_address"]: r for r in result}
    assert by_token["wif"]["gross_buy_usd"] == 300_000
    assert by_token["wif"]["gross_sell_usd"] == 50_000
    assert by_token["wif"]["net_flow_usd"] == 250_000
    assert by_token["wif"]["distinct_buyers"] == 2
    assert by_token["wif"]["distinct_sellers"] == 1
    assert by_token["wif"]["tx_count"] == 3


def test_is_new_on_radar_flag():
    rows = [_tx("wif", "w1", "buy", 100_000)]
    result = aggregate_by_token(rows, window_hours=6, now=NOW, prior_tokens={"bonk"})
    assert result[0]["is_new_on_radar"] is True
    result2 = aggregate_by_token(rows, window_hours=6, now=NOW, prior_tokens={"wif"})
    assert result2[0]["is_new_on_radar"] is False


def test_acceleration_ratio():
    # 3 buys in the most recent quarter (last 90 min of a 6h window),
    # 1 buy in the earlier three-quarters. pace ratio = (3/1.5h) / (1/4.5h) = 9.
    rows = [
        _tx("wif", "w1", "buy", 100_000, minutes_ago=30),
        _tx("wif", "w2", "buy", 100_000, minutes_ago=60),
        _tx("wif", "w3", "buy", 100_000, minutes_ago=80),
        _tx("wif", "w4", "buy", 100_000, minutes_ago=300),
    ]
    result = aggregate_by_token(rows, window_hours=6, now=NOW, prior_tokens=set())
    assert result[0]["acceleration"] > 2.0


def test_composite_score_ranks_by_blend():
    # Two tokens; one has more distinct buyers, the other has bigger net flow.
    rows = [
        _tx("wif", "w1", "buy", 100_000),
        _tx("wif", "w2", "buy", 100_000),
        _tx("wif", "w3", "buy", 100_000),
        _tx("bonk", "w1", "buy", 2_000_000),
    ]
    aggregated = aggregate_by_token(rows, window_hours=6, now=NOW, prior_tokens=set())
    scored = compute_composite_scores(aggregated)
    by_token = {r["token_address"]: r for r in scored}
    # distinct_buyers is weighted 0.40 — WIF should outrank BONK despite smaller flow
    assert by_token["wif"]["composite_score"] > by_token["bonk"]["composite_score"]


def test_aggregate_top_wallets_collapses_across_tokens():
    rows = [
        _tx("wif", "w1", "buy", 100_000, label="Alameda"),
        _tx("bonk", "w1", "buy", 200_000, label="Alameda"),
        _tx("wif", "w2", "sell", 50_000),
    ]
    wallets = aggregate_top_wallets(rows)
    by_addr = {w["address"]: w for w in wallets}
    assert by_addr["w1"]["total_volume_usd"] == 300_000
    assert by_addr["w1"]["tx_count"] == 2
    assert by_addr["w1"]["tokens_touched"] == 2
    assert by_addr["w1"]["label"] == "Alameda"
    assert by_addr["w1"]["dominant_side"] == "buy"


def test_top_wallets_dominant_side_mixed():
    rows = [
        _tx("wif", "w1", "buy", 100_000),
        _tx("wif", "w1", "sell", 100_000),
    ]
    wallets = aggregate_top_wallets(rows)
    assert wallets[0]["dominant_side"] == "mixed"
```

- [ ] **Step 2: Run — expect failure**

Run: `pytest tests/api/test_whale_leaderboard.py -v`
Expected: FAIL (module not found or functions missing)

- [ ] **Step 3: Implement pure aggregation functions**

```python
# src/api/routes/whale_leaderboard.py
"""Whale token leaderboard + top wallets routes.

Computes per-window aggregations on demand from the whale_transactions table.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Set

from aiohttp import web

from src.api.response_envelope import envelope_error_response, envelope_response

logger = logging.getLogger(__name__)

VALID_WINDOWS = {"1h": 1, "6h": 6, "24h": 24}
VALID_SORTS = {"composite", "buyers", "new"}
DEFAULT_WINDOW = "6h"
DEFAULT_SORT = "composite"
LEADERBOARD_LIMIT_MAX = 100
TOP_WALLETS_LIMIT_MAX = 50


def aggregate_by_token(
    rows: Iterable[Dict[str, Any]],
    *,
    window_hours: int,
    now: datetime,
    prior_tokens: Set[str],
) -> List[Dict[str, Any]]:
    """Group transactions by token and compute per-token metrics."""
    window_cutoff = now - timedelta(hours=window_hours)
    recent_cutoff = now - timedelta(hours=window_hours / 4)

    by_token: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        token = r["token_address"]
        if token not in by_token:
            by_token[token] = {
                "token_address": token,
                "token_symbol": r.get("token_symbol", "???"),
                "token_name": r.get("token_name", "Unknown"),
                "gross_buy_usd": 0.0,
                "gross_sell_usd": 0.0,
                "buyers": set(),
                "sellers": set(),
                "tx_count": 0,
                "recent_tx_count": 0,
                "older_tx_count": 0,
                "whale_volume": {},  # address -> {"amount_usd", "side", "label"}
            }
        agg = by_token[token]
        amount = float(r.get("amount_usd", 0))
        direction = r.get("direction")
        wallet = r.get("wallet_address", "")

        if direction == "buy":
            agg["gross_buy_usd"] += amount
            if wallet:
                agg["buyers"].add(wallet)
        else:
            agg["gross_sell_usd"] += amount
            if wallet:
                agg["sellers"].add(wallet)
        agg["tx_count"] += 1

        ts = r.get("tx_timestamp")
        if isinstance(ts, datetime):
            if ts >= recent_cutoff:
                agg["recent_tx_count"] += 1
            elif ts >= window_cutoff:
                agg["older_tx_count"] += 1

        if wallet:
            entry = agg["whale_volume"].setdefault(
                wallet,
                {"amount_usd": 0.0, "side": direction, "label": r.get("wallet_label")},
            )
            entry["amount_usd"] += amount
            if entry["label"] is None and r.get("wallet_label"):
                entry["label"] = r.get("wallet_label")

    results: List[Dict[str, Any]] = []
    for token, agg in by_token.items():
        buy_sell_ratio = agg["gross_buy_usd"] / max(agg["gross_sell_usd"], 1.0)
        buy_sell_ratio = min(buy_sell_ratio, 100.0)
        recent = agg["recent_tx_count"]
        older = agg["older_tx_count"]
        # recent pace per hour vs older pace per hour
        recent_pace = recent / max(window_hours / 4, 1e-6)
        older_pace = older / max(window_hours * 3 / 4, 1e-6)
        acceleration = recent_pace / max(older_pace, 1.0)

        top_whales = sorted(
            [
                {"address": addr, **v}
                for addr, v in agg["whale_volume"].items()
            ],
            key=lambda x: x["amount_usd"],
            reverse=True,
        )[:3]

        results.append({
            "token_address": token,
            "token_symbol": agg["token_symbol"],
            "token_name": agg["token_name"],
            "net_flow_usd": agg["gross_buy_usd"] - agg["gross_sell_usd"],
            "gross_buy_usd": agg["gross_buy_usd"],
            "gross_sell_usd": agg["gross_sell_usd"],
            "distinct_buyers": len(agg["buyers"]),
            "distinct_sellers": len(agg["sellers"]),
            "tx_count": agg["tx_count"],
            "buy_sell_ratio": buy_sell_ratio,
            "acceleration": acceleration,
            "is_new_on_radar": token not in prior_tokens,
            "top_whales": top_whales,
        })
    return results


def _percentile_rank(values: List[float]) -> Dict[int, float]:
    """Return 0..1 percentile for each index; stable for ties."""
    n = len(values)
    if n == 0:
        return {}
    indexed = sorted(range(n), key=lambda i: values[i])
    ranks: Dict[int, float] = {}
    for rank_idx, original_idx in enumerate(indexed):
        ranks[original_idx] = rank_idx / max(n - 1, 1)
    return ranks


def compute_composite_scores(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not rows:
        return rows
    buyers = [float(r["distinct_buyers"]) for r in rows]
    net = [max(float(r["net_flow_usd"]), 0.0) for r in rows]
    ratio = [float(r["buy_sell_ratio"]) for r in rows]
    accel = [float(r["acceleration"]) for r in rows]

    pr_buyers = _percentile_rank(buyers)
    pr_net = _percentile_rank(net)
    pr_ratio = _percentile_rank(ratio)
    pr_accel = _percentile_rank(accel)

    out = []
    for i, r in enumerate(rows):
        score = 100 * (
            0.40 * pr_buyers.get(i, 0.0)
            + 0.30 * pr_net.get(i, 0.0)
            + 0.20 * pr_ratio.get(i, 0.0)
            + 0.10 * pr_accel.get(i, 0.0)
        )
        out.append({**r, "composite_score": round(score, 1)})
    return out


def aggregate_top_wallets(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_wallet: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        wallet = r.get("wallet_address") or ""
        if not wallet:
            continue
        agg = by_wallet.setdefault(wallet, {
            "address": wallet,
            "label": r.get("wallet_label"),
            "gross_buy_usd": 0.0,
            "gross_sell_usd": 0.0,
            "tx_count": 0,
            "tokens": set(),
        })
        amount = float(r.get("amount_usd", 0))
        if r.get("direction") == "buy":
            agg["gross_buy_usd"] += amount
        else:
            agg["gross_sell_usd"] += amount
        agg["tx_count"] += 1
        if r.get("token_address"):
            agg["tokens"].add(r["token_address"])
        if agg["label"] is None and r.get("wallet_label"):
            agg["label"] = r.get("wallet_label")

    out: List[Dict[str, Any]] = []
    for wallet, agg in by_wallet.items():
        total = agg["gross_buy_usd"] + agg["gross_sell_usd"]
        if total == 0:
            dominant = "mixed"
        else:
            buy_frac = agg["gross_buy_usd"] / total
            if buy_frac > 0.6:
                dominant = "buy"
            elif buy_frac < 0.4:
                dominant = "sell"
            else:
                dominant = "mixed"
        out.append({
            "address": wallet,
            "label": agg["label"],
            "total_volume_usd": total,
            "tx_count": agg["tx_count"],
            "tokens_touched": len(agg["tokens"]),
            "dominant_side": dominant,
        })
    out.sort(key=lambda w: w["total_volume_usd"], reverse=True)
    return out
```

- [ ] **Step 4: Run — expect pass**

Run: `pytest tests/api/test_whale_leaderboard.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```
git add src/api/routes/whale_leaderboard.py tests/api/test_whale_leaderboard.py
git commit -m "feat(whale): aggregation helpers for leaderboard + top wallets"
```

---

## Task 3: Route handlers

**Files:**
- Modify: `src/api/routes/whale_leaderboard.py` (append)
- Modify: `tests/api/test_whale_leaderboard.py` (append route tests)

- [ ] **Step 1: Append route tests**

```python
# tests/api/test_whale_leaderboard.py (append)
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient

from src.api.routes.whale_leaderboard import setup_whale_leaderboard_routes


def _mock_db_with(rows, prior=None):
    mock = AsyncMock()
    mock.get_whale_aggregations = AsyncMock(return_value={
        "rows": rows, "prior_token_addresses": prior or set(),
    })
    return mock


@pytest.mark.asyncio
async def test_leaderboard_returns_ranked_rows():
    rows = [_tx("wif", "w1", "buy", 100_000), _tx("wif", "w2", "buy", 200_000)]
    app = web.Application()
    setup_whale_leaderboard_routes(app)
    with patch("src.api.routes.whale_leaderboard.get_database", return_value=_mock_db_with(rows)):
        server = TestServer(app); client = TestClient(server)
        await server.start_server()
        try:
            resp = await client.get("/api/v1/whales/leaderboard?window=6h")
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "ok"
            assert body["data"]["window"] == "6h"
            assert len(body["data"]["rows"]) == 1
            assert body["data"]["rows"][0]["token_address"] == "wif"
            assert "composite_score" in body["data"]["rows"][0]
        finally:
            await client.close(); await server.close()


@pytest.mark.asyncio
async def test_leaderboard_invalid_window_400():
    app = web.Application()
    setup_whale_leaderboard_routes(app)
    with patch("src.api.routes.whale_leaderboard.get_database", return_value=_mock_db_with([])):
        server = TestServer(app); client = TestClient(server)
        await server.start_server()
        try:
            resp = await client.get("/api/v1/whales/leaderboard?window=99h")
            assert resp.status == 400
        finally:
            await client.close(); await server.close()


@pytest.mark.asyncio
async def test_leaderboard_empty_returns_ok_with_empty_rows():
    app = web.Application()
    setup_whale_leaderboard_routes(app)
    with patch("src.api.routes.whale_leaderboard.get_database", return_value=_mock_db_with([])):
        server = TestServer(app); client = TestClient(server)
        await server.start_server()
        try:
            resp = await client.get("/api/v1/whales/leaderboard?window=1h")
            assert resp.status == 200
            body = await resp.json()
            assert body["data"]["rows"] == []
        finally:
            await client.close(); await server.close()


@pytest.mark.asyncio
async def test_top_wallets_returns_rows():
    rows = [_tx("wif", "w1", "buy", 100_000, label="Alameda")]
    app = web.Application()
    setup_whale_leaderboard_routes(app)
    with patch("src.api.routes.whale_leaderboard.get_database", return_value=_mock_db_with(rows)):
        server = TestServer(app); client = TestClient(server)
        await server.start_server()
        try:
            resp = await client.get("/api/v1/whales/top-wallets?window=6h")
            assert resp.status == 200
            body = await resp.json()
            assert body["data"]["rows"][0]["address"] == "w1"
            assert body["data"]["rows"][0]["label"] == "Alameda"
        finally:
            await client.close(); await server.close()


@pytest.mark.asyncio
async def test_leaderboard_db_exception_returns_500_envelope():
    app = web.Application()
    setup_whale_leaderboard_routes(app)
    mock = AsyncMock()
    mock.get_whale_aggregations = AsyncMock(side_effect=Exception("boom"))
    with patch("src.api.routes.whale_leaderboard.get_database", return_value=mock):
        server = TestServer(app); client = TestClient(server)
        await server.start_server()
        try:
            resp = await client.get("/api/v1/whales/leaderboard?window=6h")
            assert resp.status == 500
            body = await resp.json()
            assert body["status"] == "error"
            assert body["errors"][0]["code"] == "LEADERBOARD_FAILED"
        finally:
            await client.close(); await server.close()
```

- [ ] **Step 2: Implement route handlers + setup**

Append to `src/api/routes/whale_leaderboard.py`:

```python
async def get_database():
    from src.storage.database import get_database as _gd
    return await _gd()


def _parse_window(request: web.Request) -> tuple[str, int] | None:
    window = request.query.get("window", DEFAULT_WINDOW)
    if window not in VALID_WINDOWS:
        return None
    return window, VALID_WINDOWS[window]


def _parse_int(value: str, default: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, max_value))


async def get_leaderboard(request: web.Request) -> web.Response:
    parsed = _parse_window(request)
    if parsed is None:
        return envelope_error_response(
            "window must be one of: 1h, 6h, 24h",
            code="INVALID_PARAMS", http_status=400,
        )
    window, hours = parsed
    sort = request.query.get("sort", DEFAULT_SORT)
    if sort not in VALID_SORTS:
        return envelope_error_response(
            "sort must be one of: composite, buyers, new",
            code="INVALID_PARAMS", http_status=400,
        )
    limit = _parse_int(request.query.get("limit", "50"), 50, LEADERBOARD_LIMIT_MAX)

    try:
        db = await get_database()
        data = await db.get_whale_aggregations(hours=hours)
        rows = data.get("rows", [])
        prior = data.get("prior_token_addresses", set())
        aggregated = aggregate_by_token(rows, window_hours=hours, now=datetime.utcnow(), prior_tokens=prior)
        scored = compute_composite_scores(aggregated)

        if sort == "composite":
            scored.sort(key=lambda r: r["composite_score"], reverse=True)
        elif sort == "buyers":
            scored.sort(key=lambda r: r["distinct_buyers"], reverse=True)
        elif sort == "new":
            scored.sort(key=lambda r: (r["is_new_on_radar"], r["composite_score"]), reverse=True)

        scored = scored[:limit]
        return envelope_response({
            "window": window,
            "sort": sort,
            "rows": scored,
            "updated_at": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.error("leaderboard failed: %s", e, exc_info=True)
        return envelope_error_response(
            "Failed to compute leaderboard", code="LEADERBOARD_FAILED",
            details={"message": str(e)}, http_status=500,
        )


async def get_top_wallets(request: web.Request) -> web.Response:
    parsed = _parse_window(request)
    if parsed is None:
        return envelope_error_response(
            "window must be one of: 1h, 6h, 24h",
            code="INVALID_PARAMS", http_status=400,
        )
    window, hours = parsed
    limit = _parse_int(request.query.get("limit", "15"), 15, TOP_WALLETS_LIMIT_MAX)

    try:
        db = await get_database()
        data = await db.get_whale_aggregations(hours=hours)
        rows = data.get("rows", [])
        wallets = aggregate_top_wallets(rows)[:limit]
        return envelope_response({
            "window": window,
            "rows": wallets,
            "updated_at": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.error("top-wallets failed: %s", e, exc_info=True)
        return envelope_error_response(
            "Failed to compute top wallets", code="TOP_WALLETS_FAILED",
            details={"message": str(e)}, http_status=500,
        )


def setup_whale_leaderboard_routes(app: web.Application) -> None:
    app.router.add_get("/api/v1/whales/leaderboard", get_leaderboard)
    app.router.add_get("/api/v1/whales/top-wallets", get_top_wallets)
    logger.info("Whale leaderboard routes registered")
```

- [ ] **Step 3: Run route tests**

Run: `pytest tests/api/test_whale_leaderboard.py -v`
Expected: PASS (all ~11 tests)

- [ ] **Step 4: Register routes in app factory**

Modify `src/api/app.py`: add import and setup call alongside `setup_whale_routes`.

- [ ] **Step 5: Commit**

```
git add src/api/routes/whale_leaderboard.py tests/api/test_whale_leaderboard.py src/api/app.py
git commit -m "feat(api): whale leaderboard and top-wallets endpoints"
```

---

## Task 4: Frontend types + API client + hooks

**Files:**
- Modify: `web/types/index.ts`
- Modify: `web/lib/api.ts`
- Modify: `web/lib/hooks.ts`

- [ ] **Step 1: Add types**

```ts
// web/types/index.ts (append near whale types)
export type WhaleWindow = "1h" | "6h" | "24h";
export type WhaleSort = "composite" | "buyers" | "new";

export interface WhaleLeaderboardTopWhale {
  address: string;
  label: string | null;
  side: "buy" | "sell";
  amount_usd: number;
}

export interface WhaleLeaderboardRow {
  token_address: string;
  token_symbol: string;
  token_name: string;
  net_flow_usd: number;
  gross_buy_usd: number;
  gross_sell_usd: number;
  distinct_buyers: number;
  distinct_sellers: number;
  tx_count: number;
  buy_sell_ratio: number;
  acceleration: number;
  is_new_on_radar: boolean;
  composite_score: number;
  top_whales: WhaleLeaderboardTopWhale[];
}

export interface WhaleLeaderboardResponse {
  window: WhaleWindow;
  sort: WhaleSort;
  rows: WhaleLeaderboardRow[];
  updated_at: string;
}

export interface TopWhaleRow {
  address: string;
  label: string | null;
  total_volume_usd: number;
  tx_count: number;
  tokens_touched: number;
  dominant_side: "buy" | "sell" | "mixed";
}

export interface TopWhalesResponse {
  window: WhaleWindow;
  rows: TopWhaleRow[];
  updated_at: string;
}
```

- [ ] **Step 2: Add API clients**

```ts
// web/lib/api.ts (append to WHALE API section)
export async function getWhaleLeaderboard(params: {
  window?: WhaleWindow;
  sort?: WhaleSort;
  limit?: number;
} = {}): Promise<WhaleLeaderboardResponse> {
  const sp = new URLSearchParams();
  if (params.window) sp.set("window", params.window);
  if (params.sort) sp.set("sort", params.sort);
  if (params.limit) sp.set("limit", params.limit.toString());
  const q = sp.toString();
  const raw = await fetchAPI<any>(`/api/v1/whales/leaderboard${q ? `?${q}` : ""}`);
  const data = unwrapEnvelope<WhaleLeaderboardResponse>(raw, {
    window: (params.window ?? "6h") as WhaleWindow,
    sort: (params.sort ?? "composite") as WhaleSort,
    rows: [],
    updated_at: new Date().toISOString(),
  });
  return data;
}

export async function getTopWhales(params: {
  window?: WhaleWindow;
  limit?: number;
} = {}): Promise<TopWhalesResponse> {
  const sp = new URLSearchParams();
  if (params.window) sp.set("window", params.window);
  if (params.limit) sp.set("limit", params.limit.toString());
  const q = sp.toString();
  const raw = await fetchAPI<any>(`/api/v1/whales/top-wallets${q ? `?${q}` : ""}`);
  const data = unwrapEnvelope<TopWhalesResponse>(raw, {
    window: (params.window ?? "6h") as WhaleWindow,
    rows: [],
    updated_at: new Date().toISOString(),
  });
  return data;
}
```

(Add `WhaleWindow, WhaleSort, WhaleLeaderboardResponse, TopWhalesResponse` to the existing type import from `../types`.)

- [ ] **Step 3: Add hooks**

```ts
// web/lib/hooks.ts (append to whale section)
export function useWhaleLeaderboard(params: { window: WhaleWindow; sort: WhaleSort }) {
  return useQuery({
    queryKey: ["whales", "leaderboard", params.window, params.sort],
    queryFn: () => api.getWhaleLeaderboard(params),
    staleTime: 60_000,
  });
}

export function useTopWhales(params: { window: WhaleWindow }) {
  return useQuery({
    queryKey: ["whales", "top", params.window],
    queryFn: () => api.getTopWhales(params),
    staleTime: 60_000,
  });
}
```

- [ ] **Step 4: Commit**

```
git add web/types/index.ts web/lib/api.ts web/lib/hooks.ts
git commit -m "feat(web): whale leaderboard + top-wallets types, client, hooks"
```

---

## Task 5: Frontend components

**Files:**
- Create: `web/app/whales/_components/window-sort-controls.tsx`
- Create: `web/app/whales/_components/leaderboard-row.tsx`
- Create: `web/app/whales/_components/top-whales-panel.tsx`
- Create: `web/app/whales/_components/empty-state.tsx`

- [ ] **Step 1: window-sort-controls.tsx**

```tsx
"use client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { WhaleWindow, WhaleSort } from "@/types";

const WINDOWS: WhaleWindow[] = ["1h", "6h", "24h"];
const SORTS: { value: WhaleSort; label: string }[] = [
  { value: "composite", label: "Score" },
  { value: "buyers", label: "Buyers" },
  { value: "new", label: "New" },
];

export function WindowSortControls({
  window, sort, onWindowChange, onSortChange,
}: {
  window: WhaleWindow;
  sort: WhaleSort;
  onWindowChange: (w: WhaleWindow) => void;
  onSortChange: (s: WhaleSort) => void;
}) {
  return (
    <div className="flex flex-wrap gap-4 items-center">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Window:</span>
        {WINDOWS.map((w) => (
          <Button
            key={w}
            size="sm"
            variant={window === w ? "default" : "outline"}
            onClick={() => onWindowChange(w)}
          >{w}</Button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Sort:</span>
        {SORTS.map((s) => (
          <Button
            key={s.value}
            size="sm"
            variant={sort === s.value ? "default" : "outline"}
            onClick={() => onSortChange(s.value)}
          >{s.label}</Button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: leaderboard-row.tsx**

```tsx
"use client";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { GlassCard } from "@/components/ui/card";
import { TrendingUp, Zap, Sparkles } from "lucide-react";
import { cn, formatUSD, truncateAddress } from "@/lib/utils";
import type { WhaleLeaderboardRow } from "@/types";

export function LeaderboardRow({ row, rank }: { row: WhaleLeaderboardRow; rank: number }) {
  const accelerating = row.acceleration >= 2.0;
  return (
    <GlassCard className="hover:border-emerald-500/30 transition">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="text-xl font-bold text-muted-foreground w-8 text-center">#{rank}</div>
          <div>
            <Link href={`/token/${row.token_address}`} className="font-semibold hover:text-emerald-400 transition">
              {row.token_symbol}
              <span className="text-muted-foreground font-normal ml-2">{row.token_name}</span>
            </Link>
            <div className="flex flex-wrap gap-2 mt-2 text-xs">
              {row.is_new_on_radar && (
                <Badge variant="outline" className="border-emerald-500/50 text-emerald-400 gap-1">
                  <Sparkles className="h-3 w-3" /> New on radar
                </Badge>
              )}
              {accelerating && (
                <Badge variant="outline" className="border-yellow-500/50 text-yellow-400 gap-1">
                  <Zap className="h-3 w-3" /> Accelerating
                </Badge>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="text-right">
            <div className="font-mono font-bold text-emerald-400">+{formatUSD(row.net_flow_usd)}</div>
            <div className="text-xs text-muted-foreground">net flow</div>
          </div>
          <div className="text-right">
            <div className="font-mono font-bold">{row.distinct_buyers}</div>
            <div className="text-xs text-muted-foreground">buyers</div>
          </div>
          <div className="text-right">
            <div className="font-mono font-bold text-lg">{row.composite_score.toFixed(0)}</div>
            <div className="text-xs text-muted-foreground">score</div>
          </div>
        </div>
      </div>

      {row.top_whales.length > 0 && (
        <div className="mt-3 pt-3 border-t border-white/5 flex flex-wrap gap-2 text-xs">
          <span className="text-muted-foreground">Top whales:</span>
          {row.top_whales.map((w) => (
            <Badge key={w.address} variant="secondary" className="font-mono">
              {w.label ?? truncateAddress(w.address, 4)} · {formatUSD(w.amount_usd)}
            </Badge>
          ))}
        </div>
      )}
    </GlassCard>
  );
}
```

- [ ] **Step 3: top-whales-panel.tsx**

```tsx
"use client";
import Link from "next/link";
import { GlassCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn, formatUSD, truncateAddress } from "@/lib/utils";
import type { TopWhaleRow } from "@/types";

export function TopWhalesPanel({
  rows, isError, isLoading,
}: {
  rows: TopWhaleRow[];
  isError?: boolean;
  isLoading?: boolean;
}) {
  return (
    <GlassCard>
      <h3 className="font-semibold mb-4 flex items-center gap-2">
        🐋 Top Whales
      </h3>
      {isError && <p className="text-sm text-red-400">Failed to load whales</p>}
      {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
      {!isLoading && !isError && rows.length === 0 && (
        <p className="text-sm text-muted-foreground">No active whales in this window.</p>
      )}
      <ul className="space-y-3">
        {rows.map((w) => (
          <li key={w.address} className="border-b border-white/5 pb-3 last:border-0">
            <Link href={`/whales/wallet/${w.address}`} className="hover:text-emerald-400 transition">
              <div className="flex items-center justify-between">
                <div className="font-mono text-sm">
                  {w.label ?? truncateAddress(w.address, 6)}
                </div>
                <Badge variant="outline" className={cn(
                  "text-xs",
                  w.dominant_side === "buy" && "border-emerald-500/50 text-emerald-400",
                  w.dominant_side === "sell" && "border-red-500/50 text-red-400",
                )}>
                  {w.dominant_side}
                </Badge>
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {formatUSD(w.total_volume_usd)} · {w.tx_count} tx · {w.tokens_touched} tokens
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </GlassCard>
  );
}
```

- [ ] **Step 4: empty-state.tsx**

```tsx
"use client";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/card";
import { Fish } from "lucide-react";
import type { WhaleWindow } from "@/types";

export function EmptyState({ onJumpToWide }: { onJumpToWide: (w: WhaleWindow) => void }) {
  return (
    <GlassCard className="text-center py-12">
      <Fish className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
      <h3 className="text-lg font-semibold mb-2">Quiet hour</h3>
      <p className="text-muted-foreground mb-4">
        No whale activity in this window. Try a wider lookback.
      </p>
      <Button onClick={() => onJumpToWide("24h")}>Show last 24h</Button>
    </GlassCard>
  );
}
```

- [ ] **Step 5: Commit**

```
git add web/app/whales/_components
git commit -m "feat(web): whale leaderboard UI components"
```

---

## Task 6: Rewrite whales page

**Files:**
- Modify (rewrite): `web/app/whales/page.tsx`
- Modify (rewrite): `web/tests/app/whales.page.test.tsx`

- [ ] **Step 1: Rewrite page.tsx**

```tsx
"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useWhaleLeaderboard, useTopWhales } from "@/lib/hooks";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Fish, Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import type { WhaleWindow, WhaleSort } from "@/types";
import { WindowSortControls } from "./_components/window-sort-controls";
import { LeaderboardRow } from "./_components/leaderboard-row";
import { TopWhalesPanel } from "./_components/top-whales-panel";
import { EmptyState } from "./_components/empty-state";

export default function WhalesPage() {
  const [window, setWindow] = useState<WhaleWindow>("6h");
  const [sort, setSort] = useState<WhaleSort>("composite");
  const queryClient = useQueryClient();

  const leaderboard = useWhaleLeaderboard({ window, sort });
  const topWhales = useTopWhales({ window });

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["whales"] });
  };

  const rows = leaderboard.data?.rows ?? [];
  const busy = leaderboard.isFetching || topWhales.isFetching;

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
            <Fish className="h-8 w-8 text-emerald-500" /> Whale Tracker
          </h1>
          <p className="text-muted-foreground">
            What whales are buying right now — ranked by signal strength
          </p>
        </div>
        <Button variant="outline" onClick={handleRefresh} disabled={busy}>
          <RefreshCw className={cn("h-4 w-4 mr-2", busy && "animate-spin")} /> Refresh
        </Button>
      </div>

      <GlassCard className="mb-8">
        <WindowSortControls
          window={window}
          sort={sort}
          onWindowChange={setWindow}
          onSortChange={setSort}
        />
      </GlassCard>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_320px] gap-6">
        <div className="space-y-4">
          {leaderboard.isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
            </div>
          )}
          {leaderboard.isError && (
            <GlassCard className="text-center py-8 text-red-400">
              Failed to load leaderboard. Try again.
            </GlassCard>
          )}
          {!leaderboard.isLoading && !leaderboard.isError && rows.length === 0 && (
            <EmptyState onJumpToWide={setWindow} />
          )}
          {rows.map((row, i) => (
            <LeaderboardRow key={row.token_address} row={row} rank={i + 1} />
          ))}
        </div>

        <aside>
          <TopWhalesPanel
            rows={topWhales.data?.rows ?? []}
            isError={topWhales.isError}
            isLoading={topWhales.isLoading}
          />
        </aside>
      </div>

      {leaderboard.data && rows.length > 0 && (
        <div className="text-center text-sm text-muted-foreground mt-8">
          Window: {window} · Last updated:{" "}
          {new Date(leaderboard.data.updated_at).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Rewrite whales.page.test.tsx**

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import WhalesPage from "@/app/whales/page";
import * as api from "@/lib/api";

vi.mock("@/lib/api");

const leaderboardResponse = {
  window: "6h",
  sort: "composite",
  rows: [
    {
      token_address: "wif-addr",
      token_symbol: "WIF",
      token_name: "dogwifhat",
      net_flow_usd: 2_400_000,
      gross_buy_usd: 2_700_000,
      gross_sell_usd: 300_000,
      distinct_buyers: 8,
      distinct_sellers: 2,
      tx_count: 14,
      buy_sell_ratio: 9,
      acceleration: 2.4,
      is_new_on_radar: true,
      composite_score: 87.0,
      top_whales: [{ address: "w1", label: "Alameda", side: "buy", amount_usd: 800_000 }],
    },
  ],
  updated_at: "2026-04-17T12:00:00",
};

const topWhalesResponse = {
  window: "6h",
  rows: [
    {
      address: "w1", label: "Alameda", total_volume_usd: 4_200_000,
      tx_count: 12, tokens_touched: 5, dominant_side: "buy",
    },
  ],
  updated_at: "2026-04-17T12:00:00",
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WhalesPage />
    </QueryClientProvider>
  );
}

describe("WhalesPage", () => {
  beforeEach(() => {
    vi.mocked(api.getWhaleLeaderboard).mockResolvedValue(leaderboardResponse as any);
    vi.mocked(api.getTopWhales).mockResolvedValue(topWhalesResponse as any);
  });

  it("renders the leaderboard and sidebar", async () => {
    renderPage();
    expect(await screen.findByText("WIF")).toBeInTheDocument();
    expect(await screen.findByText("Alameda")).toBeInTheDocument();
    expect(screen.getByText(/new on radar/i)).toBeInTheDocument();
    expect(screen.getByText(/accelerating/i)).toBeInTheDocument();
  });

  it("renders empty state when leaderboard is empty", async () => {
    vi.mocked(api.getWhaleLeaderboard).mockResolvedValue({
      ...leaderboardResponse,
      rows: [],
    } as any);
    renderPage();
    expect(await screen.findByText(/quiet hour/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /show last 24h/i })).toBeInTheDocument();
  });

  it("changing window triggers refetch with new key", async () => {
    renderPage();
    await screen.findByText("WIF");
    const oneHourBtn = screen.getByRole("button", { name: "1h" });
    await userEvent.click(oneHourBtn);
    expect(api.getWhaleLeaderboard).toHaveBeenCalledWith(
      expect.objectContaining({ window: "1h" })
    );
  });

  it("sidebar failure does not unmount leaderboard", async () => {
    vi.mocked(api.getTopWhales).mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByText("WIF")).toBeInTheDocument();
    expect(screen.getByText(/failed to load whales/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run frontend tests**

Run: `cd web && npx vitest run tests/app/whales.page.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```
git add web/app/whales/page.tsx web/tests/app/whales.page.test.tsx
git commit -m "feat(web): rewrite /whales page as ranked leaderboard"
```

---

## Task 7: Live validation

- [ ] **Step 1: Start backend**

`python -m src.main` (or `docker compose up api`) in one shell.

- [ ] **Step 2: Curl leaderboard**

```
curl -s http://localhost:8000/api/v1/whales/leaderboard?window=6h | jq '.status,.data.rows|length'
```
Expected: `"ok"` and a non-negative integer.

- [ ] **Step 3: Curl top-wallets**

```
curl -s http://localhost:8000/api/v1/whales/top-wallets?window=6h | jq '.status,.data.rows|length'
```
Expected: `"ok"` and a non-negative integer.

- [ ] **Step 4: Curl invalid window**

```
curl -s -o /dev/null -w "%{http_code}\n" 'http://localhost:8000/api/v1/whales/leaderboard?window=99h'
```
Expected: `400`.

- [ ] **Step 5: Curl all windows**

```
for w in 1h 6h 24h; do echo -n "$w: "; curl -s "http://localhost:8000/api/v1/whales/leaderboard?window=$w" | jq '.status'; done
```
Expected: three `"ok"` lines.

- [ ] **Step 6: Frontend dev server + manual check**

`cd web && npm run dev` — navigate to `http://localhost:3000/whales`. Verify:
  - leaderboard + sidebar render
  - window pills switch data
  - sort pills reorder rows
  - row link navigates to `/token/[address]`
  - sidebar item navigates to `/whales/wallet/[address]`
