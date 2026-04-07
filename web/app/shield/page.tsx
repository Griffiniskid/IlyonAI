"use client";

import { COMING_SOON } from "@/lib/feature-flags";
import { ComingSoon } from "@/components/coming-soon";
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Shield,
  Search,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Wallet,
  ChevronDown,
  ChevronUp,
  Copy,
  ExternalLink,
} from "lucide-react";
import { cn, formatRelativeTime, getEvmExplorerAddressUrl, isValidEvmAddress, truncateAddress } from "@/lib/utils";
import * as api from "@/lib/api";
import type { ApprovalItem, ShieldScanResponse } from "@/types";

const CHAINS = ["all", "ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche"];

function formatAllowance(approval: ApprovalItem) {
  if (
    approval.allowance === "unlimited"
    || approval.allowance === "115792089237316195423570985008687907853269984665640564039457584007913129639935"
  ) {
    return "Unlimited";
  }

  return approval.allowance;
}

function RiskIcon({ level }: { level: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" }) {
  if (level === "CRITICAL" || level === "HIGH") return <XCircle className="h-5 w-5 text-red-400" />;
  if (level === "MEDIUM") return <AlertTriangle className="h-5 w-5 text-yellow-400" />;
  return <CheckCircle2 className="h-5 w-5 text-emerald-400" />;
}

function ApprovalCard({
  approval,
  onRevoke,
  isRevoking,
}: {
  approval: ApprovalItem;
  onRevoke: (approval: ApprovalItem) => void;
  isRevoking: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  const copy = (text: string) => navigator.clipboard.writeText(text);
  const tokenUrl = getEvmExplorerAddressUrl(approval.chain, approval.token_address);
  const spenderUrl = getEvmExplorerAddressUrl(approval.chain, approval.spender_address);
  const tokenLabel = approval.token_symbol || approval.token_name || truncateAddress(approval.token_address, 8);
  const spenderLabel = approval.spender_name ?? truncateAddress(approval.spender_address, 8);

  return (
    <GlassCard className={cn(
      "transition-all",
      (approval.risk_level === "CRITICAL" || approval.risk_level === "HIGH") && "border-red-500/30",
      approval.risk_level === "MEDIUM" && "border-yellow-500/30",
    )}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <RiskIcon level={approval.risk_level} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className="font-semibold text-sm">
                {spenderLabel}
              </span>
              {approval.spender_is_verified && (
                <Badge variant="safe" className="text-xs">Verified</Badge>
              )}
              <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 border border-white/10 capitalize">
                {approval.chain}
              </span>
            </div>
            <div className="text-sm text-foreground">
              {approval.token_name ? `${approval.token_name} ` : ""}
              <span className="font-mono text-xs text-emerald-300">{tokenLabel}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground font-mono">
              Token: {truncateAddress(approval.token_address, 8)}
              <button onClick={() => copy(approval.token_address)} className="ml-1 opacity-50 hover:opacity-100">
                <Copy className="inline h-3 w-3" />
              </button>
              {tokenUrl && (
                <a
                  href={tokenUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-emerald-300 hover:text-emerald-200"
                >
                  Explorer
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground font-mono">
              Spender: {truncateAddress(approval.spender_address, 8)}
              <button onClick={() => copy(approval.spender_address)} className="ml-1 opacity-50 hover:opacity-100">
                <Copy className="inline h-3 w-3" />
              </button>
              {spenderUrl && (
                <a
                  href={spenderUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-emerald-300 hover:text-emerald-200"
                >
                  Explorer
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Badge
            variant={approval.risk_level === "CRITICAL" || approval.risk_level === "HIGH" ? "danger" : approval.risk_level === "MEDIUM" ? "caution" : "safe"}
          >
            {approval.risk_level}
          </Badge>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-white/5 space-y-3">
          {/* Risk reasons */}
          {approval.risk_reasons.length > 0 && (
            <div className="space-y-1">
              {approval.risk_reasons.map((r, i) => (
                <div key={i} className="flex items-start gap-2 text-sm text-yellow-400">
                  <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                  <span>{r}</span>
                </div>
              ))}
            </div>
          )}

          {/* Allowance */}
          <div className="text-xs text-muted-foreground">
            Allowance:{" "}
            <span className="font-mono text-foreground">{formatAllowance(approval)}</span>
          </div>

          {approval.allowance_usd != null && approval.allowance_usd > 0 && (
            <div className="text-xs text-muted-foreground">
              Estimated exposure: <span className="font-mono text-foreground">${approval.allowance_usd.toFixed(2)}</span>
            </div>
          )}

          {(approval.approved_at || approval.last_used) && (
            <div className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
              <div>Approved: {approval.approved_at ? formatRelativeTime(approval.approved_at) : "Unknown"}</div>
              <div>Last used: {approval.last_used ? formatRelativeTime(approval.last_used) : "Unknown"}</div>
            </div>
          )}

          {/* Revoke button */}
          {approval.risk_level !== "LOW" && (
            <Button
              size="sm"
              variant="destructive"
              onClick={() => onRevoke(approval)}
              disabled={isRevoking}
              className="w-full sm:w-auto"
            >
              {isRevoking ? (
                <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Preparing...</>
              ) : (
                <><XCircle className="h-4 w-4 mr-2" /> Revoke Approval</>
              )}
            </Button>
          )}
        </div>
      )}
    </GlassCard>
  );
}

function SummaryBar({ data }: { data: ShieldScanResponse }) {
  const s = data.summary;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
      {[
        { label: "Total Approvals", value: s.total_approvals, icon: Shield, color: "text-foreground" },
        { label: "High Risk", value: s.high_risk_count, icon: XCircle, color: "text-red-400" },
        { label: "Medium Risk", value: s.medium_risk_count, icon: AlertTriangle, color: "text-yellow-400" },
        { label: "Low Risk", value: s.low_risk_count, icon: CheckCircle2, color: "text-emerald-400" },
      ].map(({ label, value, icon: Icon, color }) => (
        <GlassCard key={label} className="text-center py-4">
          <Icon className={cn("h-5 w-5 mx-auto mb-1", color)} />
          <div className={cn("text-2xl font-bold", color)}>{value}</div>
          <div className="text-xs text-muted-foreground">{label}</div>
        </GlassCard>
      ))}
    </div>
  );
}

export default function ShieldPage() {
  if (COMING_SOON) {
    return <ComingSoon title="Shield" description="Scan your wallet for risky token approvals across all EVM chains and revoke them in one click — coming soon." icon="shield" />;
  }
  return <ShieldPageContent />;
}

function ShieldPageContent() {
  const [wallet, setWallet] = useState("");
  const [inputWallet, setInputWallet] = useState("");
  const [chainFilter, setChainFilter] = useState("all");
  const [revokeTarget, setRevokeTarget] = useState<ApprovalItem | null>(null);
  const [revokeResult, setRevokeResult] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["shield", wallet, chainFilter],
    queryFn: () =>
      api.scanWalletApprovals(
        wallet,
        chainFilter !== "all" ? (chainFilter as any) : undefined
      ),
    enabled: !!wallet,
    staleTime: 30_000,
  });

  const revokeMutation = useMutation({
    mutationFn: async (approval: ApprovalItem) => {
      const result = await api.prepareRevoke(
        approval.token_address,
        approval.spender_address,
        approval.chain
      );
      return result;
    },
    onSuccess: (result) => {
      setRevokeResult(
        `Transaction prepared. Send this calldata to your wallet:\n\nTo: ${result.unsigned_transaction.to}\nData: ${result.unsigned_transaction.data}\n\n${result.warning}`
      );
    },
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputWallet.trim();
    if (!trimmed) return;
    if (!isValidEvmAddress(trimmed)) {
      setValidationError("Enter a valid EVM wallet address.");
      return;
    }

    setValidationError(null);
    setWallet(trimmed);
    setRevokeResult(null);
  };

  const handleRevoke = (approval: ApprovalItem) => {
    setRevokeTarget(approval);
    revokeMutation.mutate(approval);
  };

  const visibleApprovals = data?.approvals.filter(
    (a) => chainFilter === "all" || a.chain === chainFilter
  ) ?? [];

  const sortedApprovals = [...visibleApprovals].sort((a, b) => b.risk_score - a.risk_score);
  const errorMessage = validationError || (error instanceof Error ? error.message : "Failed to scan wallet. Check the address and try again.");

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <Shield className="h-8 w-8 text-emerald-400" />
          <h1 className="text-3xl font-bold">Shield</h1>
        </div>
        <p className="text-muted-foreground">
          Scan your wallet for risky token approvals across all EVM chains and revoke them in one click
        </p>
      </div>

      {/* Search */}
      <GlassCard className="mb-6">
        <form onSubmit={handleSearch} className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Wallet className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Enter wallet address (0x...)"
              value={inputWallet}
              onChange={(e) => {
                setInputWallet(e.target.value);
                setValidationError(null);
              }}
              className="pl-10 font-mono"
            />
          </div>
          <Button
            type="submit"
            className="bg-emerald-600 hover:bg-emerald-500 text-black font-semibold shrink-0"
            disabled={isLoading}
          >
            {isLoading ? (
              <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Scanning...</>
            ) : (
              <><Search className="h-4 w-4 mr-2" /> Scan Approvals</>
            )}
          </Button>
        </form>
      </GlassCard>

      {/* Error */}
      {(validationError || error) && (
        <GlassCard className="border-red-500/30 mb-6">
          <div className="flex items-center gap-2 text-red-400">
            <AlertTriangle className="h-5 w-5" />
            <span>{errorMessage}</span>
          </div>
        </GlassCard>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <div className="text-center">
            <Loader2 className="h-8 w-8 animate-spin text-emerald-500 mx-auto mb-4" />
            <p className="text-muted-foreground">Scanning approvals across all chains…</p>
          </div>
        </div>
      )}

      {/* Results */}
      {data && !isLoading && (
        <>
          <SummaryBar data={data} />

          <GlassCard className="mb-6">
            <div className="flex flex-col gap-2 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
              <div>
                Wallet <code className="rounded bg-black/20 px-2 py-1 font-mono text-slate-200">{truncateAddress(data.wallet, 10)}</code>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span>Chains scanned:</span>
                {data.chains_scanned.map((chain) => (
                  <Badge key={chain} variant="outline" className="capitalize">
                    {chain}
                  </Badge>
                ))}
                {data.scanned_at && <span>Updated {formatRelativeTime(data.scanned_at)}</span>}
              </div>
            </div>
          </GlassCard>

          {/* Recommendation */}
          {data.recommendation && (
            <GlassCard className="mb-6 border-emerald-500/20">
              <div className="flex items-start gap-3">
                <Shield className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
                <p className="text-sm">{data.recommendation}</p>
              </div>
            </GlassCard>
          )}

          {/* Chain filter */}
          <div className="flex flex-wrap gap-2 mb-4">
            {CHAINS.filter((c) =>
              c === "all" || data.chains_scanned.includes(c)
            ).map((c) => (
              <Button
                key={c}
                variant={chainFilter === c ? "default" : "outline"}
                size="sm"
                className={cn(chainFilter === c && "bg-emerald-600 hover:bg-emerald-500", "capitalize")}
                onClick={() => setChainFilter(c)}
              >
                {c === "all" ? "All Chains" : c}
              </Button>
            ))}
          </div>

          {/* Approvals */}
          {sortedApprovals.length === 0 ? (
            <GlassCard className="text-center py-12">
              <CheckCircle2 className="h-12 w-12 text-emerald-400 mx-auto mb-4" />
              <p className="font-semibold mb-1">No approvals found</p>
              <p className="text-sm text-muted-foreground">This wallet looks clean on the selected chain(s)</p>
            </GlassCard>
          ) : (
            <div className="space-y-3">
              {sortedApprovals.map((approval, i) => (
                <ApprovalCard
                  key={`${approval.chain}:${approval.token_address}:${approval.spender_address}:${i}`}
                  approval={approval}
                  onRevoke={handleRevoke}
                  isRevoking={
                    revokeMutation.isPending
                    && revokeTarget?.chain === approval.chain
                    && revokeTarget?.token_address === approval.token_address
                    && revokeTarget?.spender_address === approval.spender_address
                  }
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Revoke result modal */}
      {revokeResult && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <GlassCard className="max-w-lg w-full">
            <h3 className="font-semibold mb-3">Revoke Transaction Prepared</h3>
            <pre className="text-xs font-mono bg-black/30 p-3 rounded-lg overflow-auto whitespace-pre-wrap mb-4">
              {revokeResult}
            </pre>
            <Button onClick={() => setRevokeResult(null)} className="w-full">Close</Button>
          </GlassCard>
        </div>
      )}

      {/* Empty state — no wallet entered */}
      {!wallet && !isLoading && (
        <GlassCard className="text-center py-16">
          <Shield className="h-16 w-16 text-emerald-400/50 mx-auto mb-4" />
          <h3 className="text-xl font-semibold mb-2">Protect Your Wallet</h3>
          <p className="text-muted-foreground max-w-sm mx-auto">
            Enter any EVM wallet address above to scan all token approvals and identify risky spenders
          </p>
        </GlassCard>
      )}
    </div>
  );
}
