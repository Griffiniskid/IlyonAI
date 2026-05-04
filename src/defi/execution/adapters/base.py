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


@dataclass
class VerifyResult:
    confirmed: bool
    detail: str | None = None
    receipt: dict[str, Any] | None = None


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
