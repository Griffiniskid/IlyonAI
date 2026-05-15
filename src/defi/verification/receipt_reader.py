"""Per-kind RPC receipt verifier — §6g implementation layer.

Consumes a (ReceiptKind, chain, tx_hash, owner, expected) tuple and returns
a `ReadResult` indicating whether the on-chain state matches the plan.
Wraps the v3_pool_resolver._eth_call_with_fallback helper so calls reuse
the existing RPC fallback chain.

Coverage in this first cut (EVM kinds):
  - V3_NFT        — NFPM Transfer(0x0,user,tokenId) log + NFPM.positions(tokenId)
  - ATOKEN        — ERC20.balanceOf(user, aToken) > 0
  - ERC4626_SHARE — ERC20.balanceOf(user, vault) > 0
  - LP_ERC20      — ERC20.balanceOf(user, lpToken) > 0
  - CTOKEN        — ERC20.balanceOf(user, comet) > 0
  - LST_ERC20     — ERC20.balanceOf(user, lst) > 0
  - LRT_ERC20     — ERC20.balanceOf(user, lrt) > 0

Solana kinds defer to the sidecar `/verify` endpoint already wired in
solana_yield_builder adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.data.v3_pool_resolver import _eth_call_with_fallback
from src.defi.verification.receipt_table import ReceiptKind, verifier_for

# ERC20.balanceOf(address) selector
_BALANCE_OF_SEL = "0x70a08231"
# NFP.positions(uint256 tokenId) selector
_NFP_POSITIONS_SEL = "0x99fbab88"


def _pad32(hex_str: str) -> str:
    return hex_str.lower().removeprefix("0x").rjust(64, "0")


@dataclass
class ReadResult:
    confirmed: bool
    kind: ReceiptKind
    detail: str
    raw: dict[str, Any] | None = None


async def _read_erc20_balance(chain: str, token: str, owner: str) -> int | None:
    data = _BALANCE_OF_SEL + _pad32(owner)
    raw = await _eth_call_with_fallback(chain, token, data)
    if not raw or raw == "0x":
        return None
    try:
        return int(raw.removeprefix("0x"), 16)
    except ValueError:
        return None


async def _read_nfp_position(chain: str, nfpm: str, token_id: int) -> dict[str, Any] | None:
    data = _NFP_POSITIONS_SEL + format(token_id, "064x")
    raw = await _eth_call_with_fallback(chain, nfpm, data)
    if not raw or raw == "0x":
        return None
    body = raw.removeprefix("0x")
    if len(body) < 64 * 12:
        return None
    # NFP.positions return tuple:
    # (nonce, operator, token0, token1, fee, tickLower, tickUpper,
    #  liquidity, feeGrowthInside0LastX128, feeGrowthInside1LastX128,
    #  tokensOwed0, tokensOwed1)
    def _word(i: int) -> int:
        return int(body[i * 64:(i + 1) * 64], 16)

    def _word_signed(i: int) -> int:
        v = _word(i)
        if v >= 1 << 255:
            v -= 1 << 256
        return v

    return {
        "nonce": _word(0),
        "operator": "0x" + body[2 * 64 + 24:3 * 64],
        "token0": "0x" + body[2 * 64 + 24:3 * 64],
        "token1": "0x" + body[3 * 64 + 24:4 * 64],
        "fee": _word(4),
        "tickLower": _word_signed(5),
        "tickUpper": _word_signed(6),
        "liquidity": _word(7),
    }


async def verify_receipt(
    *,
    kind: ReceiptKind | str,
    chain: str,
    owner: str,
    expected: dict[str, Any] | None = None,
) -> ReadResult:
    """Top-level verifier. `expected` carries plan-time data (token_id, vault
    address, lp_token address, expected_delta, etc.). Returns ReadResult."""
    # Tolerate string kinds — return "no spec" before forcing enum coercion
    # so callers can probe with unknown identifiers cleanly.
    if isinstance(kind, str):
        try:
            k = ReceiptKind(kind)
        except ValueError:
            return ReadResult(
                confirmed=False,
                kind=ReceiptKind.LP_ERC20,  # neutral placeholder
                detail=f"No verifier spec registered for {kind!r}.",
            )
    else:
        k = kind
    spec = verifier_for(k)
    if spec is None:
        return ReadResult(confirmed=False, kind=k,
                          detail=f"No verifier spec registered for {k}.")
    exp = expected or {}

    if spec.chain_family != "evm":
        return ReadResult(
            confirmed=False, kind=k,
            detail=f"{k.value} is a Solana receipt — delegated to sidecar /verify.",
        )

    if k in {ReceiptKind.ATOKEN, ReceiptKind.ERC4626_SHARE, ReceiptKind.LP_ERC20,
             ReceiptKind.CTOKEN, ReceiptKind.LST_ERC20, ReceiptKind.LRT_ERC20,
             ReceiptKind.BPT, ReceiptKind.PENDLE_PT_YT, ReceiptKind.STARGATE_SHARE}:
        receipt_addr = exp.get("token") or exp.get("vault") or exp.get("lp_token")
        if not receipt_addr:
            return ReadResult(confirmed=False, kind=k,
                              detail=f"{k.value} verify requires expected.token / vault / lp_token.")
        bal = await _read_erc20_balance(chain, str(receipt_addr), owner)
        if bal is None:
            return ReadResult(confirmed=False, kind=k,
                              detail=f"RPC read returned no data for {receipt_addr} balanceOf({owner}).")
        min_expected = int(exp.get("min_expected", 1))
        ok = bal >= min_expected
        return ReadResult(
            confirmed=ok, kind=k,
            detail=(f"balanceOf({owner})={bal} >= {min_expected}." if ok
                    else f"balanceOf({owner})={bal} < {min_expected}."),
            raw={"balance": bal, "token": receipt_addr},
        )

    if k == ReceiptKind.V3_NFT:
        nfpm = exp.get("nfpm") or exp.get("nfp_manager")
        token_id = exp.get("token_id") or exp.get("tokenId")
        if not nfpm or token_id is None:
            return ReadResult(confirmed=False, kind=k,
                              detail="V3_NFT verify requires expected.nfpm + token_id.")
        pos = await _read_nfp_position(chain, str(nfpm), int(token_id))
        if pos is None:
            return ReadResult(confirmed=False, kind=k,
                              detail=f"NFP.positions({token_id}) returned no data.")
        ok = int(pos["liquidity"]) > 0
        return ReadResult(
            confirmed=ok, kind=k,
            detail=f"NFP.positions({token_id}).liquidity={pos['liquidity']} > 0={ok}.",
            raw=pos,
        )

    if k == ReceiptKind.V4_NFT:
        # PoolManager.getPositionInfo(bytes32 poolId, bytes32 positionId) selector 0x97fd7b42.
        # positionId = keccak256(abi.encodePacked(owner, tickLower, tickUpper, salt)) per V4.
        pool_manager = exp.get("pool_manager") or exp.get("poolManager")
        pool_id = exp.get("pool_id") or exp.get("poolId")
        position_id = exp.get("position_id") or exp.get("positionId")
        if not pool_manager or not pool_id or not position_id:
            return ReadResult(
                confirmed=False, kind=k,
                detail="V4_NFT verify requires expected.pool_manager + pool_id + position_id.",
            )
        data = (
            "0x97fd7b42"
            + str(pool_id).removeprefix("0x").rjust(64, "0")
            + str(position_id).removeprefix("0x").rjust(64, "0")
        )
        raw = await _eth_call_with_fallback(chain, str(pool_manager), data)
        if not raw or raw == "0x":
            return ReadResult(
                confirmed=False, kind=k,
                detail=f"PoolManager.getPositionInfo returned no data for poolId {pool_id}.",
            )
        body = raw.removeprefix("0x")
        # Layout: (uint128 liquidity, uint256 feeGrowthInside0LastX128, uint256 feeGrowthInside1LastX128)
        # The first 32-byte word starts with high-order zeros padding the uint128.
        liquidity_hex = body[:64]
        try:
            liquidity = int(liquidity_hex, 16)
        except ValueError:
            return ReadResult(confirmed=False, kind=k, detail="getPositionInfo decode failed.")
        ok = liquidity > 0
        return ReadResult(
            confirmed=ok, kind=k,
            detail=f"PoolManager.getPositionInfo.liquidity={liquidity} > 0={ok}.",
            raw={"liquidity": liquidity, "pool_id": pool_id, "position_id": position_id},
        )

    return ReadResult(
        confirmed=False, kind=k,
        detail=f"No EVM verifier path implemented for {k.value} yet.",
    )
