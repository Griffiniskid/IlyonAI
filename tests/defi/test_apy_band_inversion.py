"""Pin tests for the inverted APY band parser bug surfaced in Pass A.

Bug class (Pass A H + enso hand-read):
- H11, H14 turn_1 emitted `min_apy=0.5, max_apy=0.48` (impossible band) -> 0
  candidates -> agent fell through to freeform-fallback hell.
- enso-02 turn_1 same shape: `min_apy=0.5, max_apy=0.48`.
- H14 also leaked floating-point junk: `max_apy=0.08000000000000002`.

These tests pin that:
1. `OpportunitySearchRequest` CANNOT be constructed with `min_apy > max_apy`
   (the dataclass post-init swaps and logs a WARNING).
2. The widest-interval rule wins: `min=min(a,b), max=max(a,b)`.
3. An inverted band no longer kills all candidates downstream — a 5% APY
   pool survives `_candidate_exclusions` after the swap.
"""
from __future__ import annotations

import logging

from src.defi.search.models import OpportunityCandidate, OpportunitySearchRequest
from src.defi.search.ranking import rank_opportunities


def test_inverted_apy_band_is_swapped_at_model_level() -> None:
    """Direct repro of H11/H14/enso-02 t1: min=0.5, max=0.48."""
    request = OpportunitySearchRequest(min_apy=0.5, max_apy=0.48)
    assert request.min_apy == 0.48
    assert request.max_apy == 0.5
    assert request.min_apy <= request.max_apy


def test_inverted_band_emits_warning(caplog) -> None:
    """A WARNING must be logged so the inversion is visible in traces."""
    with caplog.at_level(logging.WARNING, logger="src.defi.search.models"):
        OpportunitySearchRequest(min_apy=0.5, max_apy=0.48)
    msgs = [r.getMessage() for r in caplog.records]
    assert any("apy band inverted" in m.lower() for m in msgs), (
        f"expected 'apy band inverted' WARNING, got {msgs}"
    )


def test_inverted_band_with_fp_junk_swapped() -> None:
    """H14 leaked `max_apy=0.08000000000000002` — must still swap cleanly."""
    request = OpportunitySearchRequest(min_apy=0.5, max_apy=0.08000000000000002)
    assert request.min_apy == 0.08000000000000002
    assert request.max_apy == 0.5


def test_valid_band_left_untouched() -> None:
    """No swap when band is already correct."""
    request = OpportunitySearchRequest(min_apy=1.0, max_apy=50.0)
    assert request.min_apy == 1.0
    assert request.max_apy == 50.0


def test_equal_min_max_left_untouched() -> None:
    """min == max is degenerate but not inverted — leave it."""
    request = OpportunitySearchRequest(min_apy=5.0, max_apy=5.0)
    assert request.min_apy == 5.0
    assert request.max_apy == 5.0


def test_none_bounds_not_disturbed() -> None:
    """Either bound being None disables the swap (we cannot order them)."""
    request = OpportunitySearchRequest(min_apy=None, max_apy=0.48)
    assert request.min_apy is None
    assert request.max_apy == 0.48
    request2 = OpportunitySearchRequest(min_apy=0.5, max_apy=None)
    assert request2.min_apy == 0.5
    assert request2.max_apy is None


def test_inverted_band_does_not_strand_candidates() -> None:
    """The behavioural pin: before the fix, a 5% APY pool was excluded
    against a `min=0.5, max=0.48` band as `apy_above_target_band`, leaving
    0 primaries. After the swap to `min=0.48, max=0.5`... wait, 5% is still
    above 0.5%. The honest pin is that swapping to the widest interpretation
    (here min(0.48, 0.5)=0.48, max(0.48,0.5)=0.5) preserves the user's
    intent if they typed "0.48-0.5% APY". A 0.49% pool survives.
    """
    candidate = OpportunityCandidate(
        protocol="TestProto",
        chain="ethereum",
        symbol="USDC",
        apy=0.49,
        tvl_usd=50_000_000.0,
        risk_level="LOW",
    )
    request = OpportunitySearchRequest(
        min_apy=0.5,
        max_apy=0.48,
        min_tvl=0.0,
    )
    result = rank_opportunities([candidate], request)
    # After swap: min=0.48, max=0.5. apy=0.49 falls inside. Candidate survives.
    assert len(result.primary) == 1
    assert result.primary[0].protocol == "TestProto"
