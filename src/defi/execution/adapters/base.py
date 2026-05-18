"""YieldAdapter protocol and helper types."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from src.defi.execution.models import ExecutionStepV3


@dataclass
class CapabilityResult:
    supported: bool
    adapter_id: str | None = None
    reason: str | None = None


@dataclass
class YieldQuoteRequest:
    chain: str
    protocol: str
    asset_in: str
    amount_in: Decimal
    asset_out: str | None = None
    user_address: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class YieldQuote:
    adapter_id: str
    expected_apy: float | None
    expected_amount_out: str | None
    fees: dict[str, Any]
    metadata: dict[str, Any]


@dataclass
class YieldBuildRequest:
    chain: str
    protocol: str
    asset_in: str
    amount_in: Decimal
    user_address: str
    asset_out: str | None = None
    slippage_bps: int = 50
    extra: dict[str, Any] | None = None


@dataclass
class YieldVerifyRequest:
    chain: str
    user_address: str
    expected_position: dict[str, Any]
    receipt: dict[str, Any] | None = None


@dataclass
class VerifyResult:
    confirmed: bool
    detail: str | None = None
    receipt: dict[str, Any] | None = None
    event_signature: str | None = None
    log_match: int = 0
    raw_log: dict[str, Any] | None = None


def parse_receipt_logs(receipt: dict[str, Any] | None, expected_topic0: str) -> VerifyResult:
    """Shared helper: scan EVM receipt logs for canonical topic0 match.

    Returns a VerifyResult populated with confirmed/event_signature/log_match/raw_log.
    Adapters delegate here to keep behavior consistent across protocols.
    """
    if not receipt or not isinstance(receipt, dict):
        return VerifyResult(
            confirmed=False,
            detail="No receipt provided to verify().",
            event_signature=None,
            log_match=0,
            raw_log=None,
        )
    logs = receipt.get("logs", []) or []
    normalized = expected_topic0.lower() if isinstance(expected_topic0, str) else expected_topic0
    matching: list[dict[str, Any]] = []
    for log in logs:
        if not isinstance(log, dict):
            continue
        topics = log.get("topics") or []
        if not topics:
            continue
        topic0 = topics[0]
        if isinstance(topic0, str) and topic0.lower() == normalized:
            matching.append(log)
    confirmed = len(matching) > 0
    return VerifyResult(
        confirmed=confirmed,
        detail=(
            f"matched {len(matching)} log(s) for topic0={expected_topic0}"
            if confirmed
            else f"no logs matched expected topic0={expected_topic0}"
        ),
        receipt=receipt,
        event_signature=expected_topic0 if confirmed else None,
        log_match=len(matching),
        raw_log=matching[0] if matching else None,
    )


@runtime_checkable
class YieldAdapter(Protocol):
    adapter_id: str
    chains: set[str]
    protocols: set[str]
    actions: set[str]

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult: ...

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote: ...

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]: ...

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult: ...
