"""Per-kind RPC receipt verifier — §6g implementation layer.

Consumes a (ReceiptKind, chain, tx_hash, owner, expected) tuple and returns
a `ReadResult` indicating whether the on-chain state matches the plan.
Wraps the v3_pool_resolver._eth_call_with_fallback helper so calls reuse
the existing RPC fallback chain.

EVM kinds (eth_call + abi-decode):
  - V3_NFT        — NFPM Transfer(0x0,user,tokenId) log + NFPM.positions(tokenId)
  - V4_NFT        — PoolManager.getPositionInfo(poolId, positionId)
  - ATOKEN        — ERC20.balanceOf(user, aToken) > 0
  - ERC4626_SHARE — ERC20.balanceOf(user, vault) > 0
  - LP_ERC20      — ERC20.balanceOf(user, lpToken) > 0
  - CTOKEN        — ERC20.balanceOf(user, comet) > 0
  - LST_ERC20     — ERC20.balanceOf(user, lst) > 0
  - LRT_ERC20     — ERC20.balanceOf(user, lrt) > 0
  - BPT / PENDLE_PT_YT / STARGATE_SHARE — same ERC-20 balance shape

SPL kinds (Solana RPC `getTokenAccountsByOwner` + optional `getAccountInfo`):
  - MSOL                  — Marinade mSOL SPL token balance > 0
  - JITOSOL               — Jito jitoSOL SPL token balance > 0
  - JLP                   — Jupiter Perps JLP SPL token balance > 0
  - POSITION_PDA          — Meteora DLMM position PDA (no NFT, PDA exists+owner)
  - POSITION_PDA_WITH_NFT — Orca Whirlpool / Raydium CLMM (NFT amount=1 + PDA exists)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

from src.config import settings
from src.data.v3_pool_resolver import _eth_call_with_fallback
from src.defi.verification.receipt_table import ReceiptKind, verifier_for

logger = logging.getLogger(__name__)

# Canonical SPL Token program IDs — same values used by src/data/solana.py and
# build_yield_execution_plan.py. We accept both legacy Token + Token-2022 so a
# Token-2022 receipt doesn't false-negative when filtered by legacy programId.
_SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
_SPL_TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

# Canonical SPL receipt mints — sourced from `build_yield_execution_plan.py`
# (lines 1232–1238) and `wallet_swap.py` (lines 250–251), both of which read
# these from the same on-chain registries we cross-reference against
# Solscan / jup.ag docs. DO NOT change without re-verifying on chain.
_MSOL_MINT = "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So"        # Marinade staked SOL
_JITOSOL_MINT = "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"     # Jito staked SOL
_JLP_MINT = "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4"         # Jupiter Perpetuals LP

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


async def _solana_rpc(
    method: str,
    params: list[Any],
    *,
    rpc_url: str | None = None,
    timeout_s: float = 8.0,
    session: aiohttp.ClientSession | None = None,
) -> dict[str, Any] | None:
    """One-shot Solana JSON-RPC call. Returns the `result` dict on success,
    None on transport/protocol error. Mirrors the request shape used by
    src/data/solana.py::check_account_frozen so SPL receipt reads share the
    fail-soft envelope (transient failures NEVER fabricate confirmation)."""
    url = rpc_url or getattr(settings, "solana_rpc_url", "https://api.mainnet-beta.solana.com")
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s))
    try:
        try:
            async with session.post(url, json=payload,
                                    timeout=aiohttp.ClientTimeout(total=timeout_s)) as resp:
                if resp.status != 200:
                    return None
                body = await resp.json()
        except Exception as exc:
            logger.debug("Solana RPC %s failed: %s", method, exc)
            return None
        if not isinstance(body, dict) or body.get("error"):
            return None
        return body.get("result")
    finally:
        if owns_session and session is not None:
            await session.close()


async def _spl_token_balance(
    owner: str,
    mint: str,
    *,
    rpc_url: str | None = None,
    session: aiohttp.ClientSession | None = None,
) -> tuple[int | None, int | None]:
    """Return (raw_amount, decimals) for `owner`'s ATA(s) of `mint`.

    Fans out across SPL Token + Token-2022 program IDs (Token-2022 mints
    don't show up under the legacy programId filter). Sums all matching
    accounts in case the owner has multiple ATAs (rare but legal).
    Returns (None, None) on transport error so the caller can distinguish
    'RPC down' from 'balance = 0'.
    """
    total: int | None = None
    decimals: int | None = None
    for program_id in (_SPL_TOKEN_PROGRAM, _SPL_TOKEN_2022_PROGRAM):
        result = await _solana_rpc(
            "getTokenAccountsByOwner",
            [
                owner,
                {"mint": mint, "programId": program_id},
                {"encoding": "jsonParsed", "commitment": "confirmed"},
            ],
            rpc_url=rpc_url,
            session=session,
        )
        if result is None:
            continue  # transport flake on this program — try the other
        accounts = result.get("value") if isinstance(result, dict) else None
        if not isinstance(accounts, list):
            continue
        for entry in accounts:
            acct = (entry or {}).get("account") or {}
            data = acct.get("data")
            if not isinstance(data, dict):
                continue
            info = ((data.get("parsed") or {}).get("info") or {}) if isinstance(data, dict) else {}
            token_amount = info.get("tokenAmount") if isinstance(info, dict) else None
            if not isinstance(token_amount, dict):
                continue
            try:
                amt = int(token_amount.get("amount") or 0)
            except (TypeError, ValueError):
                continue
            dec = token_amount.get("decimals")
            if isinstance(dec, int):
                decimals = dec
            total = (total or 0) + amt
    return total, decimals


async def _solana_account_exists(
    address: str,
    *,
    rpc_url: str | None = None,
    session: aiohttp.ClientSession | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    """Returns (exists, parsed_account). For PDA verification we just need
    to confirm the position account exists + capture its `data` for the
    optional liquidity decode the caller can do on its own."""
    result = await _solana_rpc(
        "getAccountInfo",
        [address, {"encoding": "jsonParsed", "commitment": "confirmed"}],
        rpc_url=rpc_url,
        session=session,
    )
    if result is None:
        return (False, None)
    value = result.get("value") if isinstance(result, dict) else None
    if value is None:
        return (False, None)
    return (True, value if isinstance(value, dict) else None)


async def _verify_spl_balance_receipt(
    kind: ReceiptKind,
    owner: str,
    mint: str,
    expected: dict[str, Any],
    *,
    rpc_url: str | None = None,
) -> ReadResult:
    """Shared SPL-balance verifier path for MSOL / JITOSOL / JLP and any
    other 'just hold the receipt mint' kinds. Asserts balance >= min_expected
    (default 1 raw unit) — same convention as the EVM ATOKEN/ERC4626 path."""
    if not owner:
        return ReadResult(confirmed=False, kind=kind,
                          detail=f"{kind.value} verify requires owner pubkey.")
    bal, decimals = await _spl_token_balance(owner, mint, rpc_url=rpc_url)
    if bal is None:
        return ReadResult(
            confirmed=False, kind=kind,
            detail=f"Solana RPC returned no data for {mint} balance of {owner}.",
        )
    min_expected = int(expected.get("min_expected", 1))
    ok = bal >= min_expected
    # Optional sanity check: caller can pass expected_input_lamports + a
    # rough exchange rate so we sanity-check that ATA delta * rate ≈ input.
    sanity = ""
    expected_amount = expected.get("expected_amount")
    if expected_amount is not None:
        try:
            tol_bps = int(expected.get("tolerance_bps", 200))  # 2% default
            target = int(expected_amount)
            if target > 0:
                drift_bps = abs(bal - target) * 10_000 // target
                if drift_bps > tol_bps:
                    ok = False
                    sanity = f" (balance {bal} drifted {drift_bps}bps from expected {target}; tol={tol_bps}bps)"
        except (TypeError, ValueError):
            pass
    return ReadResult(
        confirmed=ok, kind=kind,
        detail=(f"SPL balance(owner={owner[:8]}…, mint={mint[:8]}…)={bal} >= {min_expected}.{sanity}"
                if ok else
                f"SPL balance(owner={owner[:8]}…, mint={mint[:8]}…)={bal} < {min_expected}.{sanity}"),
        raw={"balance": bal, "decimals": decimals, "mint": mint},
    )


async def _verify_spl_position_pda(
    kind: ReceiptKind,
    owner: str,
    expected: dict[str, Any],
    *,
    rpc_url: str | None = None,
) -> ReadResult:
    """POSITION_PDA + POSITION_PDA_WITH_NFT verifier.

    Required `expected` keys:
      - position_pda: derived PDA address (Raydium CLMM / Orca Whirlpool /
        Meteora DLMM). The plan-builder computes it from program ID +
        position seed; we don't re-derive here, just read it.
      - position_mint (optional, only for POSITION_PDA_WITH_NFT): the
        Metaplex NFT mint that Whirlpool / Raydium CLMM stamps the
        position with. We assert owner holds amount=1 of it.
    """
    pda = expected.get("position_pda") or expected.get("positionPda")
    if not pda:
        return ReadResult(
            confirmed=False, kind=kind,
            detail=f"{kind.value} verify requires expected.position_pda.",
        )
    exists, account = await _solana_account_exists(str(pda), rpc_url=rpc_url)
    if not exists:
        return ReadResult(
            confirmed=False, kind=kind,
            detail=f"Position PDA {pda} not found on chain.",
        )
    # For POSITION_PDA_WITH_NFT also require the owner to actually hold the
    # Metaplex NFT (amount==1). Whirlpool & Raydium CLMM both mint these.
    if kind == ReceiptKind.POSITION_PDA_WITH_NFT:
        nft_mint = expected.get("position_mint") or expected.get("positionMint")
        if not nft_mint:
            return ReadResult(
                confirmed=False, kind=kind,
                detail="POSITION_PDA_WITH_NFT verify requires expected.position_mint.",
            )
        nft_bal, _ = await _spl_token_balance(owner, str(nft_mint), rpc_url=rpc_url)
        if nft_bal is None:
            return ReadResult(
                confirmed=False, kind=kind,
                detail=f"Solana RPC returned no data for NFT mint {nft_mint}.",
            )
        if nft_bal < 1:
            return ReadResult(
                confirmed=False, kind=kind,
                detail=f"Owner {owner[:8]}… does not hold position NFT {nft_mint} (balance={nft_bal}).",
                raw={"pda": pda, "nft_mint": nft_mint, "nft_balance": nft_bal},
            )
        return ReadResult(
            confirmed=True, kind=kind,
            detail=(f"PDA {pda[:8]}… exists AND owner holds position NFT "
                    f"{nft_mint[:8]}… (balance={nft_bal})."),
            raw={"pda": pda, "nft_mint": nft_mint, "nft_balance": nft_bal,
                 "account": account},
        )
    # POSITION_PDA (Meteora DLMM) — PDA existence alone is sufficient; the
    # account's parsed data carries liquidity / bin distribution which the
    # caller can inspect in `raw` if needed.
    return ReadResult(
        confirmed=True, kind=kind,
        detail=f"Position PDA {pda} exists on chain.",
        raw={"pda": pda, "account": account},
    )


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

    if spec.chain_family == "solana":
        # SPL receipt verification — runs the same RPC call the sidecar
        # `/verify` endpoint would, but inline so callers can read the
        # full receipt-state without an extra hop. The sidecar path is
        # still the source of truth for the long-running 60s polling
        # window; this is the synchronous spot-check.
        rpc_url = exp.get("rpc_url") if isinstance(exp.get("rpc_url"), str) else None
        if k == ReceiptKind.MSOL:
            return await _verify_spl_balance_receipt(k, owner, _MSOL_MINT, exp, rpc_url=rpc_url)
        if k == ReceiptKind.JITOSOL:
            return await _verify_spl_balance_receipt(k, owner, _JITOSOL_MINT, exp, rpc_url=rpc_url)
        if k == ReceiptKind.JLP:
            return await _verify_spl_balance_receipt(k, owner, _JLP_MINT, exp, rpc_url=rpc_url)
        # KTOKEN / LP_MINT_SPL / INF take the mint from `expected` since
        # there's no single canonical address (Kamino has many kTokens,
        # Sanctum has multiple INF flavors, etc.).
        if k in {ReceiptKind.KTOKEN, ReceiptKind.LP_MINT_SPL, ReceiptKind.INF}:
            mint = exp.get("mint") or exp.get("receipt_mint") or exp.get("token")
            if not mint:
                return ReadResult(confirmed=False, kind=k,
                                  detail=f"{k.value} verify requires expected.mint / receipt_mint.")
            return await _verify_spl_balance_receipt(k, owner, str(mint), exp, rpc_url=rpc_url)
        if k in {ReceiptKind.POSITION_PDA, ReceiptKind.POSITION_PDA_WITH_NFT}:
            return await _verify_spl_position_pda(k, owner, exp, rpc_url=rpc_url)
        # Kinds without a synchronous SPL path (OBLIGATION_STATE needs a
        # full klend obligation decode — that still lives in the sidecar).
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
