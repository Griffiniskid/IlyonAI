# Curated allowlist of audited Uniswap V4 hook addresses (lowercase).
# Hooks not in this set are refused by preflight to prevent malicious-hook drains.
from typing import Optional

V4_HOOKS_ALLOWLIST: set[str] = {
    # Rebase hook (placeholder; replace with real audited addrs as published)
    "0x0000000000000000000000000000000000000000",  # zero address = no hook (allowed)
    # Dynamic-fee hook (placeholder)
    # "0x1234...": "dynamic_fee",
}


def is_hook_allowed(hook_addr: str) -> bool:
    if not hook_addr:
        return True  # no hook attached, allowed
    return hook_addr.lower() in V4_HOOKS_ALLOWLIST


def check_v4_hook(hook_addr: str) -> Optional[str]:
    """Returns DISALLOWED_V4_HOOK blocker code if not allowed."""
    if not is_hook_allowed(hook_addr):
        return "DISALLOWED_V4_HOOK"
    return None
