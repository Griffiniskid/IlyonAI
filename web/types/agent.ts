// Auto-generated from src/api/schemas/agent.py — DO NOT EDIT BY HAND.
// Run `python scripts/gen_agent_types.py` to regenerate.

export interface SentinelBlock {
  sentinel: number;
  safety: number;
  durability: number;
  exit: number;
  confidence: number;
  risk_level: "HIGH" | "MEDIUM" | "LOW";
  strategy_fit: "conservative" | "balanced" | "aggressive";
  flags: string[];
}

export interface ShieldBlock {
  verdict: "SAFE" | "CAUTION" | "RISKY" | "DANGEROUS" | "SCAM";
  grade: "A+" | "A" | "B" | "C" | "D" | "F";
  reasons: string[];
}

export type ChainTone = "eth" | "sol" | "arb" | "mainnet" | "base" | "polygon" | "bsc" | "op" | "avax";
export type RiskLevelLower = "low" | "medium" | "high";
export type StrategyFit = "conservative" | "balanced" | "aggressive";
export type WalletKind = "MetaMask" | "Phantom" | "WalletConnect";

export interface AllocationPosition {
  rank: number;
  protocol: string;
  asset: string;
  chain: ChainTone;
  apy: string;
  sentinel: number;
  risk: RiskLevelLower;
  fit: StrategyFit;
  weight: number;
  usd: string;
  tvl: string;
  router: string;
  safety: number;
  durability: number;
  exit: number;
  confidence: number;
  flags: string[];
}

export interface AllocationPayload {
  positions: AllocationPosition[];
  total_usd: string;
  blended_apy: string;
  chains: number;
  weighted_sentinel: number;
  risk_mix: Record<string, number>;
  combined_tvl: string;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface SentinelMatrixPayload {
  positions: AllocationPosition[];
  low_count: number;
  medium_count: number;
  high_count: number;
  weighted_sentinel: number;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface ExecutionStep {
  index: number;
  verb: string;
  amount: string;
  asset: string;
  target: string;
  chain: ChainTone;
  router: string;
  wallet: WalletKind;
  gas: string;
}

export interface ExecutionPlanPayload {
  steps: ExecutionStep[];
  total_gas: string;
  slippage_cap: string;
  wallets: string;
  tx_count: number;
  requires_signature: boolean;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface SwapQuotePayload {
  pay: Record<string, unknown>;
  receive: Record<string, unknown>;
  rate: string;
  router: string;
  price_impact_pct: number;
  priority_fee_usd?: string | null;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface PoolPayload {
  protocol: string;
  chain: string;
  asset: string;
  apy: string;
  tvl: string;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface TokenPayload {
  symbol: string;
  address: string;
  chain: string;
  price_usd: string;
  change_24h_pct: number;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface PositionPayload {
  wallet: string;
  rows: Array<Record<string, unknown>>;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface PlanStep {
  step: number;
  action: string;
  detail: string;
}

export interface PlanPayload {
  steps: PlanStep[];
  requires_signature: boolean;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface PlanStepV2 {
  step_id: string;
  order: number;
  action: "swap" | "bridge" | "stake" | "unstake" | "deposit_lp" | "withdraw_lp" | "transfer" | "approve" | "wait_receipt" | "get_balance";
  params: Record<string, unknown>;
  depends_on: string[];
  resolves_from: Record<string, string>;
  sentinel?: SentinelBlock | null;
  shield_flags: string[];
  estimated_gas_usd?: number | null;
  estimated_duration_s?: number | null;
  status: "pending" | "ready" | "signing" | "broadcast" | "confirmed" | "failed" | "skipped";
  tx_hash?: string | null;
  receipt?: Record<string, unknown> | null;
  error?: string | null;
}

export interface ExecutionPlanV2Payload {
  plan_id: string;
  title: string;
  steps: PlanStepV2[];
  total_steps: number;
  total_gas_usd: number;
  total_duration_estimate_s: number;
  blended_sentinel?: number | null;
  requires_signature_count: number;
  risk_warnings: string[];
  risk_gate: "clear" | "soft_warn" | "hard_block";
  requires_double_confirm: boolean;
  chains_touched: string[];
  user_assets_required: Record<string, string>;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface BalancePayload {
  wallet: string;
  total_usd: string;
  by_chain: Record<string, string>;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface BridgePayload {
  source_chain: string;
  target_chain: string;
  pay: Record<string, unknown>;
  receive: Record<string, unknown>;
  estimated_seconds: number;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface StakePayload {
  protocol: string;
  asset: string;
  apy: string;
  unbond_days?: number | null;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface MarketOverviewPayload {
  protocols: Array<Record<string, unknown>>;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface PairListPayload {
  query: string;
  pairs: Array<Record<string, unknown>>;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface DefiOpportunityLink {
  label: string;
  url: string;
}

export interface DefiOpportunityItem {
  protocol: string;
  symbol?: string | null;
  chain?: string | null;
  product_type?: string | null;
  apy?: number | null;
  apy_base?: number | null;
  apy_reward?: number | null;
  tvl_usd?: number | null;
  volume_24h_usd?: number | null;
  risk_level?: string | null;
  executable?: boolean | null;
  adapter_id?: string | null;
  unsupported_reason?: string | null;
  links: DefiOpportunityLink[];
  pool_id?: string | null;
}

export interface DefiOpportunitiesPayload {
  objective?: string | null;
  target_apy?: number | null;
  apy_band?: Array<number | null> | null;
  risk_levels: string[];
  chains: string[];
  execution_requested: boolean;
  items: DefiOpportunityItem[];
  excluded_count: number;
  blockers: Array<Record<string, unknown>>;
}

export interface ExecutionPlanV3StepTransaction {
  chain_kind: "evm" | "solana";
  chain_id?: number | null;
  to?: string | null;
  data?: string | null;
  value?: string | null;
  gas?: string | null;
  serialized?: string | null;
  spender?: string | null;
}

export type ExecutionPlanV3StepStatus =
  | "blocked" | "pending" | "ready" | "signing" | "submitted" | "confirmed" | "failed" | "skipped";

export interface ExecutionPlanV3Step {
  step_id: string;
  index: number;
  action:
    | "approve" | "swap" | "bridge" | "deposit_lp" | "supply" | "stake"
    | "wait_receipt" | "verify_balance" | "claim_rewards" | "compound_rewards" | "withdraw";
  title: string;
  description: string;
  chain: string;
  wallet: WalletKind;
  protocol: string;
  asset_in?: string | null;
  asset_out?: string | null;
  amount_in?: string | null;
  amount_out?: string | null;
  slippage_bps?: number | null;
  gas_estimate_usd?: number | null;
  duration_estimate_s?: number | null;
  depends_on: string[];
  status: ExecutionPlanV3StepStatus;
  blocker_codes: string[];
  transaction?: ExecutionPlanV3StepTransaction | null;
  receipt?: Record<string, unknown> | null;
  risk_warnings: string[];
}

export interface ExecutionPlanV3Blocker {
  code: string;
  severity: "info" | "warning" | "blocker";
  title: string;
  detail: string;
  affected_step_ids: string[];
  recoverable: boolean;
  cta?: string | null;
}

export interface ExecutionPlanV3Totals {
  estimated_gas_usd: number;
  estimated_duration_s: number;
  signatures_required: number;
  chains_touched: string[];
  assets_required: Record<string, string>;
}

export interface ExecutionPlanV3Payload {
  plan_id: string;
  title: string;
  summary: string;
  status: "draft" | "blocked" | "ready" | "executing" | "complete" | "failed" | "aborted";
  risk_gate: "clear" | "soft_warn" | "hard_block";
  requires_double_confirm: boolean;
  blockers: ExecutionPlanV3Blocker[];
  steps: ExecutionPlanV3Step[];
  totals: ExecutionPlanV3Totals;
  research_thesis?: string | null;
  strategy_id?: string | null;
}

export type CardType =
  | "allocation" | "sentinel_matrix" | "execution_plan"
  | "swap_quote" | "pool" | "token" | "position"
  | "plan" | "execution_plan_v2" | "execution_plan_v3" | "balance" | "bridge" | "stake" | "market_overview" | "pair_list"
  | "defi_opportunities"
  | "sentinel"
  | "sentinel_token_report" | "sentinel_pool_report" | "sentinel_whale_feed"
  | "sentinel_smart_money_hub" | "sentinel_shield_report" | "sentinel_entity_card";

export interface SentinelTokenReportPayload {
  address: string;
  symbol?: string | null;
  chain?: string | null;
  score: number;
  grade?: string | null;
  verdict?: string | null;
  price_usd?: number | null;
  market_cap_usd?: number | null;
  liquidity_usd?: number | null;
  volume_24h_usd?: number | null;
  rug_probability_pct?: number | null;
  security: {
    mint_authority_enabled?: boolean | null;
    freeze_authority_enabled?: boolean | null;
    liquidity_locked?: boolean | null;
    lp_lock_percent?: number | null;
    honeypot_status?: string | null;
    is_honeypot?: boolean | null;
    is_renounced?: boolean | null;
    rugcheck_score?: number | null;
  };
  holders?: {
    total?: number | null;
    top10_pct?: number | null;
    top_holder_pct?: number | null;
  } | null;
  ai?: {
    red_flags?: string[];
    green_flags?: string[];
    recommendation?: string | null;
  } | null;
  recommendation?: string | null;
}

export interface SentinelPoolReportPayload {
  pool_id?: string | null;
  protocol?: string | null;
  symbol?: string | null;
  chain?: string | null;
  apy?: number | null;
  apy_base?: number | null;
  apy_reward?: number | null;
  tvl_usd?: number | null;
  volume_24h_usd?: number | null;
  il_risk?: string | null;
  predicted_class?: string | null;
  underlying_tokens?: string[];
  links?: { label: string; url: string }[];
}

export interface SentinelWhaleEvent {
  ts?: string | number | null;
  action?: string | null;
  symbol?: string | null;
  chain?: string | null;
  usd_value?: number | null;
  wallet?: string | null;
  tx_hash?: string | null;
}
export interface SentinelWhaleFeedPayload {
  chain?: string | null;
  hours: number;
  items: SentinelWhaleEvent[];
}

export interface SentinelSmartMoneyHubPayload {
  chain: string;
  top_wallets?: { address: string; usd_value?: number; pnl_24h?: number; tag?: string }[];
  recent_accumulations?: { symbol: string; usd_value?: number; chain?: string; ts?: string | number }[];
  trending_tokens?: { symbol: string; usd_value?: number; price_change?: number }[];
  conviction?: { symbol: string; score?: number; reason?: string }[];
  flow_direction?: string;
}

export interface SentinelShieldFinding {
  spender?: string;
  contract?: string;
  token?: string;
  symbol?: string;
  severity?: string;
  risk?: string;
}
export interface SentinelShieldReportPayload {
  address: string;
  chain?: string | null;
  verdict?: string | null;
  risk_score?: number | null;
  scanned_at?: string | null;
  summary?: {
    total_approvals?: number;
    high_risk_count?: number;
    medium_risk_count?: number;
    low_risk_count?: number;
  };
  approvals?: SentinelShieldFinding[];
  recommendation?: string | null;
}

export interface SentinelEntityCardPayload {
  query: string;
  name?: string | null;
  description?: string | null;
  tags?: string[];
  addresses?: string[];
  empty?: boolean;
  empty_reason?: string;
}

export interface AllocationCard { card_id: string; card_type: "allocation"; payload: AllocationPayload; }
export interface SentinelMatrixCard { card_id: string; card_type: "sentinel_matrix"; payload: SentinelMatrixPayload; }
export interface ExecutionPlanCard { card_id: string; card_type: "execution_plan"; payload: ExecutionPlanPayload; }
export interface SwapQuoteCard { card_id: string; card_type: "swap_quote"; payload: SwapQuotePayload; }
export interface PoolCard { card_id: string; card_type: "pool"; payload: PoolPayload; }
export interface TokenCard { card_id: string; card_type: "token"; payload: TokenPayload; }
export interface PositionCard { card_id: string; card_type: "position"; payload: PositionPayload; }
export interface PlanCard { card_id: string; card_type: "plan"; payload: PlanPayload; }
export interface ExecutionPlanV2Card { card_id: string; card_type: "execution_plan_v2"; payload: ExecutionPlanV2Payload; }
export interface BalanceCard { card_id: string; card_type: "balance"; payload: BalancePayload; }
export interface BridgeCard { card_id: string; card_type: "bridge"; payload: BridgePayload; }
export interface StakeCard { card_id: string; card_type: "stake"; payload: StakePayload; }
export interface MarketOverviewCard { card_id: string; card_type: "market_overview"; payload: MarketOverviewPayload; }
export interface PairListCard { card_id: string; card_type: "pair_list"; payload: PairListPayload; }
export interface DefiOpportunitiesCard { card_id: string; card_type: "defi_opportunities"; payload: DefiOpportunitiesPayload; }
export interface ExecutionPlanV3Card { card_id: string; card_type: "execution_plan_v3"; payload: ExecutionPlanV3Payload; }
export interface SentinelBreakdownCardFrame { card_id: string; card_type: "sentinel"; payload: SentinelBlock; }
export interface SentinelTokenReportCard { card_id: string; card_type: "sentinel_token_report"; payload: SentinelTokenReportPayload; }
export interface SentinelPoolReportCard { card_id: string; card_type: "sentinel_pool_report"; payload: SentinelPoolReportPayload; }
export interface SentinelWhaleFeedCard { card_id: string; card_type: "sentinel_whale_feed"; payload: SentinelWhaleFeedPayload; }
export interface SentinelSmartMoneyHubCard { card_id: string; card_type: "sentinel_smart_money_hub"; payload: SentinelSmartMoneyHubPayload; }
export interface SentinelShieldReportCard { card_id: string; card_type: "sentinel_shield_report"; payload: SentinelShieldReportPayload; }
export interface SentinelEntityCard { card_id: string; card_type: "sentinel_entity_card"; payload: SentinelEntityCardPayload; }

export type AgentCard =
  | AllocationCard | SentinelMatrixCard | ExecutionPlanCard | SwapQuoteCard | PoolCard | TokenCard | PositionCard
  | PlanCard | ExecutionPlanV2Card | BalanceCard | BridgeCard | StakeCard | MarketOverviewCard | PairListCard
  | DefiOpportunitiesCard | ExecutionPlanV3Card
  | SentinelBreakdownCardFrame
  | SentinelTokenReportCard | SentinelPoolReportCard | SentinelWhaleFeedCard
  | SentinelSmartMoneyHubCard | SentinelShieldReportCard | SentinelEntityCard;

export interface ToolError {
  code: string;
  message: string;
}

export interface ToolEnvelope {
  ok: boolean;
  data?: Record<string, unknown> | null;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
  card_type?: CardType | null;
  card_id: string;
  card_payload?: Record<string, unknown> | null;
  error?: ToolError | null;
}

export interface ThoughtFrame {
  kind: "thought";
  step_index: number;
  content: string;
}

export interface ToolFrame {
  kind: "tool";
  step_index: number;
  name: string;
  args: Record<string, unknown>;
}

export interface ObservationFrame {
  kind: "observation";
  step_index: number;
  name: string;
  ok: boolean;
  error?: ToolError | null;
}

export interface CardFrame {
  kind: "card";
  step_index: number;
  card_id: string;
  card_type: CardType;
  payload: Record<string, unknown>;
}

export interface StepStatusFrame {
  kind: "step_status";
  plan_id: string;
  step_id: string;
  status: "pending" | "ready" | "signing" | "broadcast" | "confirmed" | "failed" | "skipped";
  order: number;
  tx_hash?: string | null;
  error?: string | null;
  event?: "step_status";
}

export interface PlanCompleteFrame {
  kind: "plan_complete";
  plan_id: string;
  status: "complete" | "aborted" | "failed" | "expired";
  payload: Record<string, unknown>;
  event?: "plan_complete";
}

export interface FinalFrame {
  kind: "final";
  content: string;
  card_ids: string[];
  elapsed_ms: number;
  steps: number;
}

export interface DoneFrame {
  kind: "done";
}

export type SSEFrame =
  | ThoughtFrame | ToolFrame | ObservationFrame | CardFrame | StepStatusFrame | PlanCompleteFrame | FinalFrame | DoneFrame;
