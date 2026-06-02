"use client";

import { useCallback, useEffect, useState } from "react";
import { GlassCard } from "@/components/ui/card";
import { ArrowLeftRight, ArrowRightLeft, Send, Coins, Droplets, ExternalLink, Loader2, Receipt, RefreshCw } from "lucide-react";

type TxRow = {
  id: number;
  wallet: string;
  kind: string;
  status: string;
  chain: string | null;
  dst_chain: string | null;
  from_token: string | null;
  to_token: string | null;
  from_amount: string | null;
  to_amount: string | null;
  signature: string | null;
  order_id: string | null;
  explorer_url: string | null;
  created_at: string | null;
};

function readWallet(): string {
  if (typeof window === "undefined") return "";
  try {
    const ctx = localStorage.getItem("ap_phantom_wallet_context");
    if (ctx) {
      const parsed = JSON.parse(ctx);
      if (parsed?.solanaAddress) return String(parsed.solanaAddress);
      if (parsed?.evmAddress) return String(parsed.evmAddress);
    }
  } catch { /* ignore */ }
  return localStorage.getItem("ap_sol_wallet") || localStorage.getItem("ap_wallet") || "";
}

const KIND_ICON: Record<string, typeof Receipt> = {
  swap: ArrowLeftRight,
  bridge: ArrowRightLeft,
  transfer: Send,
  stake: Coins,
  lp: Droplets,
};

function StatusBadge({ status }: { status: string }) {
  const s = (status || "").toLowerCase();
  const color = s === "confirmed" ? "#34D399" : s === "failed" ? "#F87171" : "#A78BFA";
  return (
    <span style={{ color, fontSize: 12, fontWeight: 600, textTransform: "capitalize" }}>
      {s || "sent"}
    </span>
  );
}

function relTime(iso: string | null): string {
  if (!iso) return "";
  const t = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z").getTime();
  if (Number.isNaN(t)) return "";
  const diff = Math.max(0, Date.now() - t);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function ActivityPage() {
  const [wallet, setWallet] = useState<string>("");
  const [rows, setRows] = useState<TxRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (w: string) => {
    if (!w) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/transactions?wallet=${encodeURIComponent(w)}&limit=100`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRows(Array.isArray(data.transactions) ? data.transactions : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const w = readWallet();
    setWallet(w);
    if (w) load(w);
  }, [load]);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6">
      <div className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Receipt className="h-5 w-5 text-emerald-400" />
          <h1 className="text-lg font-semibold text-white">Activity</h1>
        </div>
        <button
          onClick={() => load(wallet)}
          disabled={!wallet || loading}
          className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 disabled:opacity-40"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Refresh
        </button>
      </div>

      <p className="mb-4 text-xs text-white/40">
        Your swaps, bridges, and transfers made through Ilyon. Recorded when you sign.
      </p>

      {!wallet && (
        <GlassCard className="p-6 text-center text-sm text-white/60">
          Connect a wallet to see your activity.
        </GlassCard>
      )}

      {wallet && error && (
        <GlassCard className="p-6 text-center text-sm text-red-300">{error}</GlassCard>
      )}

      {wallet && !error && !loading && rows.length === 0 && (
        <GlassCard className="p-8 text-center text-sm text-white/50">
          No transactions yet. Your swaps and bridges will appear here after you sign them.
        </GlassCard>
      )}

      <div className="flex flex-col gap-2">
        {rows.map((tx) => {
          const Icon = KIND_ICON[tx.kind] ?? Receipt;
          const route = tx.dst_chain && tx.chain && tx.dst_chain !== tx.chain
            ? `${tx.chain} → ${tx.dst_chain}`
            : (tx.chain || "");
          return (
            <GlassCard key={tx.id} className="flex items-center justify-between gap-3 p-3.5">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-400/10">
                  <Icon className="h-4.5 w-4.5 text-emerald-300" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm font-medium text-white">
                    <span className="capitalize">{tx.kind}</span>
                    <span className="truncate text-white/60">
                      {tx.from_amount ? `${tx.from_amount} ` : ""}{tx.from_token || ""}
                      {tx.to_token ? ` → ${tx.to_token}` : ""}
                    </span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs text-white/40">
                    {route && <span>{route}</span>}
                    {route && <span>·</span>}
                    <span>{relTime(tx.created_at)}</span>
                  </div>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <StatusBadge status={tx.status} />
                {tx.explorer_url && (
                  <a
                    href={tx.explorer_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-white/40 hover:text-white"
                    title="View on explorer"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </a>
                )}
              </div>
            </GlassCard>
          );
        })}
      </div>
    </div>
  );
}
