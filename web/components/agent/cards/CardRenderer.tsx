"use client";
import type {
  CardFrame,
  TokenPayload,
  SwapQuotePayload,
  BalancePayload,
  PoolPayload,
  StakePayload,
  MarketOverviewPayload,
  AllocationPayload,
  SentinelMatrixPayload,
  ExecutionPlanPayload,
  ExecutionPlanV2Payload,
  ExecutionPlanV3Payload,
  PlanPayload,
  PositionPayload,
  BridgePayload,
  PairListPayload,
  DefiOpportunitiesPayload,
  SentinelBlock,
} from "@/types/agent";
import { TrendingUp, TrendingDown, ExternalLink } from "lucide-react";
import { AllocationCard as DemoAllocationCard } from "./AllocationCard";
import { SentinelMatrixCard as DemoSentinelMatrixCard } from "./SentinelMatrixCard";
import { ExecutionPlanCard as DemoExecutionPlanCard } from "./ExecutionPlanCard";
import { DefiOpportunitiesCard } from "./DefiOpportunitiesCard";
import { ExecutionPlanV3Card } from "./ExecutionPlanV3Card";
import { SentinelBadge } from "./SentinelBadge";
import { ShieldBadge } from "./ShieldBadge";
import { SentinelBreakdownCard } from "./SentinelBreakdownCard";
import { SentinelTokenReportCard } from "./sentinel/SentinelTokenReportCard";
import { SentinelPoolReportCard } from "./sentinel/SentinelPoolReportCard";
import { SentinelWhaleFeedCard } from "./sentinel/SentinelWhaleFeedCard";
import { SentinelSmartMoneyHubCard } from "./sentinel/SentinelSmartMoneyHubCard";
import { SentinelShieldReportCard } from "./sentinel/SentinelShieldReportCard";
import { SentinelEntityCard } from "./sentinel/SentinelEntityCard";
import type {
  SentinelTokenReportPayload, SentinelPoolReportPayload, SentinelWhaleFeedPayload,
  SentinelSmartMoneyHubPayload, SentinelShieldReportPayload, SentinelEntityCardPayload,
} from "@/types/agent";

interface Props {
  card: CardFrame;
  onStartSigning?: (payload: ExecutionPlanPayload) => void;
  onRerunAllocation?: () => void;
  onSignStep?: (planId: string, stepId: string) => void;
}

/* ── Sentinel / Shield Helpers ────────────────────────────────────────── */

function ScoringBar({ sentinel }: { sentinel?: SentinelBlock | null }) {
  if (!sentinel) return null;
  const metrics = [
    { label: "Safety", value: sentinel.safety || 0 },
    { label: "Durability", value: sentinel.durability || 0 },
    { label: "Exit", value: sentinel.exit || 0 },
    { label: "Confidence", value: sentinel.confidence || 0 },
  ];
  
  return (
    <div className="grid grid-cols-2 gap-2 mt-2">
      {metrics.map((m) => (
        <div key={m.label} className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-slate-400">{m.label}</span>
            <span className="text-slate-300">{m.value.toFixed(0)}</span>
          </div>
          <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div 
              className={`h-full rounded-full transition-all ${
                m.value >= 80 ? "bg-emerald-500" :
                m.value >= 60 ? "bg-yellow-500" :
                m.value >= 40 ? "bg-orange-500" :
                "bg-red-500"
              }`}
              style={{ width: `${m.value}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function RiskFlags({ flags }: { flags?: string[] }) {
  if (!flags || flags.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-2">
      {flags.map((flag) => (
        <span key={flag} className="text-xs px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">
          {flag}
        </span>
      ))}
    </div>
  );
}

/* ── Helper ─────────────────────────────────────────────────────────── */

function changeBadge(pct: number) {
  const positive = pct >= 0;
  const Icon = positive ? TrendingUp : TrendingDown;
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-md ${
        positive
          ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20"
          : "bg-red-500/15 text-red-400 border border-red-500/20"
      }`}
    >
      <Icon className="h-3 w-3" />
      {positive ? "+" : ""}
      {pct.toFixed(2)}%
    </span>
  );
}

function cardShell(
  title: string,
  children: React.ReactNode,
  extra?: React.ReactNode,
  scoring?: React.ReactNode,
) {
  return (
    <div className="rounded-xl border border-slate-700/80 bg-slate-800/60 backdrop-blur-sm overflow-hidden shadow-lg">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/60 bg-slate-800/80">
        <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          {title}
        </span>
        {extra}
      </div>
      <div className="p-4 space-y-3">
        {children}
        {scoring}
      </div>
    </div>
  );
}

/* ── Token Card ─────────────────────────────────────────────────────── */

function TokenCard({ payload }: { payload: TokenPayload }) {
  const extra = (
    <div className="flex items-center gap-2">
      {payload.sentinel && <SentinelBadge sentinel={payload.sentinel} />}
      {payload.shield && <ShieldBadge shield={payload.shield} />}
    </div>
  );

  return cardShell(
    `${payload.symbol} Price`,
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold text-white">
            ${payload.price_usd}
          </span>
          {changeBadge(payload.change_24h_pct)}
        </div>
      </div>
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span>{payload.chain}</span>
        <span className="font-mono text-slate-500">{payload.address}</span>
      </div>
      {payload.sentinel && <ScoringBar sentinel={payload.sentinel} />}
    </>,
    extra,
  );
}

/* ── Swap Quote Card ───────────────────────────────────────────────── */

function SwapQuoteCard({ payload }: { payload: SwapQuotePayload }) {
  const payLabel = (payload.pay?.symbol as string) ?? (payload.pay?.token as string) ?? (payload.pay?.address as string) ?? "?";
  const payAmt = (payload.pay?.amount as string) ?? (payload.pay?.amount_in as string) ?? "?";
  const recvLabel = (payload.receive?.symbol as string) ?? (payload.receive?.token as string) ?? (payload.receive?.address as string) ?? "?";
  const recvAmt = (payload.receive?.amount as string) ?? (payload.receive?.amount_out as string) ?? "?";

  const extra = (
    <div className="flex items-center gap-2">
      {payload.sentinel && <SentinelBadge sentinel={payload.sentinel} />}
      {payload.shield && <ShieldBadge shield={payload.shield} />}
    </div>
  );

  return cardShell(
    "Swap Quote",
    <>
      <div className="flex items-center justify-between bg-slate-900/50 rounded-lg p-3">
        <div className="text-center">
          <div className="text-lg font-bold text-white">{payAmt}</div>
          <div className="text-xs text-slate-400">{payLabel}</div>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-px w-8 bg-slate-600" />
          <ExternalLink className="h-4 w-4 text-slate-500" />
          <div className="h-px w-8 bg-slate-600" />
        </div>
        <div className="text-center">
          <div className="text-lg font-bold text-emerald-400">{recvAmt}</div>
          <div className="text-xs text-slate-400">{recvLabel}</div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex justify-between px-2 py-1.5 rounded bg-slate-700/30">
          <span className="text-slate-400">Rate</span>
          <span className="text-slate-200 font-medium">{payload.rate}</span>
        </div>
        <div className="flex justify-between px-2 py-1.5 rounded bg-slate-700/30">
          <span className="text-slate-400">Impact</span>
          <span className={payload.price_impact_pct > 1 ? "text-red-400 font-medium" : "text-slate-200 font-medium"}>
            {payload.price_impact_pct}%
          </span>
        </div>
        {payload.router && (
          <div className="flex justify-between px-2 py-1.5 rounded bg-slate-700/30 col-span-2">
            <span className="text-slate-400">Route</span>
            <span className="text-slate-200 font-medium">{payload.router}</span>
          </div>
        )}
        {payload.priority_fee_usd && (
          <div className="flex justify-between px-2 py-1.5 rounded bg-slate-700/30 col-span-2">
            <span className="text-slate-400">Priority Fee</span>
            <span className="text-slate-200 font-medium">${payload.priority_fee_usd}</span>
          </div>
        )}
      </div>
      {payload.sentinel && <ScoringBar sentinel={payload.sentinel} />}
    </>,
    extra,
  );
}

/* ── Balance Card ──────────────────────────────────────────────────── */

function BalanceCard({ payload }: { payload: BalancePayload }) {
  const chains = Object.entries(payload.by_chain ?? {});
  return cardShell(
    "Portfolio Balance",
    <>
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-400">Total Value</span>
        <span className="text-2xl font-bold text-white">${payload.total_usd}</span>
      </div>
      {chains.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {chains.map(([chain, val]) => (
            <div
              key={chain}
              className="flex items-center justify-between rounded-lg bg-slate-700/30 px-3 py-2"
            >
              <span className="text-xs text-slate-400">{chain}</span>
              <span className="text-sm font-medium text-slate-200">${val}</span>
            </div>
          ))}
        </div>
      )}
      <div className="text-xs text-slate-500 font-mono truncate">
        {payload.wallet}
      </div>
    </>,
  );
}

/* ── Pool Card ─────────────────────────────────────────────────────── */

function PoolCard({ payload }: { payload: PoolPayload }) {
  const extra = (
    <div className="flex items-center gap-2">
      {payload.sentinel && <SentinelBadge sentinel={payload.sentinel} />}
      {payload.shield && <ShieldBadge shield={payload.shield} />}
    </div>
  );

  return cardShell(
    `${payload.protocol} Pool`,
    <>
      <div className="flex items-center justify-between">
        <span className="text-base text-white font-semibold">{payload.asset}</span>
        <span className="text-xs text-slate-400 px-2 py-1 rounded bg-slate-700/30">{payload.chain}</span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex justify-between px-2 py-1.5 rounded bg-slate-700/30">
          <span className="text-slate-400">APY</span>
          <span className="text-emerald-400 font-semibold">{payload.apy}</span>
        </div>
        <div className="flex justify-between px-2 py-1.5 rounded bg-slate-700/30">
          <span className="text-slate-400">TVL</span>
          <span className="text-slate-200 font-medium">{payload.tvl}</span>
        </div>
      </div>
      {payload.sentinel && <ScoringBar sentinel={payload.sentinel} />}
    </>,
    extra,
  );
}

/* ── Stake Card ────────────────────────────────────────────────────── */

function StakeCard({ payload }: { payload: StakePayload }) {
  const extra = (
    <div className="flex items-center gap-2">
      {payload.sentinel && <SentinelBadge sentinel={payload.sentinel} />}
      {payload.shield && <ShieldBadge shield={payload.shield} />}
    </div>
  );

  return cardShell(
    `${payload.protocol} Staking`,
    <>
      <div className="flex items-center justify-between">
        <span className="text-base text-white font-semibold">{payload.asset}</span>
        <span className="text-2xl font-bold text-emerald-400">{payload.apy}</span>
      </div>
      {payload.unbond_days && (
        <div className="text-xs text-slate-400">
          Unbonding period: <span className="text-slate-200">{payload.unbond_days} days</span>
        </div>
      )}
      {payload.sentinel && <ScoringBar sentinel={payload.sentinel} />}
    </>,
    extra,
  );
}

/* ── Market Overview Card ──────────────────────────────────────────── */

function MarketOverviewCard({ payload }: { payload: MarketOverviewPayload }) {
  const protocols = payload.protocols || [];
  
  return cardShell(
    "DeFi Market Overview",
    <>
      <div className="space-y-2">
        {protocols.slice(0, 5).map((p, i) => {
          const protocol = p as Record<string, unknown>;
          const tvl = protocol.tvl as number || 0;
          const change = protocol.change_1d as number || 0;
          const name = protocol.name as string || "Unknown";
          const category = protocol.category as string || "DeFi";
          
          return (
            <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-700/30">
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold text-slate-500 w-4">{i + 1}</span>
                <div>
                  <div className="text-sm font-medium text-white">{name}</div>
                  <div className="text-xs text-slate-400">{category}</div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm font-medium text-white">${tvl.toLocaleString()}</div>
                {change !== 0 && (
                  <div className={`text-xs ${change > 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {change > 0 ? "+" : ""}{change.toFixed(2)}%
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>,
  );
}

/* ── Plan Card ─────────────────────────────────────────────────────── */

function PlanCard({ payload }: { payload: PlanPayload }) {
  const steps = payload.steps || [];
  
  return cardShell(
    "Execution Plan",
    <>
      <div className="space-y-2">
        {steps.map((step) => (
          <div key={step.step} className="flex items-start gap-3 p-3 rounded-lg bg-slate-700/30">
            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center text-xs font-bold">
              {step.step}
            </div>
            <div className="flex-1">
              <div className="text-sm font-medium text-white">{step.action}</div>
              <div className="text-xs text-slate-400 mt-0.5">{step.detail}</div>
            </div>
          </div>
        ))}
      </div>
      {payload.requires_signature && (
        <div className="text-xs text-yellow-400 bg-yellow-500/10 border border-yellow-500/20 rounded-lg px-3 py-2">
          This plan requires wallet signature to execute.
        </div>
      )}
    </>,
  );
}

/* ── Position Card ─────────────────────────────────────────────────── */

function PositionCard({ payload }: { payload: PositionPayload }) {
  const rows = payload.rows || [];
  
  return cardShell(
    "Positions",
    <>
      <div className="text-xs text-slate-500 font-mono truncate mb-2">{payload.wallet}</div>
      <div className="space-y-2">
                {rows.map((row, i) => {
          const r = row as Record<string, unknown>;
          return (
            <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-700/30">
              <div className="text-sm text-white">{(r.asset || r.symbol || "Unknown") as string}</div>
              <div className="text-sm font-medium text-slate-200">{(r.balance || r.amount || "0") as string}</div>
            </div>
          );
        })}
      </div>
    </>,
  );
}

/* ── Bridge Card ───────────────────────────────────────────────────── */

function BridgeCard({ payload }: { payload: BridgePayload }) {
  const extra = (
    <div className="flex items-center gap-2">
      {payload.sentinel && <SentinelBadge sentinel={payload.sentinel} />}
      {payload.shield && <ShieldBadge shield={payload.shield} />}
    </div>
  );

  return cardShell(
    "Bridge",
    <>
      <div className="flex items-center justify-between bg-slate-900/50 rounded-lg p-3">
        <div className="text-center">
          <div className="text-xs text-slate-400">From</div>
          <div className="text-sm font-semibold text-white">{payload.source_chain}</div>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-px w-8 bg-slate-600" />
          <ExternalLink className="h-4 w-4 text-slate-500" />
          <div className="h-px w-8 bg-slate-600" />
        </div>
        <div className="text-center">
          <div className="text-xs text-slate-400">To</div>
          <div className="text-sm font-semibold text-white">{payload.target_chain}</div>
        </div>
      </div>
      {payload.estimated_seconds && (
        <div className="text-xs text-slate-400">
          Estimated time: <span className="text-slate-200">{payload.estimated_seconds}s</span>
        </div>
      )}
    </>,
    extra,
  );
}

/* ── Pair List Card ────────────────────────────────────────────────── */

function PairListCard({ payload }: { payload: PairListPayload }) {
  const pairs = payload.pairs || [];
  
  return cardShell(
    `DEX Pairs - "${payload.query}"`,
    <>
      <div className="space-y-2">
                {pairs.slice(0, 5).map((pair, i) => {
          const p = pair as Record<string, unknown>;
          return (
            <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-700/30">
              <div>
                <div className="text-sm font-medium text-white">{(p.symbol || p.pair || "Unknown") as string}</div>
                <div className="text-xs text-slate-400">{(p.dex || "Unknown DEX") as string} on {(p.chain || "Unknown") as string}</div>
              </div>
              <div className="text-right">
                {p.priceUsd ? <div className="text-sm text-white">${p.priceUsd as string}</div> : null}
                {p.volume24h ? <div className="text-xs text-slate-400">Vol: ${p.volume24h as string}</div> : null}
              </div>
            </div>
          );
        })}
      </div>
    </>,
  );
}

function ExecutionPlanV2Card({ payload }: { payload: ExecutionPlanV2Payload }) {
  const extra = (
    <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-400">
      <span>{payload.requires_signature_count} signatures</span>
      <span>${payload.total_gas_usd.toFixed(2)} gas</span>
    </div>
  );

  return (
    <div data-testid="execution-plan-v2-card">
      {cardShell(
        "Execution Plan",
        <>
          <div>
            <div className="text-base font-semibold text-white">{payload.title}</div>
            <div className="mt-1 text-xs text-slate-400">
              {payload.total_steps} steps · ~{payload.total_duration_estimate_s}s estimate · {payload.risk_gate.replace("_", " ")}
            </div>
          </div>
          {payload.requires_double_confirm ? (
            <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-xs text-yellow-200">
              Double confirmation required before signing because this plan includes cross-chain or higher-risk execution.
            </div>
          ) : null}
          <div className="space-y-2">
            {payload.steps.map((step) => (
              <div
                key={step.step_id}
                data-testid="execution-plan-v2-row"
                className="flex items-center justify-between rounded-lg bg-slate-700/30 px-3 py-2"
              >
                <div>
                  <div className="text-sm font-medium text-white">
                    {step.order}. {step.action.replace("_", " ")}
                  </div>
                  <div className="text-xs text-slate-400">Status: {step.status}</div>
                </div>
                <div className="text-right text-xs text-slate-400">
                  {step.estimated_gas_usd != null ? <div>${step.estimated_gas_usd.toFixed(2)} gas</div> : null}
                  {step.estimated_duration_s != null ? <div>~{step.estimated_duration_s}s</div> : null}
                </div>
              </div>
            ))}
          </div>
          {payload.risk_warnings.length ? (
            <div className="space-y-1 text-xs text-yellow-300">
              {payload.risk_warnings.map((warning) => (
                <div key={warning}>{warning}</div>
              ))}
            </div>
          ) : null}
        </>,
        extra,
      )}
    </div>
  );
}

/* ── Fallback ─────────────────────────────────────────────────────────── */

function FallbackCard({ card }: { card: CardFrame }) {
  return cardShell(
    card.card_type,
    <pre className="text-xs text-slate-300 overflow-auto max-h-48 whitespace-pre-wrap">
      {JSON.stringify(card.payload, null, 2)}
    </pre>,
  );
}

/* ── Main renderer ────────────────────────────────────────────────────── */

export function CardRenderer({ card, onStartSigning, onRerunAllocation, onSignStep }: Props) {
  const { card_type, payload } = card;

  switch (card_type) {
    case "sentinel_token_report":
      return <SentinelTokenReportCard payload={payload as unknown as SentinelTokenReportPayload} />;
    case "sentinel_pool_report":
      return <SentinelPoolReportCard payload={payload as unknown as SentinelPoolReportPayload} />;
    case "sentinel_whale_feed":
      return <SentinelWhaleFeedCard payload={payload as unknown as SentinelWhaleFeedPayload} />;
    case "sentinel_smart_money_hub":
      return <SentinelSmartMoneyHubCard payload={payload as unknown as SentinelSmartMoneyHubPayload} />;
    case "sentinel_shield_report":
      return <SentinelShieldReportCard payload={payload as unknown as SentinelShieldReportPayload} />;
    case "sentinel_entity_card":
      return <SentinelEntityCard payload={payload as unknown as SentinelEntityCardPayload} />;
    case "defi_opportunities":
      return <DefiOpportunitiesCard payload={payload as unknown as DefiOpportunitiesPayload} />;
    case "execution_plan_v3":
      return <ExecutionPlanV3Card payload={payload as unknown as ExecutionPlanV3Payload} onSignStep={onSignStep} />;
    case "token":
      return <TokenCard payload={payload as unknown as TokenPayload} />;
    case "swap_quote":
      return <SwapQuoteCard payload={payload as unknown as SwapQuotePayload} />;
    case "balance":
      return <BalanceCard payload={payload as unknown as BalancePayload} />;
    case "pool":
      return <PoolCard payload={payload as unknown as PoolPayload} />;
    case "stake":
      return <StakeCard payload={payload as unknown as StakePayload} />;
    case "market_overview":
      return <MarketOverviewCard payload={payload as unknown as MarketOverviewPayload} />;
    case "allocation":
      return <DemoAllocationCard payload={payload as unknown as AllocationPayload} />;
    case "sentinel_matrix":
      return <DemoSentinelMatrixCard payload={payload as unknown as SentinelMatrixPayload} />;
    case "execution_plan":
      return <DemoExecutionPlanCard payload={payload as unknown as ExecutionPlanPayload} onStartSigning={onStartSigning} onRerunAllocation={onRerunAllocation} />;
    case "execution_plan_v2":
      return <ExecutionPlanV2Card payload={payload as unknown as ExecutionPlanV2Payload} />;
    case "plan":
      return <PlanCard payload={payload as unknown as PlanPayload} />;
    case "position":
      return <PositionCard payload={payload as unknown as PositionPayload} />;
    case "bridge":
      return <BridgeCard payload={payload as unknown as BridgePayload} />;
    case "pair_list":
      return <PairListCard payload={payload as unknown as PairListPayload} />;
    case "sentinel":
      return <SentinelBreakdownCard sentinel={payload as unknown as SentinelBlock} />;
    default:
      return <FallbackCard card={card} />;
  }
}
