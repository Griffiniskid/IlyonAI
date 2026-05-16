"""Pin top-one prior-pools sticky carve-out against bare-digit false-match.

v4-A19/A20 caught: 'Stake 1 SOL on Marinade' with prior defi_opportunities
card whose top item was 'gmtrade SOL-USDC' (turn 2 lost the staking filter)
routed to prior-card 'gmtrade SOL-USDC' execute_pool_position instead of
detect_intent's Marinade dispatch. Root cause: explicit-ref regex
`#?\s*1\b` matched the bare '1' in '1 SOL' amount token, disabling the
protocol carve-out at line 5726.
"""
from __future__ import annotations

import re


def test_carve_out_keeps_explicit_proto_with_bare_amount():
    """Explicit-ref regex must NOT match the digit in '1 SOL' / '1 USDC'."""
    explicit_ref_re = re.compile(r"\b(top|first|best|1st)\b|#\s*1\b", re.IGNORECASE)
    # Names that include bare digit amount but NO ordinal selector — should
    # NOT match (carve-out should fire and protect detect_intent dispatch).
    no_match = [
        "Stake 1 SOL on Marinade",
        "Stake 1 SOL on Jito",
        "Deposit 0.1 ETH to Aave V3 Optimism",
        "Supply 100 USDC to Aave V3 on Base",
        "Stake 1 ETH on Lido",
        "Withdraw all USDC from Aave V3 Base",
        "Bridge 100 USDC from Ethereum to Arbitrum",
    ]
    for msg in no_match:
        assert not explicit_ref_re.search(msg), f"{msg!r} unexpectedly matched explicit_ref"

    # Real ordinal selectors — should match.
    match = [
        "Pick #1",
        "Pick # 1",
        "Use the top pool",
        "Take the first one",
        "Best item",
        "The 1st option",
    ]
    for msg in match:
        assert explicit_ref_re.search(msg), f"{msg!r} should match explicit_ref"
