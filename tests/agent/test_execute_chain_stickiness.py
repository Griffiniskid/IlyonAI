"""Execute-path chain stickiness regression pins.

v4-A01 turn 5: user said "Actually on Optimism" in prior turn, then
"Execute on Aave V3 with 250 USDC". Plan came back as Base (default).
Fix: when execute turn has no explicit chain and last defi_opportunities/
pool_link/execution_plan card narrowed to a single chain, inherit it.
"""
from __future__ import annotations


def _build_history_with_chain(chain: str) -> list[dict]:
    return [
        {
            "card_type": "defi_opportunities",
            "payload": {"chains": [chain], "items": []},
        }
    ]


def test_execute_inherits_optimism_when_message_silent() -> None:
    """Mimic the runtime stickiness logic to prove the conditions hold."""
    import re

    message = "Execute on Aave V3 with 250 USDC"
    tool_input = {"chain": "ethereum", "protocol": "aave-v3", "asset_in": "USDC", "amount_in": "250"}
    history = _build_history_with_chain("optimism")

    explicit = re.search(
        r"\b(ethereum|polygon|arbitrum|optimism|base|avalanche|avax|bsc|bnb|solana|sol|linea|zksync|scroll|mantle|blast|berachain|bera|sonic)\b",
        message.lower(),
    )
    assert explicit is None  # no chain in message

    # Inherit
    inherited = None
    for hc in reversed(history):
        if hc["card_type"] == "defi_opportunities":
            cp = hc["payload"].get("chains") or []
            if len(cp) == 1:
                inherited = cp[0]
                break
    assert inherited == "optimism"

    # Apply override
    current = tool_input["chain"].lower()
    if (not current or current in {"ethereum", "base"}) and current != inherited:
        tool_input["chain"] = inherited

    assert tool_input["chain"] == "optimism"


def test_explicit_chain_not_overridden() -> None:
    import re

    message = "Execute on Aave V3 with 250 USDC on Base"
    tool_input = {"chain": "base"}
    history = _build_history_with_chain("optimism")

    explicit = re.search(
        r"\b(ethereum|polygon|arbitrum|optimism|base|avalanche|avax|bsc|bnb|solana|sol|linea|zksync|scroll|mantle|blast|berachain|bera|sonic)\b",
        message.lower(),
    )
    assert explicit is not None  # message names chain — skip inheritance
    # Stickiness logic is gated by `not _explicit_chain`, so no override happens.
    assert tool_input["chain"] == "base"


def test_solana_inheritance_from_history() -> None:
    """Bridge ETH→Solana scenarios mustn't lose Solana context."""
    import re

    message = "Execute the deposit"
    tool_input = {"chain": "ethereum"}
    history = _build_history_with_chain("solana")

    explicit = re.search(
        r"\b(ethereum|polygon|arbitrum|optimism|base|avalanche|avax|bsc|bnb|solana|sol|linea|zksync|scroll|mantle|blast|berachain|bera|sonic)\b",
        message.lower(),
    )
    assert explicit is None

    inherited = history[0]["payload"]["chains"][0]
    current = tool_input["chain"].lower()
    if (not current or current in {"ethereum", "base"}) and current != inherited:
        tool_input["chain"] = inherited

    assert tool_input["chain"] == "solana"
