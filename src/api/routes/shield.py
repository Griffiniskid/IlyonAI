"""
Shield API routes: token approval scanning and revoke preparation.

GET  /api/v1/shield/{wallet}          - Scan wallet approvals across all EVM chains
GET  /api/v1/shield/{wallet}/{chain}  - Scan wallet approvals on a specific chain
POST /api/v1/shield/revoke            - Prepare revoke transaction calldata
"""

import logging
from datetime import datetime
from typing import Optional

from aiohttp import web

from src.chains.base import ChainType
from src.config import settings
from src.shield.approval_scanner import ApprovalScanner, encode_revoke_calldata
from src.api.response_envelope import envelope_error_response, envelope_response

logger = logging.getLogger(__name__)

_scanner: Optional[ApprovalScanner] = None


async def init_shield(app: web.Application):
    """Initialize approval scanner on app startup."""
    global _scanner
    _scanner = ApprovalScanner()
    logger.info("ApprovalScanner initialized")


async def cleanup_shield(app: web.Application):
    """Close approval scanner session on app shutdown."""
    global _scanner
    if _scanner:
        await _scanner.close()
        logger.info("ApprovalScanner closed")


def _parse_chain(chain_str: str) -> Optional[ChainType]:
    """Map a chain name string to ChainType enum."""
    mapping = {
        "ethereum": ChainType.ETHEREUM,
        "eth":      ChainType.ETHEREUM,
        "bsc":      ChainType.BSC,
        "bnb":      ChainType.BSC,
        "polygon":  ChainType.POLYGON,
        "matic":    ChainType.POLYGON,
        "arbitrum": ChainType.ARBITRUM,
        "arb":      ChainType.ARBITRUM,
        "base":     ChainType.BASE,
        "optimism": ChainType.OPTIMISM,
        "op":       ChainType.OPTIMISM,
        "avalanche":ChainType.AVALANCHE,
        "avax":     ChainType.AVALANCHE,
    }
    return mapping.get(chain_str.lower())


def _chain_display(chain: ChainType) -> str:
    chain_names = {
        ChainType.ETHEREUM:  "Ethereum",
        ChainType.BSC:       "BNB Chain",
        ChainType.POLYGON:   "Polygon",
        ChainType.ARBITRUM:  "Arbitrum",
        ChainType.BASE:      "Base",
        ChainType.OPTIMISM:  "Optimism",
        ChainType.AVALANCHE: "Avalanche",
    }
    return chain_names.get(chain, chain.value)


async def scan_wallet_approvals(request: web.Request) -> web.Response:
    """
    GET /api/v1/shield/{wallet}

    Scan a wallet's ERC-20 approvals across all supported EVM chains.

    Query params:
      chain (optional): restrict to a single chain
      min_risk (optional): filter to approvals with risk_score >= this value (0-100)
    """
    wallet = request.match_info.get("wallet", "").strip()
    if not wallet or not wallet.startswith("0x") or len(wallet) != 42:
        return envelope_error_response(
            "Invalid EVM wallet address. Must be 0x-prefixed, 42 chars.",
            code="INVALID_ADDRESS",
            http_status=400,
        )

    chain_param = request.rel_url.query.get("chain")
    min_risk_str = request.rel_url.query.get("min_risk", "0")
    try:
        min_risk = int(min_risk_str)
    except ValueError:
        min_risk = 0

    chains = None
    if chain_param:
        ct = _parse_chain(chain_param)
        if ct is None:
            return envelope_error_response(
                f"Unknown chain: {chain_param}",
                code="UNKNOWN_CHAIN",
                http_status=400,
            )
        chains = [ct]

    if _scanner is None:
        return envelope_error_response(
            "Shield scanner not available",
            code="SERVICE_UNAVAILABLE",
            http_status=503,
        )

    try:
        approvals = await _scanner.scan_wallet(wallet, chains=chains)
    except Exception as e:
        logger.error(f"Approval scan error for {wallet}: {e}")
        return envelope_error_response(
            "Approval scan failed",
            code="SCAN_FAILED",
            http_status=500,
        )

    if min_risk > 0:
        approvals = [a for a in approvals if a.get("risk_score", 0) >= min_risk]

    high_risk = [a for a in approvals if a.get("risk_level") in {"HIGH", "CRITICAL"}]
    medium_risk = [a for a in approvals if a.get("risk_level") == "MEDIUM"]
    low_risk = [a for a in approvals if a.get("risk_level") == "LOW"]

    scanned_chains = chains or [
        ChainType.ETHEREUM, ChainType.BSC, ChainType.POLYGON,
        ChainType.ARBITRUM, ChainType.BASE, ChainType.OPTIMISM,
        ChainType.AVALANCHE,
    ]

    return envelope_response({
        "wallet": wallet,
        "wallet_address": wallet,
        "chains_scanned": [c.value for c in scanned_chains],
        "chain_labels": {c.value: _chain_display(c) for c in scanned_chains},
        "scanned_at": datetime.utcnow().isoformat(),
        "summary": {
            "total_approvals": len(approvals),
            "high_risk_count": len(high_risk),
            "medium_risk_count": len(medium_risk),
            "low_risk_count": len(low_risk),
        },
        "approvals": approvals,
        "recommendation": (
            "Revoke HIGH risk approvals immediately, especially unlimited allowances to unknown contracts."
            if high_risk else
            "No critical approvals found. Review MEDIUM risk items when convenient."
        ),
    })


async def scan_wallet_chain(request: web.Request) -> web.Response:
    """
    GET /api/v1/shield/{wallet}/{chain}

    Scan approvals for a wallet on a specific chain.
    """
    wallet = request.match_info.get("wallet", "").strip()
    chain_str = request.match_info.get("chain", "").strip()

    if not wallet or not wallet.startswith("0x") or len(wallet) != 42:
        return web.json_response(
            {"error": "Invalid EVM wallet address"},
            status=400,
        )

    ct = _parse_chain(chain_str)
    if ct is None:
        return web.json_response({"error": f"Unknown chain: {chain_str}"}, status=400)

    if _scanner is None:
        return web.json_response({"error": "Shield scanner not available"}, status=503)

    try:
        approvals = await _scanner.scan_wallet(wallet, chains=[ct])
    except Exception as e:
        logger.error(f"Approval scan error for {wallet} on {chain_str}: {e}")
        return web.json_response({"error": "Approval scan failed"}, status=500)

    return web.json_response({
        "wallet": wallet,
        "wallet_address": wallet,
        "chain": ct.value,
        "display_name": _chain_display(ct),
        "chain_id": ct.chain_id,
        "total_approvals": len(approvals),
        "approvals": approvals,
        "scanned_at": datetime.utcnow().isoformat(),
    })


async def prepare_revoke(request: web.Request) -> web.Response:
    """
    POST /api/v1/shield/revoke

    Prepare calldata for revoking (setting to 0) an ERC-20 token approval.

    Body:
      {
        "token_address": "0x...",
        "spender_address": "0x...",
        "chain": "ethereum"
      }

    Returns the unsigned transaction object for the client wallet to sign and send.
    NOTE: This endpoint ONLY prepares data — it never executes any transaction.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    token = body.get("token_address", "").strip().lower()
    spender = body.get("spender_address", "").strip().lower()
    chain_str = body.get("chain", "ethereum").strip()

    if not token or not token.startswith("0x") or len(token) != 42:
        return web.json_response({"error": "Invalid token_address"}, status=400)
    if not spender or not spender.startswith("0x") or len(spender) != 42:
        return web.json_response({"error": "Invalid spender_address"}, status=400)

    ct = _parse_chain(chain_str)
    if ct is None:
        return web.json_response({"error": f"Unknown chain: {chain_str}"}, status=400)

    # Encode approve(spender, 0) calldata
    calldata = encode_revoke_calldata(spender)

    # Chain IDs for EVM networks
    chain_ids = {
        ChainType.ETHEREUM:  1,
        ChainType.BSC:       56,
        ChainType.POLYGON:   137,
        ChainType.ARBITRUM:  42161,
        ChainType.BASE:      8453,
        ChainType.OPTIMISM:  10,
        ChainType.AVALANCHE: 43114,
    }

    return web.json_response({
        "action": "revoke_approval",
        "description": f"Revoke approval: {token} -> {spender}",
        "chain": _chain_display(ct),
        "chain_id": chain_ids.get(ct),
        "unsigned_transaction": {
            "to": token,          # Call the token contract
            "data": calldata,     # approve(spender, 0)
            "value": "0x0",
            "chainId": chain_ids.get(ct),
        },
        "warning": (
            "This transaction will set your token approval to 0. "
            "Sign and broadcast using your own wallet. "
            "Ilyon AI never has access to your private keys."
        ),
    })


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


def setup_shield_routes(app: web.Application):
    """Register Shield routes and lifecycle hooks."""
    app.on_startup.append(init_shield)
    app.on_cleanup.append(cleanup_shield)

    app.router.add_get("/api/v1/shield/status", get_shield_status)
    app.router.add_get("/api/v1/shield/{wallet}", scan_wallet_approvals)
    app.router.add_get("/api/v1/shield/{wallet}/{chain}", scan_wallet_chain)
    app.router.add_post("/api/v1/shield/revoke", prepare_revoke)

    logger.info("Shield routes registered")
