"""EVM revert + Solana Anchor error decoder.

Maps the common reverts/Anchor codes our adapters surface back through Enso /
sidecar / Helius simulation into human-readable hints the UI can show next to
the blocked execution plan.

Usage:
    msg = decode_evm_revert(raw_data_or_reason)
    msg = decode_solana_error(logs)
"""
from __future__ import annotations

import re
from typing import Iterable

# Selector → human reason for known EVM custom errors that show up in
# Aave V3 / Compound V3 / Curve / Balancer / Uniswap V3 reverts. Selectors are
# the first 4 bytes of keccak256(errorSignature). Lower-case, no 0x.
_EVM_REVERT_SELECTORS: dict[str, str] = {
    # ERC20 / Permit2
    "08c379a0": "Generic revert with string reason (see decoded_string).",
    "4e487b71": "Panic (arithmetic over/underflow or div by zero).",
    "fb8f41b2": "ERC20InsufficientAllowance — approve more spend first.",
    "e450d38c": "ERC20InsufficientBalance — wallet does not hold enough of the input token.",
    # Aave V3
    "0xb4e35e0e": "AaveV3: amount must be greater than 0.",
    "0xa30bd3e6": "AaveV3: reserve is frozen.",
    # Compound V3
    "73e22b51": "CompoundV3: supply cap reached for this market.",
    # Curve
    "39ec1d49": "Curve: slippage too high — bump slippage_bps or split the deposit.",
    # Balancer
    "0e3c2c00": "Balancer: BAL#208 — token not registered in this pool.",
    # Uniswap V3
    "f4ac6a72": "UniswapV3: tick out of range — refresh quote.",
    # Permit2
    "5638b3e1": "Permit2: signature expired — re-sign the permit.",
    # Enso router
    "1c1bb91d": "Enso router: route reverted at sim — try a smaller amount or different position.",
}

# Aave V3 numeric error codes (uint16 in revert("AAVE_<n>")).
_AAVE_NUM_ERRORS: dict[int, str] = {
    26: "AaveV3 #26 — VL_AMOUNT_NOT_GREATER_THAN_0.",
    27: "AaveV3 #27 — VL_NO_ACTIVE_RESERVE.",
    28: "AaveV3 #28 — VL_RESERVE_FROZEN.",
    37: "AaveV3 #37 — VL_INVALID_INTEREST_RATE_MODE.",
    77: "AaveV3 #77 — SUPPLY_CAP_EXCEEDED.",
    78: "AaveV3 #78 — BORROW_CAP_EXCEEDED.",
    51: "AaveV3 #51 — RESERVE_PAUSED.",
    52: "AaveV3 #52 — RESERVE_DISABLED.",
}


_REVERT_STRING_RE = re.compile(
    r"(?:Reverted with reason string '(?P<msg>[^']*)'"
    r"|execution\s+reverted:?\s*(?P<msg2>.+?)$"
    r"|reverted:?\s+(?P<msg3>[A-Z_][^,;\n]*)"
    r"|Error\((?P<msg4>[^)]+)\))",
    re.IGNORECASE | re.MULTILINE,
)


def decode_evm_revert(raw: str | bytes | None) -> str | None:
    """Return a human reason for an EVM revert blob, or None if unknown.

    Accepts:
      - hex calldata starting with 0x (selector + abi-encoded args).
      - plain revert string from eth_call output ("execution reverted: ...").
      - bytes of any of the above.
    """
    if raw is None:
        return None
    s = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    s_norm = s.strip()
    if not s_norm:
        return None

    # Plain reason text already extracted.
    m = _REVERT_STRING_RE.search(s_norm)
    if m:
        reason = m.group("msg") or m.group("msg2") or m.group("msg3") or m.group("msg4") or ""
        reason = reason.strip()
        # Aave numeric: "AAVE_77" / "77" embedded in reason.
        num_m = re.search(r"\b(?:AAVE_)?(\d{1,3})\b", reason)
        if num_m:
            n = int(num_m.group(1))
            hit = _AAVE_NUM_ERRORS.get(n)
            if hit:
                return hit
        return f"Revert: {reason}" if reason else None

    # Hex selector path.
    hx = s_norm.lower()
    if hx.startswith("0x"):
        hx = hx[2:]
    if len(hx) >= 8:
        sel = hx[:8]
        if sel in _EVM_REVERT_SELECTORS:
            base = _EVM_REVERT_SELECTORS[sel]
            if sel == "08c379a0" and len(hx) >= 8 + 64 + 64:
                # Decode the string body.
                try:
                    str_len = int(hx[8 + 64 : 8 + 128], 16)
                    body = hx[8 + 128 : 8 + 128 + str_len * 2]
                    decoded = bytes.fromhex(body).decode("utf-8", "replace").strip("\x00").strip()
                    return f"Revert: {decoded}" if decoded else base
                except (ValueError, UnicodeDecodeError):
                    pass
            return base

    return None


# Anchor error code → human reason (subset that surfaces from the Solana
# yield-builder sidecar).
_ANCHOR_CODES: dict[int, str] = {
    0x1770: "Slippage tolerance exceeded — bump slippage_bps or refresh the quote.",
    0x1771: "Insufficient input amount.",
    0x1772: "Token account not initialized.",
    0x1773: "Token mint mismatch.",
    0x177c: "Invalid pool authority.",
    0x1779: "Tick array out of range — quote stale, retry.",
    0x178c: "Pool not initialized for this pair.",
    0x1800: "Pool paused.",
    0x6000: "Anchor: ConstraintMut violation.",
    0x1789: "Position is empty — open a new one.",
}


def decode_solana_error(logs: Iterable[str] | str | None) -> str | None:
    """Return a human reason for a Solana simulation/error log block, or None."""
    if not logs:
        return None
    text = "\n".join(logs) if not isinstance(logs, str) else logs
    if not text.strip():
        return None
    # Anchor: "custom program error: 0x1770"
    m = re.search(r"custom program error:\s*0x([0-9a-fA-F]+)", text)
    if m:
        code = int(m.group(1), 16)
        hit = _ANCHOR_CODES.get(code)
        if hit:
            return hit
        return f"Anchor program error 0x{m.group(1)} (unmapped)."
    # Compute budget exceeded.
    if "exceeded CUs" in text or "compute units consumed" in text and "max" in text:
        return "Compute budget exceeded — bump computeUnitLimit on the tx."
    # Insufficient lamports.
    if "insufficient funds" in text.lower() or "insufficient lamports" in text.lower():
        return "Insufficient SOL for fees + rent — top up the wallet."
    # Account not initialized.
    if "AccountNotInitialized" in text or "AccountOwnedByWrongProgram" in text:
        return "Token account or PDA not initialized — sidecar should create the ATA first."
    # Slippage hint that sometimes ships raw.
    if "slippage" in text.lower():
        return "Quote slippage exceeded — refresh the quote and re-sign."
    return None
