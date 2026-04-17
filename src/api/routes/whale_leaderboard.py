"""Whale token leaderboard + top wallets routes.

Computes per-window aggregations on demand from the ``whale_transactions``
table populated by ``WhaleTransactionStream``. No new background job, no
new table — read-only views over existing data.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Set

from aiohttp import web

from src.api.response_envelope import envelope_error_response, envelope_response

logger = logging.getLogger(__name__)

VALID_WINDOWS: Dict[str, int] = {"1h": 1, "6h": 6, "24h": 24}
VALID_SORTS = {"composite", "buyers", "new"}
DEFAULT_WINDOW = "6h"
DEFAULT_SORT = "composite"
LEADERBOARD_LIMIT_MAX = 100
TOP_WALLETS_LIMIT_MAX = 50


# ═══════════════════════════════════════════════════════════════════════════
# Pure aggregation helpers (unit-tested independently of HTTP)
# ═══════════════════════════════════════════════════════════════════════════


def aggregate_by_token(
    rows: Iterable[Dict[str, Any]],
    *,
    window_hours: int,
    now: datetime,
    prior_tokens: Set[str],
) -> List[Dict[str, Any]]:
    """Group whale transactions by token and compute per-token metrics."""
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
                "whale_volume": {},
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

        recent_pace = agg["recent_tx_count"] / max(window_hours / 4, 1e-6)
        older_pace = agg["older_tx_count"] / max(window_hours * 3 / 4, 1e-6)
        acceleration = recent_pace / max(older_pace, 0.1)

        top_whales = sorted(
            [{"address": addr, **v} for addr, v in agg["whale_volume"].items()],
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
    """0..1 percentile for each index. Ties share the average rank so that
    tied inputs produce equal scores (not arbitrary stable-sort-order)."""
    n = len(values)
    if n == 0:
        return {}
    indexed = sorted(range(n), key=lambda i: values[i])
    ranks: Dict[int, float] = {}
    denom = max(n - 1, 1)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        avg_rank = (i + j) / 2
        pct = avg_rank / denom
        for k in range(i, j + 1):
            ranks[indexed[k]] = pct
        i = j + 1
    return ranks


def compute_composite_scores(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach a 0..100 composite_score to each row via percentile-rank blend."""
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


# ═══════════════════════════════════════════════════════════════════════════
# HTTP handlers
# ═══════════════════════════════════════════════════════════════════════════


async def get_database():
    from src.storage.database import get_database as _gd
    return await _gd()


def _parse_window(request: web.Request):
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
            code="INVALID_PARAMS",
            http_status=400,
        )
    window, hours = parsed
    sort = request.query.get("sort", DEFAULT_SORT)
    if sort not in VALID_SORTS:
        return envelope_error_response(
            "sort must be one of: composite, buyers, new",
            code="INVALID_PARAMS",
            http_status=400,
        )
    limit = _parse_int(request.query.get("limit", "50"), 50, LEADERBOARD_LIMIT_MAX)

    try:
        db = await get_database()
        data = await db.get_whale_aggregations(hours=hours)
        rows = data.get("rows", [])
        prior = data.get("prior_token_addresses", set())
        aggregated = aggregate_by_token(
            rows, window_hours=hours, now=datetime.utcnow(), prior_tokens=prior
        )
        scored = compute_composite_scores(aggregated)

        if sort == "composite":
            scored.sort(key=lambda r: r["composite_score"], reverse=True)
        elif sort == "buyers":
            scored.sort(key=lambda r: r["distinct_buyers"], reverse=True)
        elif sort == "new":
            scored.sort(
                key=lambda r: (r["is_new_on_radar"], r["composite_score"]),
                reverse=True,
            )

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
            "Failed to compute leaderboard",
            code="LEADERBOARD_FAILED",
            details={"message": str(e)},
            http_status=500,
        )


async def get_top_wallets(request: web.Request) -> web.Response:
    parsed = _parse_window(request)
    if parsed is None:
        return envelope_error_response(
            "window must be one of: 1h, 6h, 24h",
            code="INVALID_PARAMS",
            http_status=400,
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
            "Failed to compute top wallets",
            code="TOP_WALLETS_FAILED",
            details={"message": str(e)},
            http_status=500,
        )


def setup_whale_leaderboard_routes(app: web.Application) -> None:
    app.router.add_get("/api/v1/whales/leaderboard", get_leaderboard)
    app.router.add_get("/api/v1/whales/top-wallets", get_top_wallets)
    logger.info("Whale leaderboard routes registered")
