import {
  ArrowDown,
  Sparkles,
  ArrowRight,
  Info,
  MessagesSquare,
  Zap,
  ShieldCheck,
} from "lucide-react";

export const metadata = {
  title: "AI Swap — Preview",
};

function PreviewBanner() {
  return (
    <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-2.5 text-sm">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-emerald-400" />
        <span className="text-foreground/90">
          Preview of the AI Swap composer
        </span>
      </div>
      <span className="rounded-full bg-emerald-500/15 px-3 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300">
        Coming Soon
      </span>
    </div>
  );
}

function TokenField({
  label,
  symbol,
  name,
  amount,
  amountHint,
  chainTint,
  balance,
}: {
  label: string;
  symbol: string;
  name: string;
  amount: string;
  amountHint?: string;
  chainTint: string;
  balance?: string;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-background/40 p-4">
      <div className="mb-2 flex items-center justify-between text-[11px] uppercase tracking-wider text-muted-foreground">
        <span>{label}</span>
        {balance && <span>Balance: {balance}</span>}
      </div>
      <div className="flex items-center justify-between gap-3">
        <button
          disabled
          className="flex items-center gap-2 rounded-xl border border-white/10 bg-card/60 px-3 py-2 opacity-95"
        >
          <div
            className={`flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-semibold ${chainTint}`}
          >
            {symbol.slice(0, 2)}
          </div>
          <div className="flex flex-col items-start leading-tight">
            <span className="text-sm font-semibold text-foreground/90">{symbol}</span>
            <span className="text-[10px] text-muted-foreground">{name}</span>
          </div>
          <ArrowDown className="ml-1 h-3.5 w-3.5 text-muted-foreground" />
        </button>
        <div className="flex-1 text-right">
          <div className="text-2xl font-semibold text-foreground/90">{amount}</div>
          {amountHint && (
            <div className="text-[11px] text-muted-foreground">{amountHint}</div>
          )}
        </div>
      </div>
    </div>
  );
}

function QuickPair({ from, to }: { from: string; to: string }) {
  return (
    <button
      disabled
      className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-card/60 px-3 py-1.5 text-xs font-medium text-foreground/80 opacity-80"
    >
      <span>{from}</span>
      <ArrowRight className="h-3 w-3 text-muted-foreground" />
      <span>{to}</span>
    </button>
  );
}

function InfoRow({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className={`font-mono ${tone ?? "text-foreground/85"}`}>{value}</span>
    </div>
  );
}

export default function AgentSwapPage() {
  return (
    <div className="container mx-auto max-w-5xl px-4 py-6">
      <PreviewBanner />

      <div className="mb-6">
        <h1 className="text-2xl font-bold">AI Swap</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          A guided swap composer. Enter a pair and amount, then hand execution to the Agent chat
          for route selection, simulation, and wallet signing.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="rounded-2xl border border-white/10 bg-card/50 p-5 backdrop-blur">
          <TokenField
            label="You pay"
            symbol="SOL"
            name="Solana"
            amount="0.5"
            chainTint="bg-violet-500/20 text-violet-300"
            balance="0.4832"
          />

          <div className="relative -my-2 flex justify-center">
            <button
              disabled
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-card/80 text-muted-foreground opacity-80"
              aria-label="Swap direction"
            >
              <ArrowDown className="h-4 w-4" />
            </button>
          </div>

          <TokenField
            label="You receive (estimate)"
            symbol="USDC"
            name="Solana"
            amount="≈ 44.80"
            amountHint="Estimated from live prices"
            chainTint="bg-blue-500/20 text-blue-300"
          />

          <div className="mt-4 space-y-2 rounded-xl border border-white/5 bg-background/40 p-3">
            <InfoRow label="Rate" value="1 SOL ≈ 89.60 USDC" />
            <InfoRow label="Router" value="Jupiter (Solana)" tone="text-purple-300" />
            <InfoRow label="Priority fee" value="~ $0.001" />
            <InfoRow label="Price impact" value="< 0.05%" tone="text-emerald-400" />
          </div>

          <div className="mt-4">
            <div className="mb-2 text-[11px] uppercase tracking-wider text-muted-foreground">
              Quick pairs
            </div>
            <div className="flex flex-wrap gap-2">
              <QuickPair from="SOL" to="USDC" />
              <QuickPair from="SOL" to="JitoSOL" />
              <QuickPair from="SOL" to="JUP" />
              <QuickPair from="ETH" to="USDC" />
              <QuickPair from="BNB" to="USDT" />
            </div>
          </div>

          <button
            disabled
            className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/15 px-4 py-3 text-sm font-semibold text-emerald-300 opacity-90"
          >
            <MessagesSquare className="h-4 w-4" />
            Continue in Agent Chat
          </button>

          <p className="mt-3 text-center text-[11px] text-muted-foreground/70">
            Final route, simulation, and wallet signature happen inside the Agent Chat.
          </p>
        </div>

        <aside className="space-y-4">
          <div className="rounded-2xl border border-white/10 bg-card/50 p-5 backdrop-blur">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
              <Info className="h-4 w-4 text-emerald-400" />
              How AI Swap works
            </div>
            <ol className="space-y-3 text-xs text-muted-foreground">
              <li className="flex gap-3">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-[10px] font-semibold text-emerald-300">
                  1
                </span>
                <span>
                  Choose a pair and amount. The page estimates output client-side from live prices.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-[10px] font-semibold text-emerald-300">
                  2
                </span>
                <span>
                  On continue, the swap is handed to the Agent as a structured prompt
                  (e.g. <code className="rounded bg-background/60 px-1">Swap 0.5 SOL for USDC</code>).
                </span>
              </li>
              <li className="flex gap-3">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-[10px] font-semibold text-emerald-300">
                  3
                </span>
                <span>
                  The chat renders a SimulationPreview card with the real route, fees, and
                  warnings, then hands the transaction to your wallet to sign.
                </span>
              </li>
            </ol>
          </div>

          <div className="rounded-2xl border border-white/10 bg-card/50 p-5 backdrop-blur">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
              <Zap className="h-4 w-4 text-purple-400" />
              Routing
            </div>
            <ul className="space-y-2 text-xs text-muted-foreground">
              <li className="flex items-center justify-between">
                <span>EVM pairs</span>
                <span className="font-mono text-purple-300">Enso</span>
              </li>
              <li className="flex items-center justify-between">
                <span>Solana pairs</span>
                <span className="font-mono text-purple-300">Jupiter</span>
              </li>
              <li className="flex items-center justify-between">
                <span>Cross-chain</span>
                <span className="font-mono text-purple-300">deBridge DLN</span>
              </li>
            </ul>
          </div>

          <div className="rounded-2xl border border-white/10 bg-card/50 p-5 backdrop-blur">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              Non-custodial
            </div>
            <p className="text-xs text-muted-foreground">
              The Agent builds transaction payloads; your wallet always signs on the client. No
              keys leave your device.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
