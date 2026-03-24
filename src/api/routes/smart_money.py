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
            meta={"surface": "smart_money_overview"},
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
