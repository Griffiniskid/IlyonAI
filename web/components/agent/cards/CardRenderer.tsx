"use client";
import type {
  CardFrame,
  TokenPayload,
  SwapQuotePayload,
  BalancePayload,
  PoolPayload,
} from "@/types/agent";

interface Props {
  card: CardFrame;
}

/* ── Helper ─────────────────────────────────────────────────────────── */

function changeBadge(pct: number) {
  const positive = pct >= 0;
  return (
    <span
      className={`inline-block text-xs font-semibold px-1.5 py-0.5 rounded ${
        positive
          ? "bg-emerald-500/15 text-emerald-400"
          : "bg-red-500/15 text-red-400"
      }`}
    >
      {positive ? "+" : ""}
      {pct.toFixed(2)}%
    </span>
  );
}

function cardShell(
  title: string,
  children: React.ReactNode,
  extra?: React.ReactNode,
) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/80 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700 bg-slate-800">
        <span className="text-xs font-medium text-slate-300 uppercase tracking-wide">
          {title}
        </span>
        {extra}
      </div>
      <div className="p-3 space-y-2">{children}</div>
    </div>
  );
}

/* ── Typed cards ─────────────────────────────────────────────────────── */

function TokenCard({ payload }: { payload: TokenPayload }) {
  return cardShell(
    `${payload.symbol}`,
    <>
      <div className="flex items-center justify-between">
        <span className="text-lg font-bold text-white">
          ${payload.price_usd}
        </span>
        {changeBadge(payload.change_24h_pct)}
      </div>
      <div className="text-xs text-slate-400">
        {payload.chain} &middot;{" "}
        <span className="font-mono">{payload.address}</span>
      </div>
    </>,
  );
}

function SwapQuoteCard({ payload }: { payload: SwapQuotePayload }) {
  const payLabel =
    (payload.pay?.symbol as string) ?? (payload.pay?.address as string) ?? "?";
  const payAmt = (payload.pay?.amount as string) ?? "?";
  const recvLabel =
    (payload.receive?.symbol as string) ??
    (payload.receive?.address as string) ??
    "?";
  const recvAmt = (payload.receive?.amount as string) ?? "?";

  return cardShell(
    "Swap Quote",
    <>
      <div className="flex items-center gap-2 text-sm">
        <span className="text-white font-semibold">
          {payAmt} {payLabel}
        </span>
        <span className="text-slate-500">&rarr;</span>
        <span className="text-white font-semibold">
          {recvAmt} {recvLabel}
        </span>
      </div>
      <div className="flex flex-wrap gap-x-4 text-xs text-slate-400">
        <span>
          Rate: <span className="text-slate-200">{payload.rate}</span>
        </span>
        <span>
          Impact:{" "}
          <span
            className={
              payload.price_impact_pct > 1
                ? "text-red-400"
                : "text-slate-200"
            }
          >
            {payload.price_impact_pct}%
          </span>
        </span>
        {payload.priority_fee_usd && (
          <span>
            Priority fee:{" "}
            <span className="text-slate-200">${payload.priority_fee_usd}</span>
          </span>
        )}
      </div>
      {payload.router && (
        <div className="text-xs text-slate-500">
          via {payload.router}
        </div>
      )}
    </>,
  );
}

function BalanceCard({ payload }: { payload: BalancePayload }) {
  const chains = Object.entries(payload.by_chain ?? {});
  return cardShell(
    "Balance",
    <>
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-400">Total</span>
        <span className="text-lg font-bold text-white">
          ${payload.total_usd}
        </span>
      </div>
      {chains.length > 0 && (
        <div className="grid grid-cols-2 gap-1 text-xs">
          {chains.map(([chain, val]) => (
            <div
              key={chain}
              className="flex items-center justify-between rounded bg-slate-700/50 px-2 py-1"
            >
              <span className="text-slate-400">{chain}</span>
              <span className="text-slate-200">${val}</span>
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

function PoolCard({ payload }: { payload: PoolPayload }) {
  return cardShell(
    `${payload.protocol}`,
    <>
      <div className="flex items-center justify-between">
        <span className="text-sm text-white font-medium">{payload.asset}</span>
        <span className="text-xs text-slate-400">{payload.chain}</span>
      </div>
      <div className="flex flex-wrap gap-x-4 text-xs text-slate-400">
        <span>
          APY:{" "}
          <span className="text-emerald-400 font-semibold">{payload.apy}</span>
        </span>
        <span>
          TVL: <span className="text-slate-200">{payload.tvl}</span>
        </span>
      </div>
    </>,
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

export function CardRenderer({ card }: Props) {
  const { card_type, payload } = card;

  switch (card_type) {
    case "token":
      return <TokenCard payload={payload as unknown as TokenPayload} />;
    case "swap_quote":
      return <SwapQuoteCard payload={payload as unknown as SwapQuotePayload} />;
    case "balance":
      return <BalanceCard payload={payload as unknown as BalancePayload} />;
    case "pool":
      return <PoolCard payload={payload as unknown as PoolPayload} />;
    default:
      return <FallbackCard card={card} />;
  }
}
