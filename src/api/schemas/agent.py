"""Cross-workstream schemas for the agent platform.

These are frozen at Day 0. Every workstream reads them; no workstream
may silently extend them. Breaking changes require a migration task.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SentinelBlock(_Strict):
    sentinel: int = Field(ge=0, le=100)
    safety: int = Field(ge=0, le=100)
    durability: int = Field(ge=0, le=100)
    exit: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    risk_level: Literal["HIGH", "MEDIUM", "LOW"]
    strategy_fit: Literal["conservative", "balanced", "aggressive"]
    flags: list[str] = Field(default_factory=list)


class ShieldBlock(_Strict):
    verdict: Literal["SAFE", "CAUTION", "RISKY", "DANGEROUS", "SCAM"]
    grade: Literal["A+", "A", "B", "C", "D", "F"]
    reasons: list[str] = Field(default_factory=list)


class _CardPayloadBase(_Strict):
    sentinel: Optional[SentinelBlock] = None
    shield: Optional[ShieldBlock] = None


class AllocationPosition(_Strict):
    rank: int
    protocol: str
    asset: str
    chain: str
    apy: str
    weight: int
    usd: str
    router: str
    sentinel: Optional[SentinelBlock] = None
    shield: Optional[ShieldBlock] = None


class AllocationPayload(_CardPayloadBase):
    positions: list[AllocationPosition]
    total_usd: str
    weighted_sentinel: int
    risk_mix: dict[str, int]


class SwapQuotePayload(_CardPayloadBase):
    pay: dict[str, Any]
    receive: dict[str, Any]
    rate: str
    router: str
    price_impact_pct: float
    priority_fee_usd: Optional[str] = None


class PoolPayload(_CardPayloadBase):
    protocol: str
    chain: str
    asset: str
    apy: str
    tvl: str


class TokenPayload(_CardPayloadBase):
    symbol: str
    address: str
    chain: str
    price_usd: str
    change_24h_pct: float


class PositionPayload(_CardPayloadBase):
    wallet: str
    rows: list[dict[str, Any]]


class PlanStep(_Strict):
    step: int
    action: str
    detail: str


class PlanPayload(_CardPayloadBase):
    steps: list[PlanStep]
    requires_signature: bool


class BalancePayload(_CardPayloadBase):
    wallet: str
    total_usd: str
    by_chain: dict[str, str]


class BridgePayload(_CardPayloadBase):
    source_chain: str
    target_chain: str
    pay: dict[str, Any]
    receive: dict[str, Any]
    estimated_seconds: int


class StakePayload(_CardPayloadBase):
    protocol: str
    asset: str
    apy: str
    unbond_days: Optional[int] = None


class MarketOverviewPayload(_CardPayloadBase):
    protocols: list[dict[str, Any]]


class PairListPayload(_CardPayloadBase):
    query: str
    pairs: list[dict[str, Any]]


class _CardBase(_Strict):
    card_id: str


class AllocationCard(_CardBase):
    card_type: Literal["allocation"]
    payload: AllocationPayload


class SwapQuoteCard(_CardBase):
    card_type: Literal["swap_quote"]
    payload: SwapQuotePayload


class PoolCard(_CardBase):
    card_type: Literal["pool"]
    payload: PoolPayload


class TokenCard(_CardBase):
    card_type: Literal["token"]
    payload: TokenPayload


class PositionCard(_CardBase):
    card_type: Literal["position"]
    payload: PositionPayload


class PlanCard(_CardBase):
    card_type: Literal["plan"]
    payload: PlanPayload


class BalanceCard(_CardBase):
    card_type: Literal["balance"]
    payload: BalancePayload


class BridgeCard(_CardBase):
    card_type: Literal["bridge"]
    payload: BridgePayload


class StakeCard(_CardBase):
    card_type: Literal["stake"]
    payload: StakePayload


class MarketOverviewCard(_CardBase):
    card_type: Literal["market_overview"]
    payload: MarketOverviewPayload


class PairListCard(_CardBase):
    card_type: Literal["pair_list"]
    payload: PairListPayload


_CardUnion = Annotated[
    Union[
        AllocationCard, SwapQuoteCard, PoolCard, TokenCard,
        PositionCard, PlanCard, BalanceCard, BridgeCard,
        StakeCard, MarketOverviewCard, PairListCard,
    ],
    Field(discriminator="card_type"),
]

_CardAdapter: TypeAdapter = TypeAdapter(_CardUnion)


class AgentCard(_Strict):
    """Wrapper enabling discriminated parsing via .model_validate."""
    card_id: str
    card_type: str
    payload: Any

    @classmethod
    def model_validate(cls, obj: Any, **kw):  # type: ignore[override]
        return _CardAdapter.validate_python(obj)


CardType = Literal[
    "allocation", "swap_quote", "pool", "token", "position", "plan",
    "balance", "bridge", "stake", "market_overview", "pair_list",
]


class ToolError(_Strict):
    code: str
    message: str


class ToolEnvelope(_Strict):
    ok: bool
    data: Optional[dict] = None
    sentinel: Optional[SentinelBlock] = None
    shield: Optional[ShieldBlock] = None
    card_type: Optional[CardType] = None
    card_id: str
    card_payload: Optional[dict] = None
    error: Optional[ToolError] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.ok and self.error is None:
            raise ValueError("ToolEnvelope(ok=False) requires error")


class ThoughtFrame(_Strict):
    step_index: int
    content: str


class ToolFrame(_Strict):
    step_index: int
    name: str
    args: dict


class ObservationFrame(_Strict):
    step_index: int
    name: str
    ok: bool
    error: Optional[ToolError] = None


class CardFrame(_Strict):
    step_index: int
    card_id: str
    card_type: CardType
    payload: dict


class FinalFrame(_Strict):
    content: str
    card_ids: list[str]
    elapsed_ms: int
    steps: int


class DoneFrame(_Strict):
    pass


SSEFrame = Union[ThoughtFrame, ToolFrame, ObservationFrame, CardFrame, FinalFrame, DoneFrame]
