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
