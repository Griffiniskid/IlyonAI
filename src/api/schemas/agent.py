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


class DefiOpportunityLink(_Strict):
    label: str
    url: str


class DefiOpportunityItem(_Strict):
    protocol: str
    symbol: Optional[str] = None
    chain: Optional[str] = None
    product_type: Optional[str] = None
    apy: Optional[float] = None
    apy_base: Optional[float] = None
    apy_reward: Optional[float] = None
    tvl_usd: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    risk_level: Optional[str] = None
    executable: Optional[bool] = None
    adapter_id: Optional[str] = None
    unsupported_reason: Optional[str] = None
    links: list[DefiOpportunityLink] = Field(default_factory=list)
    pool_id: Optional[str] = None


class DefiOpportunitiesPayload(_Strict):
    objective: Optional[str] = None
    target_apy: Optional[float] = None
    apy_band: Optional[list[Optional[float]]] = None
    risk_levels: list[str] = Field(default_factory=list)
    chains: list[str] = Field(default_factory=list)
    execution_requested: bool = False
    items: list[DefiOpportunityItem] = Field(default_factory=list)
    excluded_count: int = 0
    blockers: list[dict] = Field(default_factory=list)


class DefiOpportunitiesCard(_CardBase):
    card_type: Literal["defi_opportunities"]
    payload: DefiOpportunitiesPayload


class ExecutionPlanV3StepTransaction(_Strict):
    chain_kind: Literal["evm", "solana"]
    chain_id: Optional[int] = None
    to: Optional[str] = None
    data: Optional[str] = None
    value: Optional[str] = None
    gas: Optional[str] = None
    serialized: Optional[str] = None
    spender: Optional[str] = None


class ExecutionPlanV3Step(_Strict):
    step_id: str
    index: int
    action: Literal[
        "approve", "swap", "bridge", "deposit_lp", "supply", "stake",
        "wait_receipt", "verify_balance", "claim_rewards", "compound_rewards",
        "withdraw",
    ]
    title: str
    description: str
    chain: str
    wallet: Literal["MetaMask", "Phantom", "WalletConnect"]
    protocol: str
    asset_in: Optional[str] = None
    asset_out: Optional[str] = None
    amount_in: Optional[str] = None
    amount_out: Optional[str] = None
    slippage_bps: Optional[int] = None
    gas_estimate_usd: Optional[float] = None
    duration_estimate_s: Optional[int] = None
    depends_on: list[str] = Field(default_factory=list)
    status: Literal["blocked", "pending", "ready", "signing", "submitted", "confirmed", "failed", "skipped"] = "pending"
    blocker_codes: list[str] = Field(default_factory=list)
    transaction: Optional[ExecutionPlanV3StepTransaction] = None
    receipt: Optional[dict] = None
    risk_warnings: list[str] = Field(default_factory=list)


class ExecutionPlanV3Blocker(_Strict):
    code: str
    severity: Literal["info", "warning", "blocker"]
    title: str
    detail: str
    affected_step_ids: list[str] = Field(default_factory=list)
    recoverable: bool = True
    cta: Optional[str] = None


class ExecutionPlanV3Totals(_Strict):
    estimated_gas_usd: float = 0.0
    estimated_duration_s: int = 0
    signatures_required: int = 0
    chains_touched: list[str] = Field(default_factory=list)
    assets_required: dict[str, str] = Field(default_factory=dict)


class ExecutionPlanV3Payload(_Strict):
    plan_id: str
    title: str
    summary: str
    status: Literal["draft", "blocked", "ready", "executing", "complete", "failed", "aborted"] = "draft"
    risk_gate: Literal["clear", "soft_warn", "hard_block"] = "clear"
    requires_double_confirm: bool = False
    blockers: list[ExecutionPlanV3Blocker] = Field(default_factory=list)
    steps: list[ExecutionPlanV3Step] = Field(default_factory=list)
    totals: ExecutionPlanV3Totals = Field(default_factory=ExecutionPlanV3Totals)
    research_thesis: Optional[str] = None
    strategy_id: Optional[str] = None


class ExecutionPlanV3Card(_CardBase):
    card_type: Literal["execution_plan_v3"]
    payload: ExecutionPlanV3Payload


_CardUnion = Annotated[
    Union[
        AllocationCard, SentinelMatrixCard, ExecutionPlanCard,
        SwapQuoteCard, PoolCard, TokenCard,
        PositionCard, PlanCard, ExecutionPlanV2Card, BalanceCard, BridgeCard,
        StakeCard, MarketOverviewCard, PairListCard,
        DefiOpportunitiesCard, ExecutionPlanV3Card,
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
    "execution_plan_v2", "execution_plan_v3", "balance", "bridge", "stake", "transfer",
    "market_overview", "pair_list", "lp", "preferences",
    "defi_opportunities",
    "text", "no_change",
    "sentinel_token_report", "sentinel_pool_report", "sentinel_whale_feed",
    "sentinel_smart_money_hub", "sentinel_shield_report", "sentinel_entity_card",
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
