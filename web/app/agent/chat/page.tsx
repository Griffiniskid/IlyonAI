import {
  Brain,
  ChevronDown,
  ChevronUp,
  MessagesSquare,
  Sparkles,
  ArrowUp,
  Layers,
  ListChecks,
  ShieldCheck,
  TrendingUp,
  Signal,
  Wallet,
  DollarSign,
  Gauge,
  Scale,
  RefreshCcw,
  AlertTriangle,
  Activity,
} from "lucide-react";

export const metadata = {
  title: "AI Agent Chat — Preview",
};

function PreviewBanner() {
  return (
    <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-2.5 text-sm">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-emerald-400" />
        <span className="text-foreground/90">
          Preview of the AI Agent Chat layout · Sentinel scoring layered in
        </span>
      </div>
      <span className="rounded-full bg-emerald-500/15 px-3 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300">
        Coming Soon
      </span>
    </div>
  );
}

function ReasoningAccordion({
  steps,
  time,
  expanded = false,
  lines,
}: {
  steps: number;
  time: string;
  expanded?: boolean;
  lines?: string[];
}) {
  return (
    <div className="my-2 ml-11 max-w-2xl">
      <div className="rounded-xl border border-purple-500/20 bg-purple-500/5 px-4 py-2.5 text-sm">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-purple-300">
            <Brain className="h-4 w-4" />
            <span>Agent Reasoning — {steps} steps</span>
          </div>
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-purple-400/70" />
          ) : (
            <ChevronDown className="h-4 w-4 text-purple-400/70" />
          )}
        </div>
        {expanded && lines && (
          <ol className="mt-3 space-y-1.5 border-t border-purple-500/15 pt-3 text-[12px] text-foreground/80">
            {lines.map((line, i) => (
              <li key={i} className="flex gap-2.5">
                <span className="shrink-0 font-mono text-purple-300/80">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="text-foreground/75">{line}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
      <div className="mt-1 ml-1 text-[11px] text-muted-foreground/70">{time}</div>
    </div>
  );
}

function AssistantBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-purple-500/15 text-purple-300">
        <span className="text-xs font-semibold">A</span>
      </div>
      <div className="max-w-2xl rounded-2xl rounded-tl-sm border border-white/10 bg-card/70 px-4 py-3 text-sm text-foreground/90 backdrop-blur">
        {children}
      </div>
    </div>
  );
}

function UserBubble({ children, time }: { children: React.ReactNode; time: string }) {
  return (
    <div className="flex items-start justify-end gap-3">
      <div className="flex flex-col items-end">
        <div className="max-w-xl rounded-2xl rounded-tr-sm border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-100">
          {children}
        </div>
        <span className="mt-1 mr-1 text-[11px] text-muted-foreground/70">{time}</span>
      </div>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-300">
        <span className="text-xs font-semibold">U</span>
      </div>
    </div>
  );
}

type ChainTone = "eth" | "sol" | "arb" | "mainnet";

const chainToneMap: Record<ChainTone, { label: string; tint: string }> = {
  eth: { label: "Ethereum", tint: "bg-blue-500/15 text-blue-300 border-blue-500/25" },
  sol: { label: "Solana", tint: "bg-violet-500/15 text-violet-300 border-violet-500/25" },
  arb: { label: "Arbitrum", tint: "bg-sky-500/15 text-sky-300 border-sky-500/25" },
  mainnet: {
    label: "Mainnet",
    tint: "bg-indigo-500/15 text-indigo-300 border-indigo-500/25",
  },
};

function ChainPill({ tone }: { tone: ChainTone }) {
  const c = chainToneMap[tone];
  return (
    <span className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${c.tint}`}>
      {c.label}
    </span>
  );
}

type RiskLevel = "low" | "medium" | "high";
type StrategyFit = "conservative" | "balanced" | "aggressive";

const riskToneMap: Record<RiskLevel, { pill: string; dot: string; label: string }> = {
  low: {
    pill: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    dot: "bg-emerald-400",
    label: "Low risk",
  },
  medium: {
    pill: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    dot: "bg-amber-400",
    label: "Medium risk",
  },
  high: {
    pill: "bg-red-500/15 text-red-300 border-red-500/30",
    dot: "bg-red-400",
    label: "High risk",
  },
};

const fitToneMap: Record<StrategyFit, string> = {
  conservative: "bg-emerald-500/10 text-emerald-300 border-emerald-500/25",
  balanced: "bg-sky-500/10 text-sky-300 border-sky-500/25",
  aggressive: "bg-amber-500/10 text-amber-300 border-amber-500/25",
};

function SentinelPill({ score, risk }: { score: number; risk: RiskLevel }) {
  const tone = riskToneMap[risk];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-[11px] font-semibold ${tone.pill}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} />
      <span className="font-mono">{score}</span>
    </span>
  );
}

function FitPill({ fit }: { fit: StrategyFit }) {
  return (
    <span className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium capitalize ${fitToneMap[fit]}`}>
      {fit}
    </span>
  );
}

type Position = {
  rank: number;
  protocol: string;
  asset: string;
  chain: ChainTone;
  apy: string;
  sentinel: number;
  risk: RiskLevel;
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
};

const allocation: Position[] = [
  {
    rank: 1,
    protocol: "Lido",
    asset: "stETH",
    chain: "eth",
    apy: "3.1%",
    sentinel: 94,
    risk: "low",
    fit: "conservative",
    weight: 35,
    usd: "$3,500",
    tvl: "$24.5B",
    router: "Enso",
    safety: 96,
    durability: 92,
    exit: 98,
    confidence: 95,
    flags: [],
  },
  {
    rank: 2,
    protocol: "Rocket Pool",
    asset: "rETH",
    chain: "eth",
    apy: "2.9%",
    sentinel: 91,
    risk: "low",
    fit: "conservative",
    weight: 20,
    usd: "$2,000",
    tvl: "$3.4B",
    router: "Enso",
    safety: 93,
    durability: 89,
    exit: 91,
    confidence: 92,
    flags: ["Node operator set"],
  },
  {
    rank: 3,
    protocol: "Jito",
    asset: "JitoSOL",
    chain: "sol",
    apy: "7.2%",
    sentinel: 88,
    risk: "low",
    fit: "balanced",
    weight: 20,
    usd: "$2,000",
    tvl: "$2.1B",
    router: "Jupiter",
    safety: 89,
    durability: 87,
    exit: 85,
    confidence: 90,
    flags: ["MEV rebate dependency"],
  },
  {
    rank: 4,
    protocol: "Aave v3",
    asset: "aArbUSDC",
    chain: "arb",
    apy: "4.8%",
    sentinel: 90,
    risk: "low",
    fit: "balanced",
    weight: 15,
    usd: "$1,500",
    tvl: "$890M",
    router: "Enso",
    safety: 95,
    durability: 85,
    exit: 96,
    confidence: 88,
    flags: [],
  },
  {
    rank: 5,
    protocol: "Pendle",
    asset: "PT-sUSDe",
    chain: "mainnet",
    apy: "18.2%",
    sentinel: 71,
    risk: "medium",
    fit: "aggressive",
    weight: 10,
    usd: "$1,000",
    tvl: "$320M",
    router: "Enso",
    safety: 68,
    durability: 62,
    exit: 72,
    confidence: 82,
    flags: ["Fixed maturity", "Ethena dependency"],
  },
];

function AllocationCard() {
  return (
    <div className="mt-3 ml-11 max-w-2xl rounded-2xl border border-purple-500/25 bg-card/70 p-4 backdrop-blur">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-purple-300">
          <Layers className="h-3.5 w-3.5" />
          <span>Allocation Proposal</span>
        </div>
        <span className="rounded-full border border-purple-500/30 bg-purple-500/5 px-2 py-0.5 text-[10px] font-medium text-purple-200/80">
          Sentinel × DefiLlama
        </span>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatTile icon={<DollarSign className="h-3 w-3" />} label="Deploy" value="$10,000" />
        <StatTile icon={<TrendingUp className="h-3 w-3" />} label="Blended APY" value="~5.6%" tone="emerald" />
        <StatTile icon={<Signal className="h-3 w-3" />} label="Chains" value="3" />
        <StatTile
          icon={<ShieldCheck className="h-3 w-3" />}
          label="Sentinel (weighted)"
          value="89 / 100"
          tone="emerald"
        />
      </div>

      <div className="space-y-1.5 rounded-lg border border-white/5 bg-background/40 p-2">
        {allocation.map((p) => (
          <PositionRow key={p.rank} position={p} />
        ))}
      </div>

      <div className="mt-4 flex items-center justify-between rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-4 py-3">
        <div className="flex flex-col">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Combined Position
          </span>
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
            5 protocols · $31.2B combined TVL · 4 Low · 1 Medium
          </span>
        </div>
        <div className="flex flex-col items-end">
          <span className="text-2xl font-bold text-emerald-400">~5.6% APY</span>
          <span className="text-[10px] text-muted-foreground/80">net of est. gas</span>
        </div>
      </div>
    </div>
  );
}

function StatTile({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: "emerald";
}) {
  return (
    <div className="rounded-lg border border-white/5 bg-background/50 px-3 py-2">
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground">
        <span className="text-purple-300/80">{icon}</span>
        <span>{label}</span>
      </div>
      <div className={`mt-0.5 text-sm font-semibold ${tone === "emerald" ? "text-emerald-300" : "text-foreground/90"}`}>
        {value}
      </div>
    </div>
  );
}

function PositionRow({ position }: { position: Position }) {
  const p = position;
  return (
    <div className="flex items-center justify-between gap-3 rounded-md px-2 py-2 hover:bg-white/[0.02]">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-purple-500/10 text-[11px] font-semibold text-purple-300">
          {p.rank}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-sm">
            <span className="font-semibold text-foreground/90">{p.protocol}</span>
            <span className="text-muted-foreground/70">·</span>
            <span className="font-mono text-foreground/80">{p.asset}</span>
          </div>
          <div className="mt-0.5 flex items-center gap-1.5">
            <ChainPill tone={p.chain} />
            <span className="text-[10px] text-muted-foreground/80">via {p.router}</span>
            <span className="text-muted-foreground/50">·</span>
            <span className="text-[10px] text-muted-foreground/80">TVL {p.tvl}</span>
          </div>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <div className="flex flex-col items-end">
          <span className="font-mono text-sm text-emerald-300">{p.apy}</span>
          <span className="text-[10px] text-muted-foreground/70">APY</span>
        </div>
        <SentinelPill score={p.sentinel} risk={p.risk} />
        <div className="flex w-20 flex-col items-end">
          <span className="font-mono text-sm text-foreground/90">{p.usd}</span>
          <span className="text-[10px] text-muted-foreground/70">{p.weight}%</span>
        </div>
      </div>
    </div>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const tone =
    value >= 85
      ? "bg-emerald-400"
      : value >= 70
      ? "bg-sky-400"
      : value >= 50
      ? "bg-amber-400"
      : "bg-red-400";
  return (
    <div className="rounded-md border border-white/5 bg-background/50 px-2 py-1.5">
      <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-muted-foreground">
        <span>{label}</span>
        <span className="font-mono text-foreground/85">{value}</span>
      </div>
      <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/5">
        <div className={`h-full ${tone}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function SentinelMatrixRow({ position }: { position: Position }) {
  const p = position;
  const risk = riskToneMap[p.risk];
  return (
    <div className="rounded-lg border border-white/5 bg-background/40 p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-purple-500/25 bg-purple-500/5 text-[10px] font-semibold text-purple-300">
            {p.rank}
          </div>
          <span className="truncate text-sm font-semibold text-foreground/90">
            {p.protocol} <span className="font-mono text-foreground/70">· {p.asset}</span>
          </span>
          <ChainPill tone={p.chain} />
          <FitPill fit={p.fit} />
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${risk.pill}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${risk.dot}`} />
            {risk.label}
          </span>
          <div className="flex items-baseline gap-1">
            <span className="font-mono text-lg font-semibold text-foreground/95">{p.sentinel}</span>
            <span className="text-[10px] text-muted-foreground/70">/ 100</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        <ScoreBar label="Safety" value={p.safety} />
        <ScoreBar label="Yield dur." value={p.durability} />
        <ScoreBar label="Exit liq." value={p.exit} />
        <ScoreBar label="Confidence" value={p.confidence} />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
        <span className="uppercase tracking-wider text-muted-foreground/70">Flags:</span>
        {p.flags.length === 0 ? (
          <span className="text-emerald-300/80">— clean</span>
        ) : (
          p.flags.map((flag) => (
            <span
              key={flag}
              className="inline-flex items-center gap-1 rounded-md border border-amber-500/25 bg-amber-500/5 px-1.5 py-0.5 text-amber-200/90"
            >
              <AlertTriangle className="h-2.5 w-2.5" />
              {flag}
            </span>
          ))
        )}
      </div>
    </div>
  );
}

function SentinelScoreCard() {
  return (
    <div className="mt-3 ml-11 max-w-2xl rounded-2xl border border-purple-500/25 bg-card/70 p-4 backdrop-blur">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-purple-300">
          <ShieldCheck className="h-3.5 w-3.5" />
          <span>Sentinel Pool Scores</span>
        </div>
        <span className="rounded-full border border-purple-500/30 bg-purple-500/5 px-2 py-0.5 text-[10px] font-medium text-purple-200/80">
          Ilyon safety lens
        </span>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-white/5 bg-background/40 px-3 py-2 text-[11px] text-muted-foreground">
        <Activity className="h-3.5 w-3.5 text-purple-300" />
        <span className="uppercase tracking-wider text-muted-foreground/70">Dimensions</span>
        <span className="text-foreground/80">Safety</span>
        <span className="text-muted-foreground/40">·</span>
        <span className="text-foreground/80">Yield durability</span>
        <span className="text-muted-foreground/40">·</span>
        <span className="text-foreground/80">Exit liquidity</span>
        <span className="text-muted-foreground/40">·</span>
        <span className="text-foreground/80">Confidence</span>
      </div>

      <div className="space-y-2">
        {allocation.map((p) => (
          <SentinelMatrixRow key={p.rank} position={p} />
        ))}
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
        <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-emerald-300">
          <div className="font-mono text-lg font-semibold">4</div>
          <div className="uppercase tracking-wider text-emerald-300/80">Low risk</div>
        </div>
        <div className="rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-amber-300">
          <div className="font-mono text-lg font-semibold">1</div>
          <div className="uppercase tracking-wider text-amber-300/80">Medium risk</div>
        </div>
        <div className="rounded-md border border-white/5 bg-background/40 px-3 py-2">
          <div className="font-mono text-lg font-semibold text-foreground/90">89 / 100</div>
          <div className="uppercase tracking-wider text-muted-foreground/70">Weighted Sentinel</div>
        </div>
      </div>
    </div>
  );
}

type ExecutionStep = {
  index: number;
  verb: string;
  amount: string;
  asset: string;
  target: string;
  chain: ChainTone;
  router: string;
  wallet: "MetaMask" | "Phantom";
  gas: string;
};

const executionPlan: ExecutionStep[] = [
  { index: 1, verb: "Stake", amount: "1.612", asset: "ETH", target: "stETH · Lido", chain: "eth", router: "Enso", wallet: "MetaMask", gas: "~$4.80" },
  { index: 2, verb: "Stake", amount: "0.921", asset: "ETH", target: "rETH · Rocket Pool", chain: "eth", router: "Enso", wallet: "MetaMask", gas: "~$5.10" },
  { index: 3, verb: "Liquid stake", amount: "22.32", asset: "SOL", target: "JitoSOL · Jito", chain: "sol", router: "Jupiter", wallet: "Phantom", gas: "~$0.01" },
  { index: 4, verb: "Supply", amount: "1,500", asset: "USDC", target: "aArbUSDC · Aave v3", chain: "arb", router: "Enso", wallet: "MetaMask", gas: "~$0.35" },
  { index: 5, verb: "Deposit", amount: "1,000", asset: "USDC", target: "PT-sUSDe · Pendle", chain: "mainnet", router: "Enso", wallet: "MetaMask", gas: "~$6.90" },
];

function ExecutionPlanCard() {
  return (
    <div className="mt-3 ml-11 max-w-2xl rounded-2xl border border-purple-500/25 bg-card/70 p-4 backdrop-blur">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-purple-300">
          <ListChecks className="h-3.5 w-3.5" />
          <span>Execution Plan</span>
        </div>
        <span className="rounded-full border border-amber-500/30 bg-amber-500/5 px-2 py-0.5 text-[10px] font-medium text-amber-200/80">
          Awaiting signatures · 5
        </span>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatTile icon={<ListChecks className="h-3 w-3" />} label="Txs" value="5" />
        <StatTile icon={<Wallet className="h-3 w-3" />} label="Wallets" value="MetaMask + Phantom" />
        <StatTile icon={<Gauge className="h-3 w-3" />} label="Total gas" value="~$17.16" />
        <StatTile icon={<Scale className="h-3 w-3" />} label="Slippage" value="0.5% cap" />
      </div>

      <div className="space-y-1.5 rounded-lg border border-white/5 bg-background/40 p-2">
        {executionPlan.map((step) => (
          <ExecutionRow key={step.index} step={step} />
        ))}
      </div>

      <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200/90">
        <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>
          Each step hands a pre-built transaction to your wallet. Keys never leave your device; you can
          reject or edit any step before signing.
        </span>
      </div>

      <div className="mt-3 flex gap-2">
        <button
          disabled
          className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/15 px-4 py-2.5 text-sm font-semibold text-emerald-300 opacity-90"
        >
          <Sparkles className="h-4 w-4" />
          Start signing (5)
        </button>
        <button
          disabled
          className="flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-card/60 px-4 py-2.5 text-sm font-medium text-foreground/80 opacity-80"
        >
          <RefreshCcw className="h-4 w-4" />
          Rebalance
        </button>
      </div>
    </div>
  );
}

function ExecutionRow({ step }: { step: ExecutionStep }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md px-2 py-2 hover:bg-white/[0.02]">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-purple-500/25 bg-purple-500/5 text-[11px] font-semibold text-purple-300">
          {step.index}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-sm">
            <span className="font-semibold text-foreground/90">{step.verb}</span>
            <span className="font-mono text-foreground/80">
              {step.amount} {step.asset}
            </span>
            <span className="text-muted-foreground/60">→</span>
            <span className="truncate text-foreground/80">{step.target}</span>
          </div>
          <div className="mt-0.5 flex items-center gap-1.5">
            <ChainPill tone={step.chain} />
            <span className="text-[10px] text-muted-foreground/80">{step.router}</span>
            <span className="text-muted-foreground/50">·</span>
            <span className="text-[10px] text-muted-foreground/80">{step.wallet}</span>
          </div>
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-end">
        <span className="font-mono text-xs text-foreground/85">{step.gas}</span>
        <span className="text-[10px] text-muted-foreground/70">gas</span>
      </div>
    </div>
  );
}

function QuickChip({
  icon,
  label,
}: {
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      disabled
      className="flex shrink-0 items-center gap-2 rounded-full border border-white/10 bg-card/50 px-4 py-2 text-sm text-foreground/80 opacity-70"
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

export default function AgentChatPage() {
  return (
    <div className="container mx-auto max-w-5xl px-4 py-6">
      <PreviewBanner />

      <div className="overflow-hidden rounded-2xl border border-white/10 bg-card/40 backdrop-blur">
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="text-foreground/90">allocate $10k yield</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              disabled
              className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-300 opacity-80"
            >
              <Sparkles className="h-3.5 w-3.5" />
              New
            </button>
            <button
              disabled
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-card/40 px-3 py-1.5 text-xs font-medium text-foreground/80 opacity-80"
            >
              <MessagesSquare className="h-3.5 w-3.5" />
              15 chats
            </button>
          </div>
        </div>

        <div className="max-h-[780px] space-y-5 overflow-y-auto px-5 py-6">
          <UserBubble time="19:11">
            <span>
              I have $10,000 USDC. Allocate it across the best staking and yield opportunities,
              risk-weighted using Sentinel scores.
            </span>
          </UserBubble>

          <ReasoningAccordion
            steps={8}
            time="19:12"
            expanded
            lines={[
              "Parsed intent: allocate $10,000 across staking + yield, risk-weighted.",
              "Queried DefiLlama yield pools — 2,041 candidates across 14 chains.",
              "Filtered TVL ≥ $200M and protocols with audits + ≥ 180 days live.",
              "Scored candidates via Sentinel pool framework — Safety × Yield durability × Exit × Confidence.",
              "Cross-checked each protocol against Ilyon Shield: approval surface, admin keys, rekt history.",
              "Dropped 3 pools for oracle-dependency and upgradeable-proxy flags.",
              "Selected 5 positions across 3 chains; Sentinel ≥ 70 and position cap ≤ 35%.",
              "Composed execution plan: Enso (EVM) + Jupiter (Solana) with 0.2% gas buffer.",
            ]}
          />

          <AssistantBubble>
            Here&rsquo;s a risk-weighted allocation across 5 top-rated positions. Weighted Sentinel
            score lands at <strong>89 / 100</strong> with 4 Low-risk pools and one Medium (Pendle,
            capped at 10% for the extra yield). Blended APY is ≈ <strong>5.6%</strong> net of gas.
          </AssistantBubble>

          <AllocationCard />

          <AssistantBubble>
            Below is the Sentinel scoring breakdown for each pool — this is the Ilyon safety lens
            layered on top of the allocation, so you can see <em>why</em> each position passed, not
            just its APY.
          </AssistantBubble>

          <SentinelScoreCard />

          <ReasoningAccordion steps={3} time="19:13" />

          <AssistantBubble>
            Ready to execute? I&rsquo;ll prepare 5 transactions — two ETH LSTs on Ethereum, a
            JitoSOL liquid-stake on Solana, a USDC supply on Arbitrum, and a Pendle PT deposit on
            mainnet. You&rsquo;ll approve each one in your wallet; I never touch keys.
          </AssistantBubble>

          <ExecutionPlanCard />
        </div>

        <div className="border-t border-white/10 bg-background/30 px-5 py-3">
          <div className="mb-3 flex gap-2 overflow-x-auto">
            <QuickChip icon={<Layers className="h-3.5 w-3.5 text-emerald-400" />} label="Rebalance now" />
            <QuickChip icon={<ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />} label="Low-risk only" />
            <QuickChip icon={<TrendingUp className="h-3.5 w-3.5 text-emerald-400" />} label="Maximize APY" />
            <QuickChip icon={<Activity className="h-3.5 w-3.5 text-emerald-400" />} label="Explain Sentinel" />
            <QuickChip icon={<RefreshCcw className="h-3.5 w-3.5 text-emerald-400" />} label="Skip Pendle" />
          </div>

          <div className="flex items-end gap-2 rounded-2xl border border-white/10 bg-card/60 p-2">
            <div className="flex-1 px-3 py-2 text-sm text-muted-foreground/80 opacity-80">
              Refine the plan — e.g. &ldquo;drop Pendle, split that 10% into Lido and Jito&rdquo;...
            </div>
            <button
              disabled
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-background/40 text-muted-foreground opacity-70"
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-2 text-center text-[11px] text-muted-foreground/70">
            Enter — send · Shift+Enter — new line
          </div>
        </div>
      </div>

      <p className="mt-6 text-center text-xs text-muted-foreground/70">
        Preview of the combined product: Agent Platform handles intent capture, tool routing, and
        wallet execution; Ilyon Sentinel layers in multi-dimensional pool scoring (Safety · Yield
        durability · Exit liquidity · Confidence) and cross-checks every protocol against the Shield
        risk surface.
      </p>
    </div>
  );
}
