"use client";

import { useEffect, useState } from "react";
import { GlassCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Shield } from "lucide-react";
import type { AuditChainEntry } from "@/types/agent";

/**
 * Settings panel — §11 D.8 audit-trail HMAC chain viewer.
 * Reads the user's audit log via GET /api/v1/audit/{wallet}.
 */
interface AuditLogPanelProps {
  userWallet: string;
}

export default function AuditLogPanel({ userWallet }: AuditLogPanelProps) {
  const [entries, setEntries] = useState<AuditChainEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/v1/audit/${userWallet}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (cancelled) return;
        setEntries((data.entries ?? []) as AuditChainEntry[]);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message || "Failed to load audit log");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userWallet]);

  return (
    <GlassCard className="mb-6">
      <div className="flex items-center gap-2 mb-4">
        <Shield className="h-5 w-5 text-emerald-500" />
        <h2 className="font-semibold">Audit Trail (§11 D.8)</h2>
        <Badge variant="outline" className="ml-auto">
          {entries.length} entries
        </Badge>
      </div>

      {loading ? (
        <div className="text-sm text-muted-foreground py-4">Loading…</div>
      ) : error ? (
        <div className="text-sm text-red-500 py-4">
          {error} — audit log unavailable.
        </div>
      ) : entries.length === 0 ? (
        <div className="text-sm text-muted-foreground py-4">
          No audit entries yet. Your signed actions will appear here with a
          tamper-evident HMAC chain.
        </div>
      ) : (
        <ul className="space-y-2 text-xs">
          {entries.slice(0, 50).map((e) => (
            <li
              key={e.entry_id}
              className="rounded-md border border-border/30 p-3 font-mono"
            >
              <div className="flex justify-between">
                <span className="text-muted-foreground">
                  {new Date(e.ts * 1000).toISOString()}
                </span>
                <Badge variant="safe">verified</Badge>
              </div>
              <div className="mt-1">
                <span className="text-muted-foreground">prompt:</span>{" "}
                {e.prompt_hash.slice(0, 16)}…
              </div>
              <div>
                <span className="text-muted-foreground">plan:</span>{" "}
                {e.plan_hash.slice(0, 16)}…
              </div>
              {e.tx_hash ? (
                <div>
                  <span className="text-muted-foreground">tx:</span>{" "}
                  {e.tx_hash.slice(0, 16)}…
                </div>
              ) : null}
              <div className="text-muted-foreground/70 mt-1">
                hmac: {e.hmac.slice(0, 12)}…
                {e.prev_hmac ? ` ← prev: ${e.prev_hmac.slice(0, 8)}…` : ""}
              </div>
            </li>
          ))}
        </ul>
      )}
    </GlassCard>
  );
}
