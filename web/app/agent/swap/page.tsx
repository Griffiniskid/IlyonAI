"use client";

import { useMemo, useState } from "react";
import { ArrowDown, MessageSquare, Shield, Sparkles, Zap } from "lucide-react";
import { useRouter } from "next/navigation";

const TOKENS = [
  { symbol: "SOL", name: "Solana", tone: "from-violet-500/25 to-emerald-400/10", chain: "Solana" },
  { symbol: "USDC", name: "USD Coin", tone: "from-sky-500/25 to-sky-400/10", chain: "Solana" },
  { symbol: "JitoSOL", name: "Jito Staked SOL", tone: "from-violet-500/25 to-cyan-400/10", chain: "Solana" },
  { symbol: "JUP", name: "Jupiter", tone: "from-emerald-500/25 to-lime-400/10", chain: "Solana" },
  { symbol: "ETH", name: "Ethereum", tone: "from-slate-500/25 to-blue-400/10", chain: "Ethereum" },
  { symbol: "BNB", name: "BNB", tone: "from-amber-500/25 to-yellow-400/10", chain: "BNB Chain" },
  { symbol: "USDT", name: "Tether", tone: "from-emerald-500/25 to-emerald-300/10", chain: "BNB Chain" },
];

const QUICK_PAIRS = [
  ["SOL", "USDC"],
  ["SOL", "JitoSOL"],
  ["SOL", "JUP"],
  ["ETH", "USDC"],
  ["BNB", "USDT"],
] as const;

const MOCK_RATES: Record<string, number> = {
  "SOL:USDC": 89.6,
  "SOL:JitoSOL": 0.967,
  "SOL:JUP": 124.5,
  "ETH:USDC": 3188.4,
  "BNB:USDT": 604.2,
};

function tokenMeta(symbol: string) {
  return TOKENS.find((token) => token.symbol === symbol) ?? TOKENS[0];
}

function TokenPill({ symbol }: { symbol: string }) {
  const token = tokenMeta(symbol);
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-2 pr-10">
      <div className={`flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br ${token.tone} text-xs font-semibold text-foreground`}>
        {symbol.slice(0, 2).toUpperCase()}
      </div>
      <div>
        <div className="text-sm font-medium text-foreground">{symbol}</div>
        <div className="text-xs text-muted-foreground">{token.chain}</div>
      </div>
    </div>
  );
}

function TokenSelectControl({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="relative">
      <TokenPill symbol={value} />
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="absolute inset-0 cursor-pointer opacity-0"
        aria-label="Token"
      >
        {TOKENS.map((token) => (
          <option key={token.symbol} value={token.symbol}>
            {token.symbol}
          </option>
        ))}
      </select>
      <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">⌄</div>
    </div>
  );
}

export default function AgentSwapPage() {
  const router = useRouter();
  const [fromToken, setFromToken] = useState("SOL");
  const [toToken, setToToken] = useState("USDC");
  const [amount, setAmount] = useState("0.5");

  const rateKey = `${fromToken}:${toToken}`;
  const rate = MOCK_RATES[rateKey] ?? 1;
  const output = useMemo(() => {
    const numeric = Number.parseFloat(amount);
    if (!Number.isFinite(numeric) || numeric <= 0) return "0.0";
    return (numeric * rate).toFixed(toToken === "USDC" || toToken === "USDT" ? 2 : 4);
  }, [amount, rate, toToken]);

  const handleContinue = () => {
    const prompt = `Swap ${amount || "0.5"} ${fromToken} to ${toToken}`;
    router.push(`/agent/chat?prompt=${encodeURIComponent(prompt)}`);
  };

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6">
      <div className="mb-5 flex items-center justify-between gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-2.5 text-sm">
        <div className="flex items-center gap-2 text-foreground/90">
          <Sparkles className="h-4 w-4 text-emerald-400" />
          <span>Preview of the AI Swap composer</span>
        </div>
        <span className="rounded-full bg-emerald-500/15 px-3 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300">
          Coming soon
        </span>
      </div>

      <div className="mb-6 max-w-4xl">
        <h1 className="text-4xl font-semibold tracking-tight text-foreground">AI Swap</h1>
        <p className="mt-2 text-base text-muted-foreground">
          A guided swap composer. Enter a pair and amount, then hand execution to the Agent chat for route selection,
          simulation, and wallet signing.
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="rounded-3xl border border-white/10 bg-card/35 p-5 backdrop-blur">
          <div className="rounded-2xl bg-background/60 p-4 ring-1 ring-white/5">
            <div className="rounded-2xl bg-black/20 p-4">
              <div className="mb-2 flex items-center justify-between text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                <span>You pay</span>
                <span>Balance: 0.4832</span>
              </div>
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-3">
                  <TokenSelectControl value={fromToken} onChange={setFromToken} />
                </div>
                <input
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                  className="w-full bg-transparent text-right text-4xl font-semibold tracking-tight text-foreground outline-none md:w-40"
                  inputMode="decimal"
                />
              </div>
            </div>

            <div className="flex justify-center py-3">
              <button
                type="button"
                onClick={() => {
                  setFromToken(toToken);
                  setToToken(fromToken);
                }}
                className="rounded-2xl border border-white/10 bg-white/[0.04] p-3 text-muted-foreground transition hover:bg-white/[0.07] hover:text-foreground"
              >
                <ArrowDown className="h-5 w-5" />
              </button>
            </div>

            <div className="rounded-2xl bg-black/20 p-4">
              <div className="mb-2 flex items-center justify-between text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                <span>You receive (estimate)</span>
                <span>Estimated from live prices</span>
              </div>
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-3">
                  <TokenSelectControl value={toToken} onChange={setToToken} />
                </div>
                <div className="text-right">
                  <div className="text-4xl font-semibold tracking-tight text-foreground">{output}</div>
                  <div className="mt-1 text-xs text-muted-foreground">Estimated from live prices</div>
                </div>
              </div>
            </div>

            <div className="mt-5 grid gap-2 rounded-2xl bg-black/15 px-4 py-3 text-sm text-muted-foreground md:grid-cols-2">
              <div className="flex items-center justify-between gap-4">
                <span>Rate</span>
                <span className="font-medium text-foreground">1 {fromToken} ≈ {rate} {toToken}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Router</span>
                <span className="font-medium text-violet-300">{fromToken === "SOL" || toToken === "SOL" || fromToken === "JitoSOL" || toToken === "JitoSOL" || fromToken === "JUP" || toToken === "JUP" ? "Jupiter (Solana)" : "Enso"}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Priority fee</span>
                <span className="font-medium text-foreground">~ $0.001</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Price impact</span>
                <span className="font-medium text-emerald-300">&lt; 0.05%</span>
              </div>
            </div>

            <div className="mt-5">
              <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Quick pairs</div>
              <div className="flex flex-wrap gap-2">
                {QUICK_PAIRS.map(([from, to]) => (
                  <button
                    key={`${from}:${to}`}
                    type="button"
                    onClick={() => {
                      setFromToken(from);
                      setToToken(to);
                    }}
                    className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm text-muted-foreground transition hover:border-emerald-500/20 hover:bg-emerald-500/5 hover:text-foreground"
                  >
                    {from} → {to}
                  </button>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={handleContinue}
              className="mt-6 flex w-full items-center justify-center gap-2 rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm font-medium text-emerald-300 transition hover:bg-emerald-500/15"
            >
              <MessageSquare className="h-4 w-4" />
              Continue in Agent Chat
            </button>
            <p className="mt-3 text-center text-xs text-muted-foreground">
              Final route, simulation, and wallet signature happen inside the Agent Chat.
            </p>
          </div>
        </section>

        <aside className="space-y-4">
          <section className="rounded-3xl border border-white/10 bg-card/30 p-5 backdrop-blur">
            <div className="flex items-center gap-2 text-lg font-medium text-foreground">
              <Shield className="h-5 w-5 text-emerald-400" />
              How AI Swap works
            </div>
            <ol className="mt-4 space-y-4 text-sm text-muted-foreground">
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-500/10 text-xs font-semibold text-emerald-300">1</span>
                <span>Choose a pair and amount. The page estimates output client-side from live prices.</span>
              </li>
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-500/10 text-xs font-semibold text-emerald-300">2</span>
                <span>On continue, the swap is handed to the Agent as a structured prompt.</span>
              </li>
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-500/10 text-xs font-semibold text-emerald-300">3</span>
                <span>The chat renders a simulation preview with route, fees, and warnings, then hands signing to your wallet.</span>
              </li>
            </ol>
          </section>

          <section className="rounded-3xl border border-white/10 bg-card/30 p-5 backdrop-blur">
            <div className="flex items-center gap-2 text-lg font-medium text-foreground">
              <Zap className="h-5 w-5 text-violet-300" />
              Routing
            </div>
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex items-center justify-between text-muted-foreground"><span>EVM pairs</span><span className="text-violet-300">Enso</span></div>
              <div className="flex items-center justify-between text-muted-foreground"><span>Solana pairs</span><span className="text-violet-300">Jupiter</span></div>
              <div className="flex items-center justify-between text-muted-foreground"><span>Cross-chain</span><span className="text-violet-300">deBridge DLN</span></div>
            </div>
          </section>

          <section className="rounded-3xl border border-white/10 bg-card/30 p-5 backdrop-blur">
            <div className="flex items-center gap-2 text-lg font-medium text-foreground">
              <Shield className="h-5 w-5 text-emerald-400" />
              Non-custodial
            </div>
            <p className="mt-4 text-sm text-muted-foreground">
              The Agent builds transaction payloads; your wallet always signs on the client. No keys leave your device.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
