"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ShieldCheck, Search, Loader2, CheckCircle2, XCircle, AlertTriangle,
  Coins, Snowflake, Lock, Droplets, Users, UserSearch, ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAnalyzeToken } from "@/lib/hooks";

// What Ilyon checks — shown in the empty state to explain the product.
const CHECKS: { icon: typeof Coins; title: string; desc: string }[] = [
  { icon: Coins, title: "Mint authority", desc: "Can the team print more supply and dilute you?" },
  { icon: Snowflake, title: "Freeze authority", desc: "Can they freeze your tokens so you can't sell?" },
  { icon: Lock, title: "Liquidity lock", desc: "Is the LP locked, or can the team pull it and rug?" },
  { icon: Droplets, title: "Honeypot check", desc: "Can the token actually be sold, or is it a trap?" },
  { icon: Users, title: "Holder concentration", desc: "Do a few wallets hold enough to dump on you?" },
  { icon: UserSearch, title: "Deployer history", desc: "Has the creator rugged tokens before?" },
];

function gradeColor(grade: string, score: number): string {
  const g = (grade || "").toUpperCase();
  if (g === "A" || g === "B" || score >= 75) return "text-emerald-400 border-emerald-500/40 bg-emerald-500/10";
  if (g === "C" || score >= 50) return "text-amber-400 border-amber-500/40 bg-amber-500/10";
  return "text-red-400 border-red-500/40 bg-red-500/10";
}

function fmtUsd(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (n > 0 && n < 0.01) return `$${n.toExponential(2)}`;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
}

// A single pass/fail safety row.
function Check({ ok, label, detail }: { ok: boolean; label: string; detail?: string }) {
  return (
    <div className="flex items-start gap-3 py-2">
      {ok ? (
        <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" />
      ) : (
        <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-400" />
      )}
      <div>
        <div className="text-sm font-medium">{label}</div>
        {detail ? <div className="text-xs text-muted-foreground">{detail}</div> : null}
      </div>
    </div>
  );
}

function TokenSafetyInner() {
  const params = useSearchParams();
  const [address, setAddress] = useState("");
  const analyze = useAnalyzeToken();
  const data = analyze.data;
  const autoRan = useRef(false);

  const runFor = (a: string) => {
    if (a.trim().length < 32) return;
    analyze.mutate({ address: a.trim(), mode: "standard", chain: "solana" });
  };
  const run = () => runFor(address);
  const idle = !data && !analyze.isPending;

  // Deep-link: /token-safety?address=… (e.g. from the home page) auto-analyzes.
  useEffect(() => {
    const a = params.get("address");
    if (a && !autoRan.current) {
      autoRan.current = true;
      setAddress(a);
      runFor(a);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-8">
      <div className="mb-6 flex items-center gap-3">
        <ShieldCheck className="h-7 w-7 text-emerald-400" />
        <div>
          <h1 className="text-2xl font-bold">Token Safety</h1>
          <p className="text-sm text-muted-foreground">
            Paste any Solana token address — Ilyon screens it for rugs before you buy.
          </p>
        </div>
      </div>

      <div className="flex gap-2">
        <Input
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="Solana token mint address (e.g. DezXAZ…B263)"
          className="flex-1 font-mono text-sm"
        />
        <Button onClick={run} disabled={analyze.isPending || address.trim().length < 32}>
          {analyze.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          <span className="ml-2">Check</span>
        </Button>
      </div>

      {/* Empty state — what Ilyon checks (fills the page before a scan) */}
      {idle && !analyze.isError ? (
        <div className="mt-10">
          <div className="mb-4 text-sm font-semibold text-muted-foreground">
            What Ilyon checks on every token
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {CHECKS.map((c) => (
              <div key={c.title} className="glass-card-hover rounded-2xl p-5">
                <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400">
                  <c.icon className="h-5 w-5" />
                </div>
                <div className="font-semibold">{c.title}</div>
                <div className="mt-1 text-sm text-muted-foreground">{c.desc}</div>
              </div>
            ))}
          </div>
          <div className="mt-8 flex items-center justify-center gap-2 rounded-2xl border border-border/50 bg-secondary/20 px-4 py-4 text-sm text-muted-foreground">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            Every token is scored <span className="font-semibold text-foreground">0–100</span> with a clear SAFE / RISKY / SCAM verdict before you trade.
            <ArrowRight className="h-4 w-4" />
          </div>
        </div>
      ) : null}

      {/* Loading skeleton */}
      {analyze.isPending ? (
        <div className="mt-8 space-y-4">
          <div className="glass-card h-24 animate-pulse rounded-2xl" />
          <div className="glass-card h-40 animate-pulse rounded-2xl" />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="glass-card h-28 animate-pulse rounded-2xl" />
            <div className="glass-card h-28 animate-pulse rounded-2xl" />
          </div>
        </div>
      ) : null}

      {analyze.isError ? (
        <div className="mt-6 flex items-center gap-2 rounded-xl border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-300">
          <AlertTriangle className="h-4 w-4" />
          Couldn&apos;t analyze that token. Check the address is a valid Solana mint and try again.
        </div>
      ) : null}

      {data ? (
        <div className="mt-8 space-y-4">
          {/* Verdict */}
          <div className="glass-card flex items-center justify-between p-5">
            <div className="flex items-center gap-4">
              {data.token?.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={data.token.logo_url} alt="" className="h-12 w-12 rounded-full" />
              ) : (
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-lg font-bold">
                  {(data.token?.symbol || "?").slice(0, 2)}
                </div>
              )}
              <div>
                <div className="text-lg font-bold">{data.token?.name || "Unknown"}</div>
                <div className="text-sm text-muted-foreground">{data.token?.symbol}</div>
              </div>
            </div>
            <div className={`flex flex-col items-center rounded-2xl border px-5 py-2 ${gradeColor(data.scores?.grade, data.scores?.overall)}`}>
              <div className="text-3xl font-black leading-none">{data.scores?.overall ?? "—"}</div>
              <div className="text-xs font-semibold">Grade {data.scores?.grade || "?"}</div>
            </div>
          </div>

          {data.recommendation ? (
            <div className="glass-card p-4 text-sm">{data.recommendation}</div>
          ) : null}

          {/* Safety checks */}
          <div className="glass-card p-5">
            <div className="mb-2 text-sm font-semibold text-muted-foreground">Safety checks</div>
            <Check
              ok={data.security?.mint_authority_enabled === false}
              label="Mint authority"
              detail={data.security?.mint_authority_enabled ? "ENABLED — supply can be inflated" : "Revoked — supply is fixed"}
            />
            <Check
              ok={data.security?.freeze_authority_enabled === false}
              label="Freeze authority"
              detail={data.security?.freeze_authority_enabled ? "ENABLED — your tokens can be frozen" : "Revoked — tokens can't be frozen"}
            />
            <Check
              ok={!!data.security?.liquidity_locked}
              label="Liquidity lock"
              detail={
                data.security?.lp_lock_percent != null
                  ? `${data.security.lp_lock_percent.toFixed(1)}% locked (${data.security?.liquidity_lock_source || "on-chain"})`
                  : data.security?.liquidity_lock_status || "unknown"
              }
            />
            <Check
              ok={(data.security?.honeypot_status || "").toLowerCase() === "safe" && !data.security?.honeypot_is_honeypot}
              label="Honeypot / sellability"
              detail={data.security?.honeypot_is_honeypot ? "Cannot sell — honeypot" : "Sellable"}
            />
          </div>

          {/* Holders + deployer */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="glass-card p-5">
              <div className="mb-2 text-sm font-semibold text-muted-foreground">Holders</div>
              <div className="space-y-1 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Top holder</span><span>{data.holders?.top_holder_pct != null ? `${data.holders.top_holder_pct.toFixed(1)}%` : "—"}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Top-10 concentration</span><span>{data.holders?.holder_concentration != null ? `${data.holders.holder_concentration.toFixed(1)}%` : "—"}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Suspicious wallets</span><span>{data.holders?.suspicious_wallets ?? "—"}</span></div>
              </div>
            </div>
            <div className="glass-card p-5">
              <div className="mb-2 text-sm font-semibold text-muted-foreground">Deployer</div>
              {data.deployer?.available ? (
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between"><span className="text-muted-foreground">Risk level</span><span>{data.deployer.risk_level}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Tokens deployed</span><span>{data.deployer.tokens_deployed}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Rugged before</span><span className={data.deployer.rugged_tokens > 0 ? "text-red-400" : ""}>{data.deployer.rugged_tokens}</span></div>
                  {data.deployer.is_known_scammer ? <div className="text-red-400">⚠ Known scammer</div> : null}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">Deployer history unavailable for this token.</div>
              )}
            </div>
          </div>

          {/* Market */}
          <div className="glass-card p-5">
            <div className="mb-2 text-sm font-semibold text-muted-foreground">Market</div>
            <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
              <div><div className="text-muted-foreground text-xs">Price</div><div>{fmtUsd(data.market?.price_usd)}</div></div>
              <div><div className="text-muted-foreground text-xs">Market cap</div><div>{fmtUsd(data.market?.market_cap)}</div></div>
              <div><div className="text-muted-foreground text-xs">Liquidity</div><div>{fmtUsd(data.market?.liquidity_usd)}</div></div>
              <div><div className="text-muted-foreground text-xs">24h</div><div className={((data.market?.price_change_24h ?? 0) >= 0) ? "text-emerald-400" : "text-red-400"}>{data.market?.price_change_24h != null ? `${data.market.price_change_24h.toFixed(1)}%` : "—"}</div></div>
            </div>
          </div>

          <p className="text-center text-xs text-muted-foreground">
            Not financial advice. Always do your own research.
          </p>
        </div>
      ) : null}
    </div>
  );
}

export default function TokenSafetyPage() {
  return (
    <Suspense fallback={<div className="mx-auto w-full max-w-3xl px-4 py-8 text-sm text-muted-foreground">Loading…</div>}>
      <TokenSafetyInner />
    </Suspense>
  );
}
