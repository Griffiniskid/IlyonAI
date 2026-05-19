"""V7-049 pin tests: V4 hook allowlist preflight gate."""
import pathlib

from src.data.v4_hooks_allowlist import (
    V4_HOOKS_ALLOWLIST,
    V4_HOOKS_ALLOWLIST_BY_CHAIN,
    check_v4_hook,
    is_hook_allowed,
)


def test_is_hook_allowed_empty_string():
    """Empty string = no hook attached, allowed."""
    assert is_hook_allowed("") is True


def test_is_hook_allowed_zero_address():
    """Zero address = canonical no-hook sentinel, allowed."""
    assert is_hook_allowed("0x0000000000000000000000000000000000000000") is True


def test_is_hook_allowed_zero_address_uppercase():
    """Case-insensitive match against allowlist (stored lowercase)."""
    assert is_hook_allowed("0X0000000000000000000000000000000000000000") is True


def test_is_hook_allowed_random_address_rejected():
    """Arbitrary non-allowlisted hook is refused."""
    assert is_hook_allowed("0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef") is False


def test_is_hook_allowed_random_string_rejected():
    """Garbage input is refused (not in allowlist)."""
    assert is_hook_allowed("0xrandomaddr") is False


def test_check_v4_hook_allowed_returns_none():
    """Allowed hook returns no blocker code."""
    assert check_v4_hook("0x0000000000000000000000000000000000000000") is None
    assert check_v4_hook("") is None


def test_check_v4_hook_disallowed_returns_blocker():
    """Disallowed hook returns DISALLOWED_V4_HOOK blocker code."""
    assert check_v4_hook("0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef") == "DISALLOWED_V4_HOOK"
    assert check_v4_hook("0xrandomaddr") == "DISALLOWED_V4_HOOK"


def test_allowlist_contains_zero_address():
    """Sanity: allowlist must include zero address as no-hook sentinel."""
    assert "0x0000000000000000000000000000000000000000" in V4_HOOKS_ALLOWLIST


def test_allowlist_stored_lowercase():
    """All entries must be lowercase for case-insensitive matching to work."""
    for addr in V4_HOOKS_ALLOWLIST:
        assert addr == addr.lower(), f"Allowlist entry {addr!r} must be lowercase"
    for (_chain_id, addr) in V4_HOOKS_ALLOWLIST_BY_CHAIN:
        assert addr == addr.lower(), f"Per-chain allowlist entry {addr!r} must be lowercase"


# ── V7-049: populated-allowlist + chain-keyed + preflight wire-up pins ────

# Verified mainnet hook addresses sourced from Uniswap's official hooklist
# registry on 2026-05-19 and confirmed via Etherscan "Exact Match" source
# verification. Keep these in sync with src/data/v4_hooks_allowlist.py —
# if you change the addresses there, update these constants too.
_ANGSTROM_ADDR = "0x0000000aa232009084bd71a5797d089aa4edfad4"     # Sorella Labs Angstrom
_BUNNI_ADDR = "0x00001f3b9712708127b1fcad61cb892535951888"        # Bunni v2 BunniHook
_ETHEREUM_CHAIN_ID = 1


def test_allowlist_has_minimum_three_entries():
    """V7-049 — allowlist must contain ≥ 3 entries (zero-addr + ≥ 2 verified
    real hook addresses). Empty placeholder is no longer acceptable."""
    assert len(V4_HOOKS_ALLOWLIST) >= 3, (
        f"V4_HOOKS_ALLOWLIST must hold zero-address + at least 2 verified "
        f"hook addresses; saw {len(V4_HOOKS_ALLOWLIST)} entries."
    )
    # And the per-chain map must have at least 2 entries (the real hooks).
    assert len(V4_HOOKS_ALLOWLIST_BY_CHAIN) >= 2, (
        f"V4_HOOKS_ALLOWLIST_BY_CHAIN must hold ≥ 2 verified entries; "
        f"saw {len(V4_HOOKS_ALLOWLIST_BY_CHAIN)} entries."
    )


def test_verified_hooks_pass_chain_keyed_check():
    """V7-049 — each verified hook is accepted on its real chain."""
    assert is_hook_allowed(_ANGSTROM_ADDR, _ETHEREUM_CHAIN_ID) is True
    assert is_hook_allowed(_BUNNI_ADDR, _ETHEREUM_CHAIN_ID) is True
    # check_v4_hook returns None (no blocker) for the same.
    assert check_v4_hook(_ANGSTROM_ADDR, _ETHEREUM_CHAIN_ID) is None
    assert check_v4_hook(_BUNNI_ADDR, _ETHEREUM_CHAIN_ID) is None


def test_verified_hooks_pass_legacy_unchained_check():
    """V7-049 — backwards-compat: callers that don't pass chain_id still
    accept the flat allowlist of verified addresses."""
    assert is_hook_allowed(_ANGSTROM_ADDR) is True
    assert is_hook_allowed(_BUNNI_ADDR) is True


def test_verified_hooks_rejected_on_wrong_chain():
    """V7-049 — chain-keyed lookup is strict. Hook approved on Ethereum
    mainnet must NOT be auto-accepted on an L2 where it isn't audited."""
    # Arbitrum chain id 42161 — neither verified hook is approved there.
    assert is_hook_allowed(_ANGSTROM_ADDR, 42161) is False
    assert check_v4_hook(_ANGSTROM_ADDR, 42161) == "DISALLOWED_V4_HOOK"


def test_random_address_rejected_with_chain_id():
    """V7-049 — chain-keyed: random unverified address is still refused."""
    assert is_hook_allowed("0xfeedfacefeedfacefeedfacefeedfacefeedface", _ETHEREUM_CHAIN_ID) is False
    assert check_v4_hook(
        "0xfeedfacefeedfacefeedfacefeedfacefeedface", _ETHEREUM_CHAIN_ID
    ) == "DISALLOWED_V4_HOOK"


def test_preflight_imports_check_v4_hook():
    """V7-049 callsite-presence pin: preflight.py MUST import and call
    check_v4_hook. If this assertion fails the preflight gate has been
    removed and any V4 pool (including malicious hooks) would route
    through unchecked.
    """
    preflight_src = pathlib.Path("src/defi/execution/preflight.py").read_text(
        encoding="utf-8"
    )
    assert "check_v4_hook(" in preflight_src, (
        "preflight does not call check_v4_hook — V4 hook allowlist gate "
        "has been removed or never wired."
    )
    assert "from src.data.v4_hooks_allowlist import" in preflight_src, (
        "preflight does not import from src.data.v4_hooks_allowlist."
    )
    assert "DISALLOWED_V4_HOOK" in preflight_src, (
        "preflight does not emit the DISALLOWED_V4_HOOK blocker code."
    )
