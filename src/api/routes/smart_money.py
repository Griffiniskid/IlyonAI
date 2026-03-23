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
    flows = []
    recent_transactions = []
    inflow_usd = 0.0
    outflow_usd = 0.0

    # Per-wallet aggregation keyed by (wallet_address, direction)
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
                token_symbol = tx.get("token_symbol")
                token_name = tx.get("token_name")
                token_address = tx.get("token_address")
                amount_tokens = tx.get("amount_tokens")
                dex_name = tx.get("dex_name")
                signature = tx.get("signature")
                timestamp = tx.get("timestamp", "")

                # Build flow entry
                flow_item = {
                    "direction": direction,
                    "amount_usd": amount,
                    "chain": chain,
                }
                flows.append(flow_item)

                # Build recent transaction entry with full context
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

                # Accumulate flow totals
                if direction == "inflow":
                    inflow_usd += amount
                else:
                    outflow_usd += amount

                # Per-wallet aggregation
                if wallet:
                    key = (wallet, direction)
                    entry = wallet_agg[key]
                    entry["wallet_address"] = wallet
                    entry["label"] = entry["label"] or label
                    entry["amount_usd"] += amount
                    entry["tx_count"] += 1
                    if timestamp and timestamp > entry["last_seen"]:
                        entry["last_seen"] = timestamp
                    if amount > entry["largest_tx_amount"]:
                        entry["largest_tx_amount"] = amount
                        entry["token_symbol"] = token_symbol
                        entry["dex_name"] = dex_name

    except Exception as e:
        logger.error(f"Smart money overview failed: {e}")
        return envelope_error_response(
            f"Failed to fetch smart money data: {e}",
            code="SMART_MONEY_FETCH_FAILED",
            http_status=502,
            meta={"surface": "smart_money_overview"},
        )

    # Separate buyers and sellers from aggregation
    top_buyers = []
    top_sellers = []
    for (wallet, direction), entry in wallet_agg.items():
        # Strip internal helper field before building response
        clean_entry = {
            "wallet_address": entry["wallet_address"],
            "label": entry["label"],
            "amount_usd": entry["amount_usd"],
            "tx_count": entry["tx_count"],
            "last_seen": entry["last_seen"],
            "token_symbol": entry["token_symbol"],
            "dex_name": entry["dex_name"],
        }
        if direction == "inflow":
            top_buyers.append(clean_entry)
        else:
            top_sellers.append(clean_entry)

    top_buyers.sort(key=lambda x: x["amount_usd"], reverse=True)
    top_sellers.sort(key=lambda x: x["amount_usd"], reverse=True)

    net_flow_usd = inflow_usd - outflow_usd
    total_volume = inflow_usd + outflow_usd

    # Derive flow direction
    if total_volume == 0:
        flow_direction = "neutral"
    elif inflow_usd > outflow_usd:
        flow_direction = "accumulating"
    else:
        flow_direction = "distributing"

    # Compute sell volume percent
    sell_volume_percent = (outflow_usd / total_volume * 100) if total_volume > 0 else 0

    payload = SmartMoneyOverviewResponse(
        net_flow_usd=net_flow_usd,
        inflow_usd=inflow_usd,
        outflow_usd=outflow_usd,
        top_buyers=top_buyers[:10],
        top_sellers=top_sellers[:10],
        flows=flows[:50],
        flow_direction=flow_direction,
        sell_volume_percent=sell_volume_percent,
        recent_transactions=recent_transactions,
        updated_at=datetime.utcnow().isoformat(),
    ).model_dump(mode="json")

    return envelope_response(payload, meta={"surface": "smart_money_overview"})


def setup_smart_money_routes(app: web.Application):
    app.router.add_get("/api/v1/smart-money/overview", get_smart_money_overview)
