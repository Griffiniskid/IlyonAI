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

export interface AllocationPosition {
  rank: number;
  protocol: string;
  asset: string;
  chain: string;
  apy: string;
  weight: number;
  usd: string;
  router: string;
  sentinel?: SentinelBlock | null;
  shield?: ShieldBlock | null;
}

export interface AllocationPayload {
  positions: AllocationPosition[];
  total_usd: string;
  weighted_sentinel: number;
  risk_mix: Record<string, number>;
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
  | "allocation" | "swap_quote" | "pool" | "token" | "position"
  | "plan" | "balance" | "bridge" | "stake" | "market_overview" | "pair_list";

export interface AllocationCard { card_id: string; card_type: "allocation"; payload: AllocationPayload; }
export interface SwapQuoteCard { card_id: string; card_type: "swap_quote"; payload: SwapQuotePayload; }
export interface PoolCard { card_id: string; card_type: "pool"; payload: PoolPayload; }
export interface TokenCard { card_id: string; card_type: "token"; payload: TokenPayload; }
export interface PositionCard { card_id: string; card_type: "position"; payload: PositionPayload; }
export interface PlanCard { card_id: string; card_type: "plan"; payload: PlanPayload; }
export interface BalanceCard { card_id: string; card_type: "balance"; payload: BalancePayload; }
export interface BridgeCard { card_id: string; card_type: "bridge"; payload: BridgePayload; }
export interface StakeCard { card_id: string; card_type: "stake"; payload: StakePayload; }
export interface MarketOverviewCard { card_id: string; card_type: "market_overview"; payload: MarketOverviewPayload; }
export interface PairListCard { card_id: string; card_type: "pair_list"; payload: PairListPayload; }

export type AgentCard =
  | AllocationCard | SwapQuoteCard | PoolCard | TokenCard | PositionCard
  | PlanCard | BalanceCard | BridgeCard | StakeCard | MarketOverviewCard | PairListCard;

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
  | ThoughtFrame | ToolFrame | ObservationFrame | CardFrame | FinalFrame | DoneFrame;
