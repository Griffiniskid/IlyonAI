"""
Chains API routes.

GET /api/v1/chains          — list all supported chains
GET /api/v1/chains/{chain}  — chain details (config, explorers, DEXes)
"""

import logging
from aiohttp import web

from src.chains.base import ChainType, EVM_CHAIN_CONFIGS
from src.api.schemas.responses import ChainInfoResponse, ChainsListResponse
from src.api.response_envelope import envelope_error_response, envelope_response

logger = logging.getLogger(__name__)

# Explorer URLs per chain
EXPLORER_URLS = {
    "solana": "https://solscan.io",
    "ethereum": "https://etherscan.io",
    "base": "https://basescan.org",
    "arbitrum": "https://arbiscan.io",
    "bsc": "https://bscscan.com",
    "polygon": "https://polygonscan.com",
    "optimism": "https://optimistic.etherscan.io",
    "avalanche": "https://snowtrace.io",
}

# Chain logos (emoji fallback until we have SVGs)
CHAIN_LOGOS = {
    "solana": "◎",
    "ethereum": "Ξ",
    "base": "🔵",
    "arbitrum": "🔷",
    "bsc": "🟡",
    "polygon": "🟣",
    "optimism": "🔴",
    "avalanche": "🔺",
}


async def list_chains(request: web.Request) -> web.Response:
    """
    GET /api/v1/chains

    Returns all supported chains with metadata.
    """
    chains = []
    for chain_type in ChainType:
        evm_config = EVM_CHAIN_CONFIGS.get(chain_type, {}) if chain_type.is_evm else {}
        chains.append(ChainInfoResponse(
            chain=chain_type.value,
            chain_id=chain_type.chain_id,
            display_name=chain_type.display_name,
            native_currency=chain_type.native_token_symbol,
            explorer_url=EXPLORER_URLS.get(chain_type.value, ""),
            is_evm=chain_type.is_evm,
            block_time_seconds=float(evm_config.get("block_time_seconds", 0.4 if chain_type == ChainType.SOLANA else 0)),
            logo=CHAIN_LOGOS.get(chain_type.value, ""),
            primary_dex=evm_config.get("primary_dex") if evm_config else ("Jupiter" if chain_type == ChainType.SOLANA else None),
        ).model_dump())

    return envelope_response({
        "chains": chains,
        "total": len(chains),
        "count": len(chains),
    })


async def get_chain_detail(request: web.Request) -> web.Response:
    """
    GET /api/v1/chains/{chain}

    Returns detailed info about a specific chain.
    """
    chain_name = request.match_info.get('chain', '').lower()

    # Find matching chain
    chain_type = None
    for ct in ChainType:
        if ct.value == chain_name:
            chain_type = ct
            break

    if not chain_type:
        return envelope_error_response(
            f"Unknown chain: {chain_name}",
            code="UNKNOWN_CHAIN",
            http_status=404,
        )

    # Get config if EVM
    evm_config = EVM_CHAIN_CONFIGS.get(chain_type) if chain_type.is_evm else None

    detail = {
        "chain": chain_type.value,
        "display_name": chain_type.display_name,
        "chain_id": chain_type.chain_id,
        "native_currency": chain_type.native_token_symbol,
        "explorer_url": EXPLORER_URLS.get(chain_type.value, ""),
        "is_evm": chain_type.is_evm,
        "logo": CHAIN_LOGOS.get(chain_type.value, ""),
        "block_time_seconds": 0.4 if chain_type == ChainType.SOLANA else 0,
    }

    if evm_config:
        detail["primary_dex"] = evm_config.get("primary_dex", "")
        detail["dex_router"] = evm_config.get("dex_router_address", "")
        detail["explorer_url"] = evm_config.get("explorer_url", EXPLORER_URLS.get(chain_type.value, ""))
        detail["block_time_seconds"] = evm_config.get("block_time_seconds", 0)

    return envelope_response(detail)


def setup_chains_routes(app: web.Application):
    """Register chain info routes."""
    app.router.add_get('/api/v1/chains', list_chains)
    app.router.add_get('/api/v1/chains/{chain}', get_chain_detail)
    logger.info("Chains routes registered")
