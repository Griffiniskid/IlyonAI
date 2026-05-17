"""V7-002 §7 S12 — Claim-and-compound composer.

Spec quote (`IlyonAi_Development_Plan_v2.md` §V7-002):
  "S12 claim_compound ... write `src/defi/adapters/claim_compound_composer.py`
  2-step composer"

The user message that the detector matches looks like:
  "Claim my Aave rewards and re-stake into stkAAVE"

The detector (`src/agent/simple_runtime.py::_detect_claim_compound`)
emits action="claim_compound" with extra.reward_token + extra.stake_target.
This composer turns that single intent into two ordered ExecutionStepV3
hops:

  0. claim         — pull accrued rewards from the staking protocol's
                     incentives contract (e.g. Aave IncentivesController,
                     Compound CometRewards, Aerodrome Voter, Slipstream
                     gauge.claimFees).
  1. supply_back   — re-supply the claimed reward token into the same
                     protocol (or the explicit `stake_target` override
                     when present, e.g. stkAAVE staking module).

The composer is calldata-free; the per-protocol adapter (`AaveV3SupplyAdapter`,
`CompoundV3SupplyAdapter`, etc.) stamps the actual `transaction` payload
when `build_yield_execution_plan` walks each step. The composer's job
is to (a) prove the action expresses as `[claim, supply_back]`, (b)
wire `depends_on` so the supply leg waits on the claim receipt, and
(c) map detector-supplied protocol slugs to the canonical adapter
protocol IDs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.defi.execution.models import ExecutionStepV3, make_step


# Detector → adapter protocol slug. Keeps the composer in lock-step with
# `simple_runtime.py::_CLAIM_COMPOUND_PROTOS` so an "aave"-typed claim
# routes to the same adapter ID the capability registry sees.
_PROTO_TO_ADAPTER: dict[str, str] = {
    "aave-v3": "aave-v3",
    "aave": "aave-v3",
    "compound-v3": "compound-v3",
    "compound": "compound-v3",
    "comet": "compound-v3",
    "aerodrome": "aerodrome",
    "velodrome": "velodrome",
    "slipstream": "aerodrome-slipstream",
    "aerodrome-slipstream": "aerodrome-slipstream",
    # Fall-through: when the protocol isn't in this map, keep the
    # detector slug as-is so the registry's slug-aliasing still wins.
}


def _resolve_protocol(slug: str) -> str:
    s = (slug or "").strip().lower()
    return _PROTO_TO_ADAPTER.get(s, s)


@dataclass
class ClaimCompoundComposer:
    """Compose the two-leg [claim, supply_back] plan for §7 S12.

    `build(action_spec)` returns exactly two `ExecutionStepV3`s — the
    pin test in `tests/defi/test_s11_s14_s12_end_to_end.py` asserts
    the shape, the dependency wire, and the `claim_compound` routing.
    """

    composer_id: str = "claim-compound-v7-002"

    def build(self, action_spec: dict[str, Any]) -> list[ExecutionStepV3]:
        """Return [claim, supply_back] given the detector's action_spec.

        Required keys in `action_spec`:
          - chain            — "ethereum" / "polygon" / ...
          - protocol         — detector protocol slug ("aave-v3", etc.)
          - asset_in         — reward token symbol (AAVE, COMP, ...)
          - extra.reward_token  — same as asset_in; defensively re-read
                                  so detector + agent both work.
          - extra.stake_target  — optional override (e.g. "stkaave");
                                  defaults to the source protocol so the
                                  user "re-stakes" into the same pool.
        """
        chain = (action_spec.get("chain") or "ethereum").lower()
        protocol_raw = (action_spec.get("protocol") or "").lower()
        protocol = _resolve_protocol(protocol_raw)
        extra = action_spec.get("extra") or {}
        reward_token = str(
            extra.get("reward_token") or action_spec.get("asset_in") or ""
        ).upper()
        if not reward_token:
            raise ValueError(
                "claim_compound composer requires a reward_token (e.g. AAVE, COMP)."
            )
        stake_target_raw = extra.get("stake_target") or protocol
        stake_target = str(stake_target_raw).lower()
        # Wallet kind — Aave/Compound/Aerodrome/Slipstream are EVM-only.
        wallet: str = "MetaMask"
        if chain == "solana":
            wallet = "Phantom"

        claim_step = make_step(
            index=0,
            action="claim_rewards",
            title=f"Claim {reward_token} from {protocol}",
            description=(
                f"Pull accrued {reward_token} rewards from the {protocol} "
                f"incentives controller on {chain}."
            ),
            chain=chain,
            wallet=wallet,
            protocol=protocol,
            asset_in=reward_token,
        )
        # The compound leg's adapter routing keys are
        # (chain, stake_target_protocol, action='supply'); we surface
        # 'supply' so the capability registry can pick the supply
        # adapter for the destination (which may differ from the
        # claim protocol when stake_target is overridden — e.g.
        # claim AAVE from aave-v3 → supply into stkAAVE staking).
        compound_step = make_step(
            index=1,
            action="supply",
            title=f"Re-supply {reward_token} into {stake_target}",
            description=(
                f"Compound the claimed {reward_token} by supplying it back "
                f"into {stake_target} on {chain}."
            ),
            chain=chain,
            wallet=wallet,
            protocol=stake_target,
            asset_in=reward_token,
            depends_on=[claim_step.step_id],
        )
        return [claim_step, compound_step]
