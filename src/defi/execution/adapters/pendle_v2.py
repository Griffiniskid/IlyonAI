"""Pendle V2 three-mode adapter scaffolding — spec §8 Pendle deep.

Pendle V2 has three deposit modes per spec:
  1. mintPyFromToken   — mint PT + YT from any token
  2. swapTokenForPt    — buy PT directly (gives only price exposure)
  3. addLiquidityFromToken — add LP (earns swap fees + voting)

Calldata is fetched from Pendle's Hosted SDK (`/v2/sdk/{chainId}/convert`)
which returns ready-to-sign `tx.to/data/value` plus aggregator-routed
TokenInput. We cache by (chain, market, action, token_in, bucket(amount),
slippage_bps) for 5 minutes and fall back to the NEEDS_FRONTEND_SDK
blocker only when the hosted call fails (timeout, 4xx, 5xx).
"""
from __future__ import annotations

import asyncio
import math
import os
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from src.defi.execution.adapters.base import (
    CapabilityResult,
    VerifyResult,
    parse_receipt_logs,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
)
from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction


# Pendle V2 Router (latest stable per docs) per chain.
_PENDLE_ROUTER: dict[str, str] = {
    "ethereum": "0x888888888889758F76e7103c6CbF23ABbF58F946",
    "arbitrum": "0x888888888889758F76e7103c6CbF23ABbF58F946",
    "optimism": "0x888888888889758F76e7103c6CbF23ABbF58F946",
    "bsc":      "0x888888888889758F76e7103c6CbF23ABbF58F946",
    "base":     "0x888888888889758F76e7103c6CbF23ABbF58F946",
    "mantle":   "0x888888888889758F76e7103c6CbF23ABbF58F946",
}

# Selectors per PendleRouterV4 dispatcher.
# Pendle's router uses overloaded calls — the canonical IDs:
SEL_MINT_PY_FROM_TOKEN = "0xc81f847a"
SEL_SWAP_TOKEN_FOR_PT = "0x594a88cc"
SEL_ADD_LIQUIDITY_FROM_TOKEN = "0x9f9da99e"
# V7-057 — burn PT+YT → underlying token and PT → token swap. Pinned 4-byte
# IDs from PendleRouterV4 source (`redeemPyToToken(address,address,uint256,TokenOutput)`
# and `swapExactPtForToken(address,address,uint256,TokenOutput,LimitOrderData)`).
SEL_REDEEM_PY_TO_TOKEN = "0x47f1de22"
SEL_SWAP_EXACT_PT_FOR_TOKEN = "0x594a88cc"


# ---------------------------------------------------------------------------
# Pendle Hosted SDK — /v2/sdk/{chainId}/convert
# ---------------------------------------------------------------------------

_PENDLE_API_BASE = "https://api-v2.pendle.finance/core/v2/sdk"
_QUOTE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_S = 300
_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10.0)


def _amount_bucket(amount_wei: int) -> int:
    """Bucket the amount to the top 3 sig-figs so near-equal sizes share cache."""
    if amount_wei <= 0:
        return 0
    mag = 10 ** max(0, int(math.log10(amount_wei)) - 2)
    return (amount_wei // mag) * mag


def _cache_key(
    chain_id: int,
    market: str,
    action: str,
    token_in: str,
    amount_wei: int,
    slippage_bps: int,
) -> str:
    return (
        f"{chain_id}:{market.lower()}:{action}:{token_in.lower()}:"
        f"{_amount_bucket(amount_wei)}:{slippage_bps}"
    )


def _tokens_out_for(action: str, extra: dict) -> str | None:
    """Compute the `tokensOut` query-string value per Pendle SDK convert spec."""
    pt = extra.get("pt_address")
    yt = extra.get("yt_address")
    market = extra.get("market") or extra.get("market_address")
    if action in {"mint_py", "mint_py_from_token", "mintPy", "mintPyFromToken"} and pt and yt:
        return f"{pt},{yt}"
    if action in {
        "swap_for_pt", "swap_token_for_pt", "swap_exact_token_for_pt", "swapTokenForPt",
    } and pt:
        return pt
    if action in {"add_liquidity", "addLiquidityFromToken"} and market:
        return market
    # V7-057 — redeem and swap-out paths.
    underlying = extra.get("token_out_address") or extra.get("underlying_address")
    if action in {"redeem_py_to_token", "redeemPyToToken"} and underlying:
        return str(underlying)
    if action in {"swap_exact_pt_for_token", "swapExactPtForToken"} and underlying:
        return str(underlying)
    return None


async def _fetch_pendle_convert(
    chain_id: int,
    *,
    tokens_in: str,
    amounts_in: str,
    tokens_out: str,
    receiver: str,
    slippage: float,
    api_key: str | None = None,
) -> dict[str, Any] | None:
    """GET /v2/sdk/{chainId}/convert. Returns parsed JSON or None on 5xx/4xx/timeout."""
    params = {
        "tokensIn": tokens_in,
        "amountsIn": amounts_in,
        "tokensOut": tokens_out,
        "receiver": receiver,
        "slippage": f"{slippage:.6f}",
        "enableAggregator": "true",
        "aggregators": "kyberswap",
    }
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = f"{_PENDLE_API_BASE}/{chain_id}/convert"
    try:
        async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as sess:
            async with sess.get(url, params=params, headers=headers) as r:
                if r.status >= 400:
                    return None
                return await r.json()
    except (asyncio.TimeoutError, aiohttp.ClientError):
        return None


def _extract_route0_tx(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Pluck routes[0].tx from a Pendle convert payload — None if not present."""
    if not payload:
        return None
    routes = payload.get("routes") or []
    if not routes:
        return None
    tx = (routes[0] or {}).get("tx")
    if not isinstance(tx, dict) or not tx.get("to") or not tx.get("data"):
        return None
    return tx


@dataclass
class PendleV2Adapter:
    adapter_id: str = "pendle-v2"
    # V7-043 — canonical Pendle SY Deposit(address,address,address,uint256,uint256)
    # topic0 (ERC4626 Deposit signature; Pendle SY wraps ERC4626 semantics).
    EXPECTED_TOPIC0: str = "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7"
    chains: frozenset[str] = frozenset(_PENDLE_ROUTER.keys())
    protocols: frozenset[str] = frozenset({"pendle", "pendle-v2"})
    actions: frozenset[str] = frozenset({
        "mint_py", "mint_py_from_token",
        "redeem_py", "redeem_py_to_token",
        "swap_for_pt", "swap_token_for_pt", "swap_exact_token_for_pt",
        "swap_pt_for_token", "swap_exact_pt_for_token",
        "add_liquidity", "deposit_lp", "provide_liquidity",
    })

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        if chain not in self.chains:
            return CapabilityResult(False, None, f"Pendle V2 not on {chain}.")
        if protocol not in self.protocols:
            return CapabilityResult(False, None, f"Adapter is for Pendle, not {protocol}.")
        if action not in self.actions:
            return CapabilityResult(False, None, f"Pendle adapter does not handle {action}.")
        return CapabilityResult(True, self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=None,
            fees={"protocol": "Pendle pool fee varies by market"},
            metadata={"protocol": "pendle-v2", "chain": request.chain},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        """Per-mode dispatch — each Pendle mode emits its own typed step.

        Pendle V4 router calldata uses nested structs (ApproxParams,
        TokenInput, LimitOrderData) whose `guessOffchain` differs by market.
        We prefer Pendle's Hosted SDK `/v2/sdk/{chainId}/convert` which
        returns signable `tx.to/data/value` already aggregator-routed.
        Falls back to the NEEDS_FRONTEND_SDK blocker on hosted-SDK failure.
        """
        from src.defi.execution.models import make_step

        chain_id_map = {
            "ethereum": 1, "arbitrum": 42161, "optimism": 10,
            "bsc": 56, "base": 8453, "mantle": 5000,
        }
        chain_id = chain_id_map.get(request.chain, 1)
        router = _PENDLE_ROUTER.get(request.chain)
        if router is None:
            raise ValueError(f"Pendle V2 router not registered on {request.chain}.")

        extra = request.extra or {}
        # Epoch-boundary blocker — Pendle markets expire; the caller should
        # surface PENDING_EPOCH_ENTRY when the chosen market is past expiry.
        market_expiry_ts = extra.get("market_expiry_ts")
        if market_expiry_ts is not None:
            try:
                expiry = int(market_expiry_ts)
            except (TypeError, ValueError):
                expiry = 0
            if expiry > 0 and expiry < int(time.time()):
                return [
                    make_step(
                        index=1, action="deposit_lp",
                        title=f"Pendle market expired at ts={expiry}",
                        description=(
                            "The selected Pendle V2 market has passed its expiry "
                            "timestamp. Choose an active market or wait for the "
                            "next epoch to roll over."
                        ),
                        chain=request.chain, wallet="MetaMask", protocol="pendle-v2",
                        asset_in=request.asset_in, amount_in=str(request.amount_in),
                        slippage_bps=request.slippage_bps,
                        blocker_codes=["PENDING_EPOCH_ENTRY"],
                    ),
                ]

        action = (extra.get("action") or "add_liquidity").lower()
        market = extra.get("market") or extra.get("market_address")
        if not market:
            raise ValueError(
                "Pendle V2 build needs extra.market (the PT/YT/LP market address)."
            )

        # V7-057 — five-mode dispatch. Each mode pins router selector + emits
        # its own step_action; unknown modes raise ValueError rather than
        # silently defaulting (which could mis-route user funds).
        if action in {"mint_py", "mint_py_from_token"}:
            selector_pin = SEL_MINT_PY_FROM_TOKEN
            mode_label = "mintPyFromToken"
            step_action = "mint_py"
        elif action in {"redeem_py", "redeem_py_to_token"}:
            selector_pin = SEL_REDEEM_PY_TO_TOKEN
            mode_label = "redeemPyToToken"
            step_action = "redeem_py"
        elif action in {"swap_for_pt", "swap_token_for_pt", "swap_exact_token_for_pt"}:
            selector_pin = SEL_SWAP_TOKEN_FOR_PT
            mode_label = "swapExactTokenForPt"
            step_action = "swap_for_pt"
        elif action in {"swap_pt_for_token", "swap_exact_pt_for_token"}:
            selector_pin = SEL_SWAP_EXACT_PT_FOR_TOKEN
            mode_label = "swapExactPtForToken"
            step_action = "swap_pt_for_token"
        elif action in {"add_liquidity", "deposit_lp", "provide_liquidity", "addLiquidityFromToken"}:
            selector_pin = SEL_ADD_LIQUIDITY_FROM_TOKEN
            mode_label = "addLiquidityFromToken"
            step_action = "add_liquidity"
        else:
            raise ValueError(
                f"Pendle V2 build: unknown action {action!r}. Expected one of "
                "mint_py_from_token, redeem_py_to_token, swap_exact_token_for_pt, "
                "swap_exact_pt_for_token, add_liquidity."
            )

        # -------------------------------------------------------------------
        # Pendle Hosted SDK pre-flight — populate to/data/value when possible.
        # -------------------------------------------------------------------
        token_in_address = (
            extra.get("token_in_address")
            or extra.get("tokenInAddress")
            or extra.get("asset_in_address")
        )
        amount_in_wei = (
            extra.get("amount_in_wei")
            or extra.get("amountInWei")
            or extra.get("amount_wei")
        )
        receiver = (
            extra.get("receiver")
            or getattr(request, "user_address", None)
        )
        api_key = extra.get("pendle_api_key") or os.environ.get("PENDLE_API_KEY")

        sdk_tx: dict[str, Any] | None = None
        sdk_payload: dict[str, Any] | None = None

        tokens_out = _tokens_out_for(action, {**extra, "market": market})
        if token_in_address and amount_in_wei and receiver and tokens_out:
            try:
                amount_wei_int = int(amount_in_wei)
            except (TypeError, ValueError):
                amount_wei_int = 0
            if amount_wei_int > 0:
                slippage_bps = int(request.slippage_bps or 0)
                slippage_frac = max(0.0, min(1.0, slippage_bps / 10_000.0))
                ckey = _cache_key(
                    chain_id, market, step_action,
                    str(token_in_address), amount_wei_int, slippage_bps,
                )
                now = time.time()
                cached = _QUOTE_CACHE.get(ckey)
                if cached and (now - cached[0]) < _CACHE_TTL_S:
                    sdk_payload = cached[1]
                else:
                    sdk_payload = await _fetch_pendle_convert(
                        chain_id,
                        tokens_in=str(token_in_address),
                        amounts_in=str(amount_wei_int),
                        tokens_out=tokens_out,
                        receiver=str(receiver),
                        slippage=slippage_frac,
                        api_key=api_key,
                    )
                    if sdk_payload is not None:
                        _QUOTE_CACHE[ckey] = (now, sdk_payload)
                sdk_tx = _extract_route0_tx(sdk_payload)

        if sdk_tx is not None:
            tx_to = sdk_tx.get("to")
            tx_data = sdk_tx.get("data")
            tx_value = str(sdk_tx.get("value", "0"))
            outputs = []
            try:
                outputs = (sdk_payload.get("routes") or [{}])[0].get("outputs") or []
            except (AttributeError, IndexError, TypeError):
                outputs = []
            unsigned = UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=tx_to,
                data=tx_data,
                value=tx_value,
            )
            snapshot = {
                "pendle_sdk_outputs": outputs,
                "pendle_selector": selector_pin,
                "pendle_mode": mode_label,
                "pendle_router": router,
                "source": "pendle_hosted_sdk",
            }
            return [
                make_step(
                    index=1,
                    action=step_action,
                    title=f"Pendle V2 {mode_label} on market {market[:10]}…",
                    description=(
                        f"Pendle Hosted SDK `/convert` returned signable calldata "
                        f"for {mode_label} (selector {selector_pin}) on market "
                        f"{market}. Aggregator: kyberswap. "
                        f"Input: {request.amount_in} {request.asset_in}."
                    ),
                    chain=request.chain, wallet="MetaMask", protocol="pendle-v2",
                    asset_in=request.asset_in, amount_in=str(request.amount_in),
                    slippage_bps=request.slippage_bps,
                    transaction=unsigned,
                    snapshot=snapshot,
                ),
            ]

        return [
            make_step(
                index=1,
                action=step_action,
                title=f"Pendle V2 {mode_label} on market {market[:10]}…",
                description=(
                    f"Pendle V2 Router {router} call to {mode_label} (selector "
                    f"{selector_pin}). Frontend Pendle SDK fills ApproxParams "
                    f"+ TokenInput from the live market state before signing. "
                    f"Market: {market}. Input: {request.amount_in} {request.asset_in}."
                ),
                chain=request.chain, wallet="MetaMask", protocol="pendle-v2",
                asset_in=request.asset_in, amount_in=str(request.amount_in),
                slippage_bps=request.slippage_bps,
                blocker_codes=["NEEDS_FRONTEND_SDK"],
            ),
        ]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        """Parse receipt logs for Pendle SY (ERC4626) Deposit topic0.

        Pendle V2 wraps yield-bearing assets via SY tokens with ERC4626
        semantics, so the canonical Deposit topic0 matches. SY/PT/YT split
        accounting is delegated to the position-tracker.
        """
        receipt = request.receipt or (request.expected_position or {}).get("receipt")
        return parse_receipt_logs(receipt, self.EXPECTED_TOPIC0)
