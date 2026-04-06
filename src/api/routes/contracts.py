"""
Smart Contract Scanner API routes.

POST /api/v1/contract/scan              — scan a contract
GET  /api/v1/contract/{chain}/{address} — get cached scan results
"""

import logging
from aiohttp import web
from typing import Optional

from src.chains.address import AddressResolver
from src.chains.base import ChainType
from src.api.schemas.requests import ContractScanRequest
from src.api.schemas.responses import ContractScanResponse, VulnerabilityItem, ErrorResponse
from src.api.response_envelope import envelope_error_response, envelope_response

logger = logging.getLogger(__name__)

# In-memory cache for scan results
_scan_cache: dict = {}
_resolver = AddressResolver()


def _normalize_severity(value: str) -> str:
    return (value or "INFO").upper()


def _summarize_contract_risk(scan_result: dict, ai_result: dict) -> tuple[str, int]:
    critical = int(scan_result.get("critical_count", 0))
    high = int(scan_result.get("high_count", 0))
    medium = int(scan_result.get("medium_count", 0))
    low = int(scan_result.get("low_count", 0))
    ai_verdict = _normalize_severity(ai_result.get("risk_verdict", "UNKNOWN"))

    risk_score = min(100, critical * 35 + high * 20 + medium * 10 + low * 4)

    if ai_verdict == "CRITICAL":
        risk_score = max(risk_score, 90)
    elif ai_verdict == "HIGH":
        risk_score = max(risk_score, 75)
    elif ai_verdict == "MEDIUM":
        risk_score = max(risk_score, 55)
    elif ai_verdict in {"LOW", "SAFE"}:
        risk_score = max(risk_score, 20 if ai_verdict == "LOW" else 5)

    if critical > 0 or ai_verdict == "CRITICAL":
        return "CRITICAL", risk_score
    if high > 0 or ai_verdict == "HIGH":
        return "HIGH", risk_score
    if medium > 0 or ai_verdict == "MEDIUM":
        return "MEDIUM", risk_score
    if low > 0 or ai_verdict == "LOW":
        return "LOW", risk_score
    return "SAFE", risk_score


async def scan_contract(request: web.Request) -> web.Response:
    """
    POST /api/v1/contract/scan

    Scan a smart contract for vulnerabilities.
    Request body: { "address": "0x...", "chain": "ethereum" }
    """
    from src.contracts.scanner import ContractScanner
    from src.contracts.ai_auditor import AIContractAuditor

    try:
        data = await request.json()
        try:
            req = ContractScanRequest(**data)
        except Exception as e:
            return web.json_response(
                ErrorResponse(error="Invalid request", code="INVALID_REQUEST",
                              details={"message": str(e)}).model_dump(mode='json'),
                status=400
            )

        # Resolve chain
        chain_type = _resolver.parse_chain_from_string(req.chain)
        if not chain_type:
            return web.json_response(
                ErrorResponse(error=f"Unsupported chain: {req.chain}", code="UNKNOWN_CHAIN").model_dump(mode='json'),
                status=400
            )

        if not chain_type.is_evm:
            return web.json_response(
                ErrorResponse(
                    error="Contract scanner currently supports EVM chains only",
                    code="UNSUPPORTED_CHAIN",
                ).model_dump(mode='json'),
                status=400,
            )

        # Validate address for the selected chain family
        if chain_type.is_evm and not _resolver.is_valid_evm_address(req.address):
            return web.json_response(
                ErrorResponse(
                    error="Invalid EVM contract address",
                    code="INVALID_ADDRESS",
                    details={"expected": "0x-prefixed 20-byte address", "chain": chain_type.value},
                ).model_dump(mode='json'),
                status=400
            )

        if not chain_type.is_evm and not _resolver.is_valid_solana_address(req.address):
            return web.json_response(
                ErrorResponse(
                    error="Invalid contract address for selected chain",
                    code="INVALID_ADDRESS",
                    details={"chain": chain_type.value},
                ).model_dump(mode='json'),
                status=400
            )

        cache_key = f"{chain_type.value}:{req.address}"
        # Check DB cache first, then in-memory
        from src.storage.database import get_database
        db = await get_database()
        cached = await db.get_cached_contract_scan(chain_type.value, req.address)
        if cached is not None:
            return envelope_response(cached)
        if cache_key in _scan_cache:
            return envelope_response(_scan_cache[cache_key])

        # Run scanner
        scanner = ContractScanner()
        auditor = AIContractAuditor()

        try:
            scan_result = await scanner.scan(req.address, chain_type)

            # Run AI audit
            ai_result = await auditor.audit(
                address=req.address,
                chain=chain_type.value,
                contract_name=scan_result.get("name"),
                source_code=scan_result.get("source_code", ""),
                static_findings=scan_result.get("vulnerabilities", []),
                is_proxy=scan_result.get("is_proxy", False),
            )

            overall_risk, risk_score = _summarize_contract_risk(scan_result, ai_result)
            key_findings = ai_result.get("key_findings", []) or []
            recommendations = ai_result.get("recommendations", []) or []

            response = ContractScanResponse(
                address=req.address,
                chain=chain_type.value,
                name=scan_result.get("name"),
                is_verified=scan_result.get("is_verified", False),
                compiler_version=scan_result.get("compiler_version"),
                license=scan_result.get("license"),
                is_proxy=scan_result.get("is_proxy", False),
                proxy_implementation=scan_result.get("proxy_implementation"),
                overall_risk=overall_risk,
                risk_score=risk_score,
                vulnerabilities=[
                    VulnerabilityItem(
                        severity=_normalize_severity(v.get("severity", "info")),
                        title=v.get("title", "Unnamed finding"),
                        description=v.get("description", ""),
                        line_number=v.get("line_number"),
                        code_snippet=v.get("code_snippet"),
                        recommendation=v.get("recommendation", ""),
                    ) for v in scan_result.get("vulnerabilities", [])
                ],
                critical_count=scan_result.get("critical_count", 0),
                high_count=scan_result.get("high_count", 0),
                medium_count=scan_result.get("medium_count", 0),
                low_count=scan_result.get("low_count", 0),
                ai_audit_summary=ai_result.get("audit_summary", ""),
                ai_risk_verdict=ai_result.get("risk_verdict", "UNKNOWN"),
                ai_confidence=ai_result.get("confidence", 0),
                ai_verdict=ai_result.get("risk_verdict"),
                key_findings=key_findings,
                recommendations=recommendations,
                similar_to_scam=scan_result.get("similar_to_scam", False),
                similarity_score=scan_result.get("similarity_score", 0.0),
                similar_contract_info=scan_result.get("similar_contract_info"),
                scan_duration_ms=scan_result.get("scan_duration_ms", 0),
            ).model_dump(mode='json')

            _scan_cache[cache_key] = response
            await db.set_cached_contract_scan(chain_type.value, req.address, response)
            return envelope_response(response)

        finally:
            await scanner.close()

    except Exception as e:
        logger.error(f"Contract scan error: {e}", exc_info=True)
        return web.json_response(
            ErrorResponse(error="Contract scan failed", code="SCAN_FAILED",
                          details={"message": str(e)}).model_dump(mode='json'),
            status=500
        )


async def get_contract_scan(request: web.Request) -> web.Response:
    """
    GET /api/v1/contract/{chain}/{address}

    Get cached contract scan results.
    """
    chain_name = request.match_info.get('chain', '')
    address = request.match_info.get('address', '')

    chain_type = _resolver.parse_chain_from_string(chain_name)
    if not chain_type:
        return envelope_error_response(
            f"Unknown chain: {chain_name}",
            code="UNKNOWN_CHAIN",
            http_status=404,
        )

    cache_key = f"{chain_type.value}:{address}"
    if cache_key in _scan_cache:
        return envelope_response(_scan_cache[cache_key])

    # Check DB
    from src.storage.database import get_database
    db = await get_database()
    cached = await db.get_cached_contract_scan(chain_type.value, address)
    if cached is not None:
        _scan_cache[cache_key] = cached  # warm in-memory cache
        return envelope_response(cached)

    return envelope_error_response(
        "No cached scan. Use POST /api/v1/contract/scan first.",
        code="NOT_FOUND",
        http_status=404,
    )


def setup_contracts_routes(app: web.Application):
    """Register contract scanner routes."""
    app.router.add_post('/api/v1/contract/scan', scan_contract)
    app.router.add_get('/api/v1/contract/{chain}/{address}', get_contract_scan)
    logger.info("Contract scanner routes registered")
