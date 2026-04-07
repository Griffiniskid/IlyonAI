"use client";

import { COMING_SOON } from "@/lib/feature-flags";
import { ComingSoon } from "@/components/coming-soon";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FileSearch,
  CheckCircle,
  XCircle,
  ExternalLink,
  Search,
  Shield,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import * as api from "@/lib/api";
import type { AuditRecord } from "@/types";

const KNOWN_AUDITORS = [
  "All",
  "Trail of Bits",
  "OpenZeppelin",
  "PeckShield",
  "ChainSecurity",
  "Cantina",
  "Sherlock",
  "OtterSec",
  "Kudelski Security",
];

const CHAIN_FILTERS = ["All", "Ethereum", "Base", "Arbitrum", "Polygon", "Optimism", "Solana"];

function VerdictBadge({ verdict }: { verdict: string }) {
  if (verdict === "PASS") {
    return (
      <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
        <CheckCircle className="w-3 h-3" /> PASS
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20">
      <XCircle className="w-3 h-3" /> FAIL
    </span>
  );
}

function SeverityBar({
  findings,
}: {
  findings: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    informational: number;
  };
}) {
  const colors: Record<string, string> = {
    critical: "bg-red-500",
    high: "bg-orange-500",
    medium: "bg-yellow-500",
    low: "bg-blue-400",
    informational: "bg-slate-500",
  };

  const items = Object.entries(findings).filter(([, n]) => n > 0);

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {items.map(([sev, count]) => (
        <span key={sev} className="flex items-center gap-1 text-xs">
          <span className={cn("w-2 h-2 rounded-full", colors[sev])} />
          <span className="text-muted-foreground capitalize">{sev}: {count}</span>
        </span>
      ))}
      {items.length === 0 && (
        <span className="text-xs text-muted-foreground">No findings</span>
      )}
    </div>
  );
}

export default function AuditsPage() {
  if (COMING_SOON) {
    return <ComingSoon title="Audit Database" description="Smart contract audit records from leading security firms — coming soon." icon="file-search" />;
  }
  return <AuditsPageContent />;
}

function AuditsPageContent() {
  const [auditor, setAuditor] = useState("All");
  const [chain, setChain] = useState("All");
  const [search, setSearch] = useState("");
  const [verdict, setVerdict] = useState<"" | "PASS" | "FAIL">("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["audits", auditor, chain, verdict],
    queryFn: () => api.getAudits({
      auditor: auditor !== "All" ? auditor : undefined,
      chain: chain !== "All" ? chain : undefined,
      verdict: verdict || undefined,
      limit: 200,
    }),
    staleTime: 300_000,
  });

  const { data: statsData } = useQuery({
    queryKey: ["intel-stats"],
    queryFn: api.getIntelStats,
    staleTime: 300_000,
  });

  const allAudits: AuditRecord[] = data?.audits ?? [];
  const filtered = allAudits.filter(a =>
    !search || a.protocol.toLowerCase().includes(search.toLowerCase())
  );

  const stats = statsData?.audits;

  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <FileSearch className="w-7 h-7 text-emerald-400" />
          <h1 className="text-3xl font-bold">Audit Database</h1>
        </div>
        <p className="text-muted-foreground">
          Smart contract audit records from Trail of Bits, OpenZeppelin, PeckShield, and more.
          Verify a protocol's security before depositing funds.
        </p>
      </div>

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { label: "Total Audits", value: stats.total_audits },
            { label: "Passed", value: stats.pass_count, color: "text-emerald-400" },
            { label: "Failed", value: stats.fail_count, color: "text-red-400" },
          ].map(s => (
            <div key={s.label} className="bg-card/60 border border-white/10 rounded-xl p-4 text-center">
              <div className={cn("text-2xl font-bold", s.color || "")}>{s.value}</div>
              <div className="text-xs text-muted-foreground mt-1">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search protocol..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-8 h-9 bg-black/20 border-white/10 w-48"
          />
        </div>

        {/* Verdict */}
        <div className="flex rounded-lg border border-white/10 overflow-hidden">
          {(["", "PASS", "FAIL"] as const).map(v => (
            <button
              key={v || "all"}
              onClick={() => setVerdict(v)}
              className={cn(
                "px-3 py-1.5 text-xs font-medium transition-colors",
                verdict === v
                  ? "bg-white/10 text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {v || "All"}
            </button>
          ))}
        </div>

        {/* Chain */}
        <div className="flex gap-1 flex-wrap">
          {CHAIN_FILTERS.map(c => (
            <button
              key={c}
              onClick={() => setChain(c)}
              className={cn(
                "px-2.5 py-1 rounded-full text-xs border transition-colors",
                chain === c
                  ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                  : "text-muted-foreground border-white/10 hover:border-white/20"
              )}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {/* Auditor filter */}
      <div className="flex gap-1 flex-wrap mb-6">
        {KNOWN_AUDITORS.map(a => (
          <button
            key={a}
            onClick={() => setAuditor(a)}
            className={cn(
              "px-3 py-1 rounded-full text-xs border transition-colors",
              auditor === a
                ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                : "text-muted-foreground border-white/10 hover:border-white/20"
            )}
          >
            {a}
          </button>
        ))}
      </div>

      {/* Results */}
      {isLoading ? (
        <div className="text-center py-16 text-muted-foreground">Loading audit records...</div>
      ) : error ? (
        <div className="text-center py-16 text-red-400">
          {error instanceof Error ? error.message : "Failed to load audit records."}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">No audit records found.</div>
      ) : (
        <div className="space-y-3">
          {filtered.map(audit => (
            <div
              key={audit.id}
              className="bg-card/50 border border-white/5 hover:border-white/10 rounded-xl p-5 transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    <span className="font-semibold">{audit.protocol}</span>
                    <VerdictBadge verdict={audit.verdict} />
                    {audit.findings_source === "estimated" && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-medium text-muted-foreground bg-white/5 border border-white/10">
                        Estimated
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground">{audit.date}</span>
                  </div>

                  <div className="flex items-center gap-2 text-sm text-muted-foreground mb-3">
                    <Shield className="w-3.5 h-3.5" />
                    <span>{audit.auditor}</span>
                    {audit.chains.length > 0 && (
                      <span className="ml-2 flex gap-1">
                        {audit.chains.slice(0, 4).map(c => (
                          <span key={c} className="px-1.5 py-0.5 rounded text-[10px] bg-white/5">{c}</span>
                        ))}
                      </span>
                    )}
                  </div>

                  <SeverityBar findings={audit.severity_findings} />
                </div>

                {audit.report_url && (
                  <a
                    href={audit.report_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-shrink-0 flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                  >
                    Report <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 text-xs text-muted-foreground text-right">
        {filtered.length} audit{filtered.length !== 1 ? "s" : ""} shown
      </div>
    </div>
  );
}
