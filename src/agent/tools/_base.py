from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from src.api.schemas.agent import ToolEnvelope, ToolError


@dataclass
class ToolCtx:
    services: Any
    user_id: int
    wallet: str | None
    session_id: str | None = None
    solana_wallet: str | None = None
    evm_wallet: str | None = None


def ok_envelope(*, data, card_type=None, card_payload=None):
    return ToolEnvelope(
        ok=True,
        data=data,
        card_type=card_type,
        card_id=str(uuid4()),
        card_payload=card_payload,
    )


# Sibling normalizer to src.defi.execution.models._BLOCKER_CODE_ALIASES.
# Matrix Pass A wave 2 BUG-F-05 found that err_envelope code strings
# from swap_simulate / build_swap_tx never reach ExecutionPlanV3.add_blocker
# (no card is ever constructed for an err_envelope path), so the
# plan-side normalizer doesn't fire. Mirror the canonical mapping here so
# the tool-result observation handler sees UPPER_SNAKE codes that match
# KNOWN_BLOCKER_CODES + the recovery dispatcher.
_ERR_ENVELOPE_CODE_ALIASES: dict[str, str] = {
    "quote_unavailable": "NULL_ROUTE",
    "pool_not_found": "UNSUPPORTED_ADAPTER",
    "unsupported_chain": "WALLET_CHAIN_MISMATCH",
    "missing_allowance": "APPROVAL_MISSING",
    "insufficient_balance": "INSUFFICIENT_BALANCE",
    "gas_top_up": "GAS_TOPUP_REQUIRED",
    "gas_topup": "GAS_TOPUP_REQUIRED",
    "adapter_build_failed": "ADAPTER_BUILD_FAILED",
    "adapter_quote_required": "ADAPTER_QUOTE_REQUIRED",
    "stale_price": "STALE_PRICE_FEED",
    "pool_not_initialized": "POOL_NOT_INITIALIZED",
    "wallet_chain_mismatch": "WALLET_CHAIN_MISMATCH",
    "zero_quote": "NULL_ROUTE",
    "composed_plan_bridge_quote_failed": "ADAPTER_QUOTE_REQUIRED",
    "composed_plan_bridge_build_failed": "ADAPTER_BUILD_FAILED",
}


def _normalize_err_code(code: str | None) -> str | None:
    """Normalize lowercase err_envelope codes to canonical UPPER_SNAKE."""
    if not code:
        return code
    raw = code.strip()
    if raw in _ERR_ENVELOPE_CODE_ALIASES.values():
        return raw  # already canonical
    canonical = _ERR_ENVELOPE_CODE_ALIASES.get(raw) or _ERR_ENVELOPE_CODE_ALIASES.get(raw.lower())
    return canonical or raw


def err_envelope(code, message, *, card_type=None):
    canonical_code = _normalize_err_code(code)
    return ToolEnvelope(
        ok=False,
        data=None,
        card_type=card_type,
        card_id=str(uuid4()),
        card_payload=None,
        error=ToolError(code=canonical_code, message=message),
    )
