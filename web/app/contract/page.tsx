"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Code2,
  Search,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Info,
  ChevronDown,
  ChevronUp,
  Sparkles,
  ShieldCheck,
  ExternalLink,
  Clock3,
} from "lucide-react";
import { cn, formatRelativeTime, getEvmExplorerAddressUrl, isValidEvmAddress, truncateAddress } from "@/lib/utils";
import * as api from "@/lib/api";
import type { ContractScanResponse, VulnerabilityItem, ChainName } from "@/types";

const EVM_CHAINS: { value: ChainName; label: string }[] = [
  { value: "ethereum", label: "Ethereum" },
  { value: "base", label: "Base" },
  { value: "arbitrum", label: "Arbitrum" },
  { value: "bsc", label: "BSC" },
  { value: "polygon", label: "Polygon" },
  { value: "optimism", label: "Optimism" },
  { value: "avalanche", label: "Avalanche" },
];

const SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];

function SeverityIcon({ severity }: { severity: string }) {
  if (severity === "CRITICAL" || severity === "HIGH")
    return <XCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />;
  if (severity === "MEDIUM")
    return <AlertTriangle className="h-4 w-4 text-yellow-400 shrink-0 mt-0.5" />;
  if (severity === "LOW")
    return <AlertTriangle className="h-4 w-4 text-blue-400 shrink-0 mt-0.5" />;
  return <Info className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />;
}

function SeverityBadge({ severity }: { severity: string }) {
  const styles: Record<string, string> = {
    CRITICAL: "bg-red-500/20 text-red-400 border-red-500/30",
    HIGH: "bg-orange-500/20 text-orange-400 border-orange-500/30",
    MEDIUM: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    LOW: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    INFO: "bg-white/10 text-muted-foreground border-white/10",
    SAFE: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  };
  return (
    <span className={cn("px-2.5 py-0.5 rounded-full text-xs border font-medium", styles[severity] ?? styles.INFO)}>
      {severity}
    </span>
  );
}

function VulnerabilityRow({ vuln }: { vuln: VulnerabilityItem }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded-lg border border-white/10 bg-white/5 overflow-hidden">
      <button
        className="flex items-start gap-3 w-full px-4 py-3 hover:bg-white/5 transition-colors text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <SeverityIcon severity={vuln.severity} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm">{vuln.name}</span>
            <SeverityBadge severity={vuln.severity} />
          </div>
          {vuln.location && (
            <span className="text-xs font-mono text-muted-foreground">{vuln.location}</span>
          )}
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground shrink-0" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
        )}
      </button>
      {expanded && (
        <div className="px-4 pb-3 text-sm text-muted-foreground border-t border-white/10 pt-3">
          {vuln.description}
        </div>
      )}
    </div>
  );
}

function RiskGauge({ score, risk }: { score: number; risk: string }) {
  const color =
    risk === "CRITICAL" || risk === "HIGH"
      ? "#ef4444"
      : risk === "MEDIUM"
      ? "#eab308"
      : "#10b981";

  const circumference = 2 * Math.PI * 40;
  const dash = (score / 100) * circumference;

  return (
    <div className="relative w-28 h-28 mx-auto">
      <svg className="w-full h-full -rotate-90">
        <circle cx="56" cy="56" r="40" fill="none" stroke="hsl(var(--muted))" strokeWidth="8" />
        <circle
          cx="56"
          cy="56"
          r="40"
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeDasharray={`${dash} ${circumference}`}
          strokeLinecap="round"
          className="transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-2xl font-bold" style={{ color }}>{score}</div>
        <div className="text-xs text-muted-foreground">Risk</div>
      </div>
    </div>
  );
}

function ScanResult({ data }: { data: ContractScanResponse }) {
  const explorerUrl = getEvmExplorerAddressUrl(data.chain, data.address);
  const grouped = SEVERITY_ORDER.reduce((acc, sev) => {
    const vulns = data.vulnerabilities.filter((v) => v.severity === sev);
    if (vulns.length) acc[sev] = vulns;
    return acc;
  }, {} as Record<string, VulnerabilityItem[]>);

  const criticalCount = data.vulnerabilities.filter((v) => v.severity === "CRITICAL").length;
  const highCount = data.vulnerabilities.filter((v) => v.severity === "HIGH").length;

  return (
    <div className="space-y-6">
      {/* Overview */}
      <GlassCard>
        <div className="flex flex-col md:flex-row gap-6 items-center">
          <RiskGauge score={data.risk_score} risk={data.overall_risk} />
          <div className="flex-1 space-y-3 text-center md:text-left">
            <div>
              <div className="text-sm text-muted-foreground mb-1">Overall Risk</div>
              <SeverityBadge severity={data.overall_risk} />
            </div>
            <div className="space-y-1">
              <div className="text-lg font-semibold">{data.name || truncateAddress(data.address, 8)}</div>
              <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-muted-foreground md:justify-start">
                <code className="rounded bg-black/20 px-2 py-1 font-mono text-slate-200">{truncateAddress(data.address, 8)}</code>
                {explorerUrl && (
                  <a
                    href={explorerUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-emerald-300 transition-colors hover:text-emerald-200"
                  >
                    Explorer
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
                {data.scanned_at && (
                  <span className="inline-flex items-center gap-1">
                    <Clock3 className="h-3.5 w-3.5" />
                    {formatRelativeTime(data.scanned_at)}
                  </span>
                )}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <div className="text-xs text-muted-foreground">Verified</div>
                <div className="font-semibold">
                  {data.is_verified ? (
                    <span className="text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="h-4 w-4" /> Yes
                    </span>
                  ) : (
                    <span className="text-red-400 flex items-center gap-1">
                      <XCircle className="h-4 w-4" /> No
                    </span>
                  )}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Chain</div>
                <div className="font-semibold capitalize">{data.chain}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Compiler</div>
                <div className="font-mono text-sm">{data.compiler_version ?? "—"}</div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 justify-center md:justify-start">
              {data.is_proxy && (
                <span className="rounded border border-blue-500/20 bg-blue-500/10 px-2 py-1 text-xs text-blue-300">
                  Proxy contract
                </span>
              )}
              {data.proxy_implementation && (
                <code className="rounded bg-black/20 px-2 py-1 text-xs font-mono text-slate-200">
                  Impl {truncateAddress(data.proxy_implementation, 6)}
                </code>
              )}
              {data.license && (
                <span className="rounded border border-white/10 bg-white/5 px-2 py-1 text-xs text-muted-foreground">
                  {data.license}
                </span>
              )}
              {data.scan_duration_ms ? (
                <span className="rounded border border-white/10 bg-white/5 px-2 py-1 text-xs text-muted-foreground">
                  {(data.scan_duration_ms / 1000).toFixed(2)}s scan
                </span>
              ) : null}
            </div>
            <div className="flex gap-4 flex-wrap justify-center md:justify-start">
              <div>
                <span className="text-red-400 font-bold text-lg">{criticalCount + highCount}</span>
                <span className="text-xs text-muted-foreground ml-1">Critical/High</span>
              </div>
              <div>
                <span className="text-yellow-400 font-bold text-lg">
                  {data.vulnerabilities.filter((v) => v.severity === "MEDIUM").length}
                </span>
                <span className="text-xs text-muted-foreground ml-1">Medium</span>
              </div>
              <div>
                <span className="text-muted-foreground font-bold text-lg">
                  {data.vulnerabilities.filter((v) => ["LOW", "INFO"].includes(v.severity)).length}
                </span>
                <span className="text-xs text-muted-foreground ml-1">Low/Info</span>
              </div>
            </div>
          </div>

          {/* AI verdict */}
          {data.ai_verdict && (
            <div className="shrink-0 text-center">
              <div className="flex items-center gap-2 mb-1 justify-center">
                <Sparkles className="h-4 w-4 text-blue-400" />
                <span className="text-sm text-muted-foreground">AI Verdict</span>
              </div>
              <SeverityBadge severity={data.ai_verdict} />
            </div>
          )}
        </div>
      </GlassCard>

      {/* Key findings */}
      {data.ai_audit_summary && (
        <GlassCard>
          <h3 className="mb-3 flex items-center gap-2 font-semibold">
            <Sparkles className="h-4 w-4 text-blue-400" />
            AI Audit Summary
          </h3>
          <p className="text-sm leading-7 text-muted-foreground">{data.ai_audit_summary}</p>
        </GlassCard>
      )}

      {data.similar_to_scam && (
        <GlassCard className="border-red-500/20">
          <h3 className="mb-2 flex items-center gap-2 font-semibold text-red-300">
            <AlertTriangle className="h-4 w-4" />
            Similarity Warning
          </h3>
          <p className="text-sm text-muted-foreground">
            This contract shows similarities to known malicious patterns.
            {data.similarity_score != null ? ` Similarity score: ${Math.round(data.similarity_score * 100)}%.` : ""}
          </p>
        </GlassCard>
      )}

      {data.key_findings.length > 0 && (
        <GlassCard>
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-yellow-400" />
            Key Findings
          </h3>
          <ul className="space-y-2">
            {data.key_findings.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className="text-yellow-400 mt-0.5">•</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </GlassCard>
      )}

      {/* Recommendations */}
      {data.recommendations.length > 0 && (
        <GlassCard>
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            Recommendations
          </h3>
          <ul className="space-y-2">
            {data.recommendations.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </GlassCard>
      )}

      {/* Vulnerabilities by severity */}
      {Object.entries(grouped).map(([sev, vulns]) => (
        <div key={sev}>
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <SeverityBadge severity={sev} />
            <span className="text-muted-foreground text-sm">({vulns.length})</span>
          </h3>
          <div className="space-y-2">
            {vulns.map((v, i) => (
              <VulnerabilityRow key={i} vuln={v} />
            ))}
          </div>
        </div>
      ))}

      {data.vulnerabilities.length === 0 && (
        <GlassCard className="text-center py-8">
          <CheckCircle2 className="h-12 w-12 text-emerald-400 mx-auto mb-3" />
          <p className="font-semibold">No vulnerabilities detected</p>
          <p className="text-sm text-muted-foreground">
            The static scan found no known vulnerability patterns
          </p>
        </GlassCard>
      )}
    </div>
  );
}

export default function ContractPage() {
  const [address, setAddress] = useState("");
  const [chain, setChain] = useState<ChainName>("ethereum");
  const [validationError, setValidationError] = useState<string | null>(null);

  const scanMutation = useMutation({
    mutationFn: () => api.scanContract(address.trim(), chain),
  });

  const handleScan = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = address.trim();
    if (!trimmed) return;
    if (!isValidEvmAddress(trimmed)) {
      setValidationError("Enter a valid EVM contract address for the selected chain.");
      return;
    }

    setValidationError(null);
    scanMutation.mutate();
  };

  const errorMessage = validationError
    ?? (scanMutation.error instanceof Error
      ? scanMutation.error.message
      : "Scan failed. Ensure the address is correct and the contract is deployed on the selected chain.");

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <Code2 className="h-8 w-8 text-emerald-400" />
          <h1 className="text-3xl font-bold">Contract Scanner</h1>
        </div>
        <p className="text-muted-foreground">
          Static analysis + AI audit of any EVM smart contract — detect vulnerabilities before you interact
        </p>
      </div>

      {/* Scan form */}
      <GlassCard className="mb-8">
        <form onSubmit={handleScan} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Address */}
            <div className="md:col-span-2">
              <label className="text-xs text-muted-foreground mb-1 block">Contract Address</label>
              <div className="relative">
                <Code2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="0x..."
                  value={address}
                  onChange={(e) => {
                    setAddress(e.target.value);
                    setValidationError(null);
                    scanMutation.reset();
                  }}
                  className="pl-10 font-mono"
                />
              </div>
            </div>
            {/* Chain */}
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Chain</label>
              <select
                value={chain}
                onChange={(e) => {
                  setChain(e.target.value as ChainName);
                  setValidationError(null);
                  scanMutation.reset();
                }}
                className="w-full h-10 px-3 rounded-md bg-background border border-input text-sm"
              >
                {EVM_CHAINS.map((c) => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>
          </div>

          <Button
            type="submit"
            className="w-full bg-emerald-600 hover:bg-emerald-500 text-black font-semibold"
            disabled={!address.trim() || scanMutation.isPending}
          >
            {scanMutation.isPending ? (
              <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Scanning Contract...</>
            ) : (
              <><Search className="h-4 w-4 mr-2" /> Scan Contract</>
            )}
          </Button>
        </form>
      </GlassCard>

      {/* Error */}
      {(validationError || scanMutation.isError) && (
        <GlassCard className="border-red-500/30 mb-6">
          <div className="flex items-center gap-2 text-red-400">
            <AlertTriangle className="h-5 w-5" />
            <span>{errorMessage}</span>
          </div>
        </GlassCard>
      )}

      {/* Results */}
      {scanMutation.data && <ScanResult data={scanMutation.data} />}

      {/* Empty state */}
      {!scanMutation.data && !scanMutation.isPending && !scanMutation.isError && (
        <GlassCard className="text-center py-16">
          <Code2 className="h-16 w-16 text-emerald-400/50 mx-auto mb-4" />
          <h3 className="text-xl font-semibold mb-2">Ready to Scan</h3>
          <p className="text-muted-foreground max-w-sm mx-auto">
            Enter any EVM contract address above. We'll fetch the source code, run static analysis,
            and use AI to identify potential vulnerabilities.
          </p>
        </GlassCard>
      )}
    </div>
  );
}
