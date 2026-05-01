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


ChainTone = Literal["eth", "sol", "arb", "mainnet", "base", "polygon", "bsc", "op", "avax"]
RiskLevelLower = Literal["low", "medium", "high"]
StrategyFit = Literal["conservative", "balanced", "aggressive"]
WalletKind = Literal["MetaMask", "Phantom", "WalletConnect"]


class AllocationPosition(_Strict):
    rank: int
    protocol: str
    asset: str
    chain: ChainTone
    apy: str
    sentinel: int = Field(ge=0, le=100)
    risk: RiskLevelLower
    fit: StrategyFit
    weight: int = Field(ge=0, le=100)
    usd: str
    tvl: str
    router: str
    safety: int = Field(ge=0, le=100)
    durability: int = Field(ge=0, le=100)
    exit: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    flags: list[str] = Field(default_factory=list)


class AllocationPayload(_CardPayloadBase):
    positions: list[AllocationPosition]
    total_usd: str
    blended_apy: str
    chains: int
    weighted_sentinel: int = Field(ge=0, le=100)
    risk_mix: dict[str, int]
    combined_tvl: str


class SentinelMatrixPayload(_CardPayloadBase):
    positions: list[AllocationPosition]
    low_count: int
    medium_count: int
    high_count: int
    weighted_sentinel: int = Field(ge=0, le=100)


class ExecutionStep(_Strict):
    index: int
    verb: str
    amount: str
    asset: str
    target: str
    chain: ChainTone
    router: str
    wallet: WalletKind
    gas: str


class ExecutionPlanPayload(_CardPayloadBase):
    steps: list[ExecutionStep]
    total_gas: str
    slippage_cap: str
    wallets: str
    tx_count: int
    requires_signature: bool = True


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


class PlanStepV2(_Strict):
    step_id: str
    order: int
    action: Literal[
        "swap",
        "bridge",
        "stake",
        "unstake",
        "deposit_lp",
        "withdraw_lp",
        "transfer",
        "approve",
        "wait_receipt",
        "get_balance",
    ]
    params: dict[str, Any]
    depends_on: list[str] = Field(default_factory=list)
    resolves_from: dict[str, str] = Field(default_factory=dict)
    sentinel: Optional[SentinelBlock] = None
    shield_flags: list[str] = Field(default_factory=list)
    estimated_gas_usd: Optional[float] = None
    estimated_duration_s: Optional[int] = None
    status: Literal[
        "pending",
        "ready",
        "signing",
        "broadcast",
        "confirmed",
        "failed",
        "skipped",
    ] = "pending"
    tx_hash: Optional[str] = None
    receipt: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class ExecutionPlanV2Payload(_CardPayloadBase):
    plan_id: str
    title: str
    steps: list[PlanStepV2]
    total_steps: int
    total_gas_usd: float
    total_duration_estimate_s: int
    blended_sentinel: Optional[int] = Field(default=None, ge=0, le=100)
    requires_signature_count: int
    risk_warnings: list[str] = Field(default_factory=list)
    risk_gate: Literal["clear", "soft_warn", "hard_block"] = "clear"
    requires_double_confirm: bool = False
    chains_touched: list[str] = Field(default_factory=list)
    user_assets_required: dict[str, str] = Field(default_factory=dict)


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


class SentinelMatrixCard(_CardBase):
    card_type: Literal["sentinel_matrix"]
    payload: SentinelMatrixPayload


class ExecutionPlanCard(_CardBase):
    card_type: Literal["execution_plan"]
    payload: ExecutionPlanPayload


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


class ExecutionPlanV2Card(_CardBase):
    card_type: Literal["execution_plan_v2"]
    payload: ExecutionPlanV2Payload


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
        AllocationCard, SentinelMatrixCard, ExecutionPlanCard,
        SwapQuoteCard, PoolCard, TokenCard,
        PositionCard, PlanCard, ExecutionPlanV2Card, BalanceCard, BridgeCard,
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
    "allocation", "sentinel_matrix", "execution_plan",
    "swap_quote", "pool", "token", "position", "plan",
    "execution_plan_v2", "balance", "bridge", "stake", "market_overview", "pair_list",
]


class ToolError(_Strict):
    code: str
    message: str


class ExtraCard(_Strict):
    card_id: str
    card_type: CardType
    payload: dict


class ToolEnvelope(_Strict):
    ok: bool
    data: Optional[dict] = None
    sentinel: Optional[SentinelBlock] = None
    shield: Optional[ShieldBlock] = None
    scoring_inputs: Optional[dict[str, Any]] = None
    card_type: Optional[CardType] = None
    card_id: str
    card_payload: Optional[dict] = None
    extra_cards: list[ExtraCard] = Field(default_factory=list)
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


class StepStatusFrame(_Strict):
    plan_id: str
    step_id: str
    status: Literal["pending", "ready", "signing", "broadcast", "confirmed", "failed", "skipped"]
    order: int
    tx_hash: Optional[str] = None
    error: Optional[str] = None
    event: Literal["step_status"] = "step_status"


class PlanCompleteFrame(_Strict):
    plan_id: str
    status: Literal["complete", "aborted", "failed", "expired"]
    payload: dict[str, Any] = Field(default_factory=dict)
    event: Literal["plan_complete"] = "plan_complete"


class PlanBlockedFrame(_Strict):
    plan_id: str
    reasons: list[str]
    severity: Literal["critical"] = "critical"
    event: Literal["plan_blocked"] = "plan_blocked"


class FinalFrame(_Strict):
    content: str
    card_ids: list[str]
    elapsed_ms: int
    steps: int


class DoneFrame(_Strict):
    pass


SSEFrame = Union[
    ThoughtFrame,
    ToolFrame,
    ObservationFrame,
    CardFrame,
    StepStatusFrame,
    PlanCompleteFrame,
    PlanBlockedFrame,
    FinalFrame,
    DoneFrame,
]
