"""Spec §6a / §11 D.4 — Uniswap V4 hook allowlist.

V4 pools can attach arbitrary hook contracts that execute callbacks at
lifecycle events (beforeSwap, afterSwap, beforeAddLiquidity, etc.). A
malicious hook can redirect funds, freeze positions, or front-run the
mint. Spec §6a mandates a hook allowlist; Shield refuses unknown hooks
unless the user explicitly opts into experimental pools.

This module is the canonical hook registry. Adding an address requires:
  1. The hook contract is audited (link the report).
  2. The protocol behind it has a clear governance + upgrade path.
  3. The deployment is on a chain in scope.

`is_allowed(hook_addr, chain_id)` returns True only for audited hooks.
For experimental opt-in flows the V4 adapter passes
`allow_experimental=True` to bypass; that flag is set ONLY when the
user explicitly typed "yes I understand the hook is unaudited".
"""
from __future__ import annotations

from dataclasses import dataclass

# Empty hook = no callbacks. address(0) is allowed by definition.
NO_HOOK = "0x0000000000000000000000000000000000000000"


@dataclass(frozen=True)
class HookEntry:
    address: str
    chain_id: int
    name: str
    audit_report: str         # URL of the audit
    properties: tuple[str, ...]  # e.g. ("dynamic-fee",) ("LVR-mitigation",) ("MEV-skim",)


# Allowlist — populated conservatively. Add entries via PRs that include
# the audit report link + property tags. Empty by default at launch.
_ALLOWLIST: dict[tuple[str, int], HookEntry] = {}


def is_no_hook(addr: str | None) -> bool:
    if not addr:
        return True
    return addr.lower() == NO_HOOK.lower()


def is_allowed(addr: str | None, chain_id: int, *, allow_experimental: bool = False) -> bool:
    """Return True if the V4 hook is allowed for this chain.

    The empty/zero hook is always allowed. Other hooks require an entry
    in the allowlist OR explicit `allow_experimental=True` opt-in.
    """
    if is_no_hook(addr):
        return True
    if allow_experimental:
        return True
    if not addr:
        return False
    return (addr.lower(), int(chain_id)) in _ALLOWLIST


def describe_hook(addr: str, chain_id: int) -> HookEntry | None:
    """Returns the allowlist entry for display in the Preview card."""
    return _ALLOWLIST.get((addr.lower(), int(chain_id)))


def all_entries() -> list[HookEntry]:
    return list(_ALLOWLIST.values())


def shield_verdict_for_hook(addr: str | None, chain_id: int) -> dict[str, str | bool]:
    """Returns the canonical Shield gate verdict for a hook, ready to
    embed in the Preview card. UI surfaces this verbatim.
    """
    if is_no_hook(addr):
        return {
            "allowlist_match": True,
            "severity": "info",
            "headline": "No hook attached.",
            "detail": "Vanilla V4 pool — no callback contracts execute at lifecycle events.",
        }
    entry = describe_hook(addr or "", chain_id)
    if entry is None:
        return {
            "allowlist_match": False,
            "severity": "critical",
            "headline": f"Unknown V4 hook: {addr}.",
            "detail": (
                "This hook is NOT on Ilyon's audited allowlist. Refusing to build the "
                "mint plan. To opt into experimental V4 pools, pass allow_experimental=True "
                "in your message (e.g., 'mint this with experimental hooks: yes')."
            ),
        }
    return {
        "allowlist_match": True,
        "severity": "info",
        "headline": f"V4 hook: {entry.name}",
        "detail": (
            f"Audited hook ({entry.audit_report}). Properties: "
            f"{', '.join(entry.properties) or 'none'}."
        ),
    }
