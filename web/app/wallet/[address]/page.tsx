"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useWalletProfile, useWalletForensics } from "@/lib/hooks";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Loader2,
  ExternalLink,
  Copy,
  Wallet,
  AlertCircle,
  ArrowUpRight,
  ArrowDownLeft,
  Shield,
  Link2,
} from "lucide-react";
import {
  cn,
  truncateAddress,
  formatUSD,
  formatRelativeTime,
  copyToClipboard,
  getScoreColor,
} from "@/lib/utils";

/* ── Risk-level color helpers ── */
function getRiskColor(level: string) {
  switch (level.toUpperCase()) {
    case "LOW":
      return "text-emerald-400";
    case "MEDIUM":
      return "text-yellow-400";
    case "HIGH":
      return "text-orange-400";
    case "CRITICAL":
      return "text-red-500";
    default:
      return "text-muted-foreground";
  }
}

function getRiskBadgeClasses(level: string) {
  switch (level.toUpperCase()) {
    case "LOW":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-400";
    case "MEDIUM":
      return "border-yellow-500/40 bg-yellow-500/10 text-yellow-400";
    case "HIGH":
      return "border-orange-500/40 bg-orange-500/10 text-orange-400";
    case "CRITICAL":
      return "border-red-500/40 bg-red-500/10 text-red-500";
    default:
      return "border-muted bg-muted/10 text-muted-foreground";
  }
}

export default function WalletAddressPage() {
  const params = useParams();
  const addressParam = Array.isArray(params.address) ? params.address[0] : params.address;
  const address = addressParam ?? "";

  const { data: profile, isLoading: profileLoading, error: profileError } = useWalletProfile(address || null);
  const { data: forensics, isLoading: forensicsLoading, error: forensicsError } = useWalletForensics(address || null);

  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const ok = await copyToClipboard(address);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const isLoading = profileLoading;

  return (
    <section className="container mx-auto max-w-6xl px-4 py-8">
      {/* ── Header ── */}
      <div className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <Wallet className="h-8 w-8 text-emerald-500" />
          <h1 className="text-3xl font-bold">Wallet Intelligence</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2 mt-3">
          <code className="rounded-md bg-muted/60 px-3 py-1.5 text-sm font-mono break-all">
            {address}
          </code>
          {profile?.label && (
            <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
              {profile.label}
            </Badge>
          )}
          <Button variant="outline" size="sm" onClick={handleCopy}>
            <Copy className="h-4 w-4 mr-1" />
            {copied ? "Copied" : "Copy"}
          </Button>
          <a
            href={`https://solscan.io/account/${address}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ExternalLink className="h-4 w-4" />
            Solscan
          </a>
        </div>
      </div>

      {/* ── Loading ── */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
        </div>
      ) : profileError || !profile ? (
        /* ── No profile / error ── */
        <GlassCard className="text-center py-12">
          <AlertCircle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">
            No whale activity found for this wallet. Try a known whale address.
          </p>
        </GlassCard>
      ) : (
        <>
          {/* ── Metrics row ── */}
          <div className="grid gap-4 md:grid-cols-4 mb-8">
            {/* Risk Level */}
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                Risk Level
              </p>
              {forensicsLoading ? (
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              ) : forensics ? (
                <Badge
                  variant="outline"
                  className={cn("text-base font-semibold", getRiskBadgeClasses(forensics.risk_level))}
                >
                  {forensics.risk_level}
                </Badge>
              ) : (
                <span className="text-muted-foreground text-sm">Unknown</span>
              )}
            </GlassCard>

            {/* Volume */}
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                Volume (USD)
              </p>
              <p className="text-2xl font-semibold">{formatUSD(profile.volume_usd)}</p>
            </GlassCard>

            {/* Transaction Count */}
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                Transactions
              </p>
              <p className="text-2xl font-semibold">{profile.transaction_count.toLocaleString()}</p>
            </GlassCard>

            {/* Entity ID */}
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                Entity ID
              </p>
              <p className="text-sm font-mono truncate">
                {profile.entity_id ?? "No entity"}
              </p>
            </GlassCard>
          </div>

          {/* ── Recent Transactions ── */}
          <div className="mb-8">
            <h2 className="text-lg font-semibold mb-4">Recent Transactions</h2>
            {profile.recent_transactions.length === 0 ? (
              <GlassCard className="p-6 text-center">
                <p className="text-sm text-muted-foreground">No recent transactions.</p>
              </GlassCard>
            ) : (
              <div className="grid gap-3">
                {profile.recent_transactions.map((tx) => (
                  <GlassCard key={tx.signature} className="p-4">
                    <div className="flex items-center gap-3 flex-wrap">
                      {/* Direction icon */}
                      {tx.direction === "buy" || tx.direction === "inflow" ? (
                        <ArrowDownLeft className="h-5 w-5 text-emerald-400 shrink-0" />
                      ) : (
                        <ArrowUpRight className="h-5 w-5 text-red-400 shrink-0" />
                      )}

                      {/* Token info */}
                      <div className="flex-1 min-w-0">
                        <span className="font-semibold">{tx.token_symbol}</span>
                        <span className="text-muted-foreground text-sm ml-2">{tx.token_name}</span>
                      </div>

                      {/* Amount */}
                      <span className="font-semibold">{formatUSD(tx.amount_usd)}</span>

                      {/* DEX */}
                      <Badge variant="outline" className="text-xs">
                        {tx.dex_name}
                      </Badge>

                      {/* Chain badge */}
                      <Badge variant="secondary" className="text-xs uppercase">
                        {tx.chain}
                      </Badge>

                      {/* Relative time */}
                      <span className="text-xs text-muted-foreground whitespace-nowrap">
                        {formatRelativeTime(tx.timestamp)}
                      </span>

                      {/* Solscan link */}
                      <a
                        href={`https://solscan.io/tx/${tx.signature}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    </div>
                  </GlassCard>
                ))}
              </div>
            )}
          </div>

          {/* ── Forensics ── */}
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Shield className="h-5 w-5 text-emerald-500" />
              <h2 className="text-lg font-semibold">Forensics</h2>
            </div>
            {forensicsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : forensicsError || !forensics ? (
              <GlassCard className="p-6 text-center">
                <p className="text-sm text-muted-foreground">Forensics unavailable</p>
              </GlassCard>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {/* Reputation score */}
                <GlassCard className="p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                    Reputation Score
                  </p>
                  <p className={cn("text-3xl font-bold", getScoreColor(forensics.reputation_score))}>
                    {forensics.reputation_score}
                  </p>
                  <p className="text-xs text-muted-foreground">out of 100</p>
                </GlassCard>

                {/* Deployment stats */}
                <GlassCard className="p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                    Deployment Stats
                  </p>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Tokens deployed</span>
                      <span className="font-semibold">{forensics.tokens_deployed}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Rugged tokens</span>
                      <span className="font-semibold text-red-400">{forensics.rugged_tokens}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Active tokens</span>
                      <span className="font-semibold text-emerald-400">{forensics.active_tokens}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Rug percentage</span>
                      <span className="font-semibold">{(forensics.rug_percentage * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                </GlassCard>

                {/* Funding risk / Confidence */}
                <GlassCard className="p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                    Risk Metrics
                  </p>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Funding risk</span>
                      <span className="font-semibold">{(forensics.funding_risk * 100).toFixed(0)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Confidence</span>
                      <span className="font-semibold">{(forensics.confidence * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                </GlassCard>

                {/* Patterns detected */}
                {forensics.patterns_detected.length > 0 && (
                  <GlassCard className="p-4 md:col-span-2 lg:col-span-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                      Patterns Detected
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {forensics.patterns_detected.map((pattern) => (
                        <Badge key={pattern} variant="outline" className="text-xs">
                          {pattern}
                        </Badge>
                      ))}
                    </div>
                  </GlassCard>
                )}

                {/* Evidence summary */}
                {forensics.evidence_summary && (
                  <GlassCard className="p-4 md:col-span-2 lg:col-span-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                      Evidence Summary
                    </p>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      {forensics.evidence_summary}
                    </p>
                  </GlassCard>
                )}
              </div>
            )}
          </div>

          {/* ── Linked Wallets ── */}
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Link2 className="h-5 w-5 text-emerald-500" />
              <h2 className="text-lg font-semibold">Linked Wallets</h2>
            </div>
            {profile.linked_wallets.length === 0 ? (
              <GlassCard className="p-6 text-center">
                <p className="text-sm text-muted-foreground">No linked wallets in this entity.</p>
              </GlassCard>
            ) : (
              <>
                {profile.link_reason && (
                  <p className="text-sm text-muted-foreground mb-3">
                    Link reason: <span className="font-medium text-foreground">{profile.link_reason}</span>
                  </p>
                )}
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {profile.linked_wallets.map((w) => (
                    <Link key={w} href={`/wallet/${w}`}>
                      <GlassCard className="p-4 hover:border-emerald-500/40 transition-colors cursor-pointer">
                        <code className="text-sm font-mono">{truncateAddress(w, 6)}</code>
                      </GlassCard>
                    </Link>
                  ))}
                </div>
              </>
            )}
          </div>
        </>
      )}
    </section>
  );
}
