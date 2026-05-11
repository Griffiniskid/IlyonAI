"""EVM calldata decoder for harness semantic assertions.

Decodes the top selectors our adapters emit so the harness can prove that
mint params, swap params, approve targets and amounts are sane — instead
of just structurally hex-decodable.

Caught at least one real bug already (`amount0_desired=1` on Uniswap V3
mint when USD-price defaults were wrong).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# 4-byte selectors → field schema
_SELECTORS: dict[str, dict[str, Any]] = {
    "0x095ea7b3": {  # ERC20.approve(spender, amount)
        "name": "approve",
        "fields": [("spender", "address"), ("amount", "uint256")],
    },
    "0x88316456": {  # NFP.mint((MintParams))
        "name": "mint",
        "fields": [
            ("token0", "address"),
            ("token1", "address"),
            ("fee", "uint24"),
            ("tickLower", "int24"),
            ("tickUpper", "int24"),
            ("amount0Desired", "uint256"),
            ("amount1Desired", "uint256"),
            ("amount0Min", "uint256"),
            ("amount1Min", "uint256"),
            ("recipient", "address"),
            ("deadline", "uint256"),
        ],
    },
    "0xa9059cbb": {  # ERC20.transfer(to, amount)
        "name": "transfer",
        "fields": [("to", "address"), ("amount", "uint256")],
    },
    "0xac9650d8": {  # Multicall.multicall(bytes[])
        "name": "multicall",
        "fields": [("calls", "bytes[]")],
    },
    "0xe8e33700": {  # UniswapV2Router.addLiquidity
        "name": "addLiquidity",
        "fields": [
            ("tokenA", "address"),
            ("tokenB", "address"),
            ("amountADesired", "uint256"),
            ("amountBDesired", "uint256"),
            ("amountAMin", "uint256"),
            ("amountBMin", "uint256"),
            ("to", "address"),
            ("deadline", "uint256"),
        ],
    },
    "0x617ba037": {  # Aave V3 Pool.supply(asset, amount, onBehalfOf, referralCode)
        "name": "aave_supply",
        "fields": [
            ("asset", "address"),
            ("amount", "uint256"),
            ("onBehalfOf", "address"),
            ("referralCode", "uint16"),
        ],
    },
    "0x4515cef3": {  # Curve add_liquidity (3-coin)
        "name": "curve_add_liquidity_3",
        "fields": [
            ("amounts", "uint256[3]"),
            ("min_mint_amount", "uint256"),
        ],
    },
}


@dataclass
class DecodedCall:
    selector: str
    name: str
    fields: dict[str, Any]
    raw: str

    def assert_(self, **expectations) -> list[str]:
        """Compare each field against an expectation. Returns list of error
        strings (empty on success)."""
        errors: list[str] = []
        for key, expected in expectations.items():
            actual = self.fields.get(key)
            if actual is None:
                errors.append(f"{self.name}.{key}: missing in decoded fields")
                continue
            if isinstance(expected, tuple) and len(expected) == 2:
                lo, hi = expected
                if not (lo <= actual <= hi):
                    errors.append(
                        f"{self.name}.{key}={actual} outside [{lo}, {hi}]"
                    )
            elif callable(expected):
                if not expected(actual):
                    errors.append(
                        f"{self.name}.{key}={actual} predicate failed"
                    )
            elif isinstance(expected, str) and expected.startswith("0x"):
                if isinstance(actual, str) and actual.lower() != expected.lower():
                    errors.append(
                        f"{self.name}.{key}={actual} != {expected}"
                    )
            else:
                if actual != expected:
                    errors.append(f"{self.name}.{key}={actual} != {expected}")
        return errors


def _decode_uint(hex_body: str, offset: int, size: int = 64) -> int:
    return int(hex_body[offset : offset + size], 16)


def _decode_int(hex_body: str, offset: int, size: int = 64) -> int:
    raw = int(hex_body[offset : offset + size], 16)
    if raw >= 2**255:
        return raw - 2**256
    return raw


def _decode_address(hex_body: str, offset: int) -> str:
    return "0x" + hex_body[offset + 24 : offset + 64]


def decode(calldata: str | None) -> DecodedCall | None:
    """Decode a hex calldata blob into structured fields. Returns None if
    selector is unknown / shape doesn't fit."""
    if not calldata or not isinstance(calldata, str):
        return None
    if not calldata.startswith("0x"):
        return None
    if len(calldata) < 10:
        return None
    selector = calldata[:10].lower()
    schema = _SELECTORS.get(selector)
    if not schema:
        return DecodedCall(selector=selector, name="unknown", fields={}, raw=calldata)

    body = calldata[10:]
    decoded: dict[str, Any] = {}
    offset = 0
    for field_name, field_type in schema["fields"]:
        if field_type == "address":
            decoded[field_name] = _decode_address(body, offset)
            offset += 64
        elif field_type in {"uint256", "uint24", "uint16"}:
            decoded[field_name] = _decode_uint(body, offset)
            offset += 64
        elif field_type in {"int24", "int256"}:
            decoded[field_name] = _decode_int(body, offset)
            offset += 64
        elif field_type == "uint256[3]":
            # Inline fixed-size array
            decoded[field_name] = [
                _decode_uint(body, offset + i * 64) for i in range(3)
            ]
            offset += 3 * 64
        elif field_type == "bytes[]":
            # Skip variable-length — caller can re-decode each inner call
            decoded[field_name] = "<bytes[] — re-decode each entry>"
            break
        else:
            decoded[field_name] = None

    return DecodedCall(
        selector=selector,
        name=schema["name"],
        fields=decoded,
        raw=calldata,
    )


# Convenience: full-step assertion
def assert_mint_sane(decoded: DecodedCall, *, recipient: str, fee_bps: int) -> list[str]:
    """Sanity assertions for a Uniswap V3 NonfungiblePositionManager mint."""
    if decoded.name != "mint":
        return [f"expected mint, got {decoded.name}"]
    errors: list[str] = []
    # Sanity: both desired amounts must be > 0 when range straddles current tick.
    amount0 = decoded.fields.get("amount0Desired", 0)
    amount1 = decoded.fields.get("amount1Desired", 0)
    tick_lower = decoded.fields.get("tickLower", 0)
    tick_upper = decoded.fields.get("tickUpper", 0)
    if tick_lower >= tick_upper:
        errors.append(f"mint.tickLower {tick_lower} >= tickUpper {tick_upper}")
    if amount0 == 0 and amount1 == 0:
        errors.append("mint.amount0Desired and amount1Desired are both 0 — degenerate position")
    # Slippage: min must be ≤ desired.
    if decoded.fields.get("amount0Min", 0) > amount0:
        errors.append("mint.amount0Min > amount0Desired")
    if decoded.fields.get("amount1Min", 0) > amount1:
        errors.append("mint.amount1Min > amount1Desired")
    # Recipient sanity.
    if recipient and (decoded.fields.get("recipient") or "").lower() != recipient.lower():
        errors.append(
            f"mint.recipient {decoded.fields.get('recipient')} != expected {recipient}"
        )
    # Fee sanity.
    if fee_bps and decoded.fields.get("fee") != fee_bps:
        errors.append(f"mint.fee {decoded.fields.get('fee')} != expected {fee_bps}")
    # Deadline must be future.
    import time

    if decoded.fields.get("deadline", 0) <= int(time.time()):
        errors.append(
            f"mint.deadline {decoded.fields.get('deadline')} already passed (now={int(time.time())})"
        )
    return errors


def assert_approve_sane(decoded: DecodedCall, *, spender: str | None = None) -> list[str]:
    if decoded.name != "approve":
        return [f"expected approve, got {decoded.name}"]
    errors: list[str] = []
    if decoded.fields.get("amount", 0) == 0:
        errors.append("approve.amount is 0 — won't unlock spending")
    if spender and (decoded.fields.get("spender") or "").lower() != spender.lower():
        errors.append(
            f"approve.spender {decoded.fields.get('spender')} != expected {spender}"
        )
    return errors


def assert_curve_add_liquidity_sane(decoded: DecodedCall) -> list[str]:
    if decoded.name != "curve_add_liquidity_3":
        return [f"expected curve_add_liquidity_3, got {decoded.name}"]
    amounts = decoded.fields.get("amounts", [0, 0, 0])
    if sum(int(a) for a in amounts) == 0:
        return ["curve add_liquidity: all amounts are 0"]
    return []
