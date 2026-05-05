"""HTTP client adapter that delegates to the Solana yield-builder Node sidecar.

The sidecar lives at services/solana-yield-builder and exposes:
  POST /quote   { protocol, asset, amount, user }      → { expectedAmountOut, fee }
  POST /build   { protocol, asset, amount, user }      → { transactions: [{ b64, summary }] }
  POST /verify  { txHash, expectedPosition }            → { confirmed, detail }

Configured via SOLANA_YIELD_BUILDER_URL env (defaults to
http://solana-yield-builder:8090 inside docker-compose).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

import aiohttp

from src.defi.execution.adapters.base import (
    CapabilityResult,
    VerifyResult,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
)
from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction, make_step


_DEFAULT_URL = os.environ.get("SOLANA_YIELD_BUILDER_URL", "http://solana-yield-builder:8090")
_TIMEOUT_S = float(os.environ.get("SOLANA_YIELD_BUILDER_TIMEOUT", "12"))


@dataclass
class SolanaYieldBuilderAdapter:
    adapter_id: str = "solana-yield-builder"
    chains: frozenset[str] = frozenset({"solana", "sol"})
    protocols: frozenset[str] = frozenset({
        "kamino", "kamino-lend", "kamino-finance", "kamino-vault", "kamino-liquidity",
        "orca", "orca-dex", "orca-whirlpools", "orca-clmm",
        "meteora", "meteora-dlmm", "meteora-vault", "meteora-amm",
        "raydium", "raydium-amm", "raydium-clmm", "raydium-amm-v3", "raydium-cp",
        "marinade", "marinade-finance", "marinade-native",
        "jito", "jito-liquid-staking",
        "sanctum", "sanctum-infinity", "sanctum-liquid-staking",
        "drift", "drift-perps", "drift-spot",
        "lulo", "lulo-finance",
        "save", "save-finance",
        "lifinity", "lifinity-v2",
    })
    actions: frozenset[str] = frozenset({
        "supply", "deposit", "stake", "deposit_lp",
    })
    base_url: str = _DEFAULT_URL

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        if chain.lower() not in self.chains:
            return CapabilityResult(supported=False, reason=f"Solana yield builder does not cover {chain}.")
        if protocol.lower() not in self.protocols:
            return CapabilityResult(
                supported=False,
                reason=(
                    f"Solana yield builder has no SDK module wired for {protocol} yet; "
                    "register it in services/solana-yield-builder/src/adapters."
                ),
            )
        if action.lower() not in self.actions:
            return CapabilityResult(supported=False, reason=f"Solana yield builder does not handle {action}.")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        payload = {
            "protocol": request.protocol,
            "asset": request.asset_in,
            "amount": str(request.amount_in),
            "user": request.user_address,
        }
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=_TIMEOUT_S)) as session:
                async with session.post(f"{self.base_url}/quote", json=payload) as resp:
                    body = await resp.json()
                    return YieldQuote(
                        adapter_id=self.adapter_id,
                        expected_apy=body.get("apy"),
                        expected_amount_out=body.get("expectedAmountOut"),
                        fees=body.get("fees", {}),
                        metadata={"protocol": request.protocol, "router": "solana-sidecar"},
                    )
        except Exception as exc:  # noqa: BLE001 — sidecar can be down during dev
            return YieldQuote(
                adapter_id=self.adapter_id,
                expected_apy=None,
                expected_amount_out=None,
                fees={},
                metadata={"protocol": request.protocol, "router": "solana-sidecar", "warning": str(exc)},
            )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        payload = {
            "protocol": request.protocol,
            "asset": request.asset_in,
            "amount": str(request.amount_in),
            "user": request.user_address,
            "slippageBps": request.slippage_bps,
            "extra": request.extra or {},
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=_TIMEOUT_S)) as session:
            async with session.post(f"{self.base_url}/build", json=payload) as resp:
                if resp.status >= 400:
                    detail = await resp.text()
                    raise ValueError(f"Solana yield builder returned {resp.status}: {detail[:200]}")
                body = await resp.json()
        transactions = body.get("transactions") or []
        if not transactions:
            raise ValueError("Solana yield builder returned no transactions.")
        steps: list[ExecutionStepV3] = []
        depends_on: list[str] = []
        for index, raw in enumerate(transactions, start=1):
            serialized = raw.get("b64") or raw.get("serialized")
            if not serialized:
                raise ValueError(f"Solana yield builder tx {index} missing serialized payload.")
            summary = raw.get("summary") or f"{request.protocol} {request.action if hasattr(request,'action') else 'deposit'} step {index}"
            step = make_step(
                index=index,
                action="deposit_lp" if request.protocol.lower() in {"orca", "orca-dex", "orca-whirlpools", "meteora", "meteora-dlmm", "raydium", "raydium-amm", "raydium-clmm"} else "supply",
                title=summary,
                description=raw.get("description") or summary,
                chain="solana",
                wallet="Phantom",
                protocol=request.protocol,
                asset_in=request.asset_in,
                amount_in=str(request.amount_in),
                asset_out=raw.get("receiptToken"),
                slippage_bps=request.slippage_bps,
                gas_estimate_usd=raw.get("feeUsd", 0.01),
                duration_estimate_s=raw.get("durationS", 25),
                depends_on=list(depends_on),
                transaction=UnsignedStepTransaction(
                    chain_kind="solana",
                    serialized=serialized,
                ),
                risk_warnings=raw.get("warnings") or [
                    "Solana transactions submit immediately after signing; double-check the protocol address.",
                ],
            )
            steps.append(step)
            depends_on = [step.step_id]
        return steps

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        payload = {
            "txHash": request.expected_position.get("tx_hash"),
            "expectedPosition": request.expected_position,
        }
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=_TIMEOUT_S)) as session:
                async with session.post(f"{self.base_url}/verify", json=payload) as resp:
                    body = await resp.json()
                    return VerifyResult(
                        confirmed=bool(body.get("confirmed")),
                        detail=body.get("detail"),
                        receipt=body,
                    )
        except Exception as exc:  # noqa: BLE001
            return VerifyResult(confirmed=False, detail=f"Sidecar verify error: {exc}")
