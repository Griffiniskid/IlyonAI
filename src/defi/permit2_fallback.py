"""Permit2 wallet-capability detection with ERC-20 approve fallback.

V7-038: Detects Permit2 support via EIP-5792 wallet_getCapabilities and falls
back to ERC-20 approve() calldata when the wallet does not advertise support.
"""

PERMIT2_ADDRESS: str = "0x000000000022D473030F116dDEE9F6B43aC78BA3"


def supports_permit2(capabilities: dict) -> bool:
    """Reads wallet_getCapabilities EIP-5792 response.
    capabilities shape: {"chainId": {"permit2": {"supported": bool}}}
    """
    if not capabilities or not isinstance(capabilities, dict):
        return False
    for _chain_id, caps in capabilities.items():
        p2 = caps.get("permit2") if isinstance(caps, dict) else None
        if isinstance(p2, dict) and p2.get("supported"):
            return True
    return False


def fallback_approve_calldata(token_addr: str, spender: str, amount: int) -> dict:
    """Returns ERC-20 approve(spender, amount) calldata dict."""
    # selector: 0x095ea7b3 = approve(address,uint256)
    selector = "0x095ea7b3"
    padded_spender = spender.lower().replace("0x", "").rjust(64, "0")
    padded_amount = hex(amount)[2:].rjust(64, "0")
    data = selector + padded_spender + padded_amount
    return {"to": token_addr, "data": data, "value": "0x0"}
