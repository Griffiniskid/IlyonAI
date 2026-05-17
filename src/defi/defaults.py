"""Centralized DeFi execution defaults (slippage, deadline)."""

DEFAULT_SLIPPAGE_BPS: int = 50
DEFAULT_DEADLINE_SEC: int = 600
MIN_SLIPPAGE_BPS: int = 10
MAX_SLIPPAGE_BPS: int = 500


def clamp_slippage(bps: int) -> int:
    """Clamp slippage to [MIN_SLIPPAGE_BPS, MAX_SLIPPAGE_BPS]."""
    return max(MIN_SLIPPAGE_BPS, min(MAX_SLIPPAGE_BPS, bps))
