"use client";

import { useEffect, useState } from "react";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface Policy {
  policy_id: string;
  scope: string;
  spend_cap_24h_usd?: string | null;
  expires_at?: string | null;
  revoked_at?: string | null;
}

interface SessionKeyPanelProps {
  userWallet: string;
}

export default function SessionKeyPanel({ userWallet }: SessionKeyPanelProps) {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revoked, setRevoked] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!userWallet) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`/api/v1/sessions/${userWallet.toLowerCase()}`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        if (!data.ok) {
          setError(data.error || "Failed to load policies");
          return;
        }
        setPolicies(data.policies || []);
        setRevoked(data.revoked_cache || {});
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [userWallet]);

  const revoke = async (policyId: string) => {
    const resp = await fetch(`/api/v1/sessions/${policyId}/revoke`, {
      method: "POST",
    });
    const data = await resp.json();
    if (data.ok) {
      setRevoked((r) => ({ ...r, [policyId]: data.revoked_at }));
    }
  };

  return (
    <GlassCard className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-semibold">Session keys</h2>
          <p className="text-sm text-muted-foreground">
            Per-position policies that authorise autonomous actions on your behalf.
            One-click revoke flips the policy off-chain instantly; on-chain enforcement
            via Biconomy/ZeroDev follows when the Phase 7 framework lands.
          </p>
        </div>
      </div>
      {loading && <p className="text-sm">Loading…</p>}
      {error && <p className="text-sm text-red-500">{error}</p>}
      {!loading && policies.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No active session keys for {userWallet.slice(0, 6)}…{userWallet.slice(-4)}.
        </p>
      )}
      <ul className="space-y-3 mt-4">
        {policies.map((p) => {
          const revokedAt = p.revoked_at || revoked[p.policy_id];
          const isActive = !revokedAt;
          return (
            <li
              key={p.policy_id}
              className="flex items-center justify-between rounded-md border border-border/40 p-3"
            >
              <div>
                <div className="flex items-center gap-2">
                  <Badge variant={isActive ? "default" : "secondary"}>
                    {isActive ? "Active" : "Revoked"}
                  </Badge>
                  <span className="font-mono text-xs">
                    {p.policy_id.slice(0, 8)}…
                  </span>
                </div>
                <p className="text-sm mt-1">{p.scope}</p>
                <p className="text-xs text-muted-foreground">
                  {p.spend_cap_24h_usd
                    ? `24h cap: $${p.spend_cap_24h_usd}`
                    : "no spend cap"}
                  {p.expires_at ? ` · expires ${p.expires_at}` : ""}
                </p>
              </div>
              {isActive && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => revoke(p.policy_id)}
                >
                  Revoke
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </GlassCard>
  );
}
