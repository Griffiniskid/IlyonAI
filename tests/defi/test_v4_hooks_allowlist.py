"""V7-049 pin tests: V4 hook allowlist preflight gate."""
from src.data.v4_hooks_allowlist import (
    V4_HOOKS_ALLOWLIST,
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
