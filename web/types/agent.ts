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

export type CardType =
  | "allocation" | "sentinel_matrix" | "execution_plan"
  | "swap_quote" | "pool" | "token" | "position"
  | "plan" | "execution_plan_v2" | "balance" | "bridge" | "stake" | "market_overview" | "pair_list"
  | "sentinel";

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
export interface SentinelBreakdownCardFrame { card_id: string; card_type: "sentinel"; payload: SentinelBlock; }

export type AgentCard =
  | AllocationCard | SentinelMatrixCard | ExecutionPlanCard | SwapQuoteCard | PoolCard | TokenCard | PositionCard
  | PlanCard | ExecutionPlanV2Card | BalanceCard | BridgeCard | StakeCard | MarketOverviewCard | PairListCard
  | SentinelBreakdownCardFrame;

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
