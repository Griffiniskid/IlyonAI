"use client";

import { useEffect, useState } from "react";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Key, Zap } from "lucide-react";

/**
 * Phase 7 smart-account opt-in panel.
 *
 * Hits POST /api/v1/auth/eip7702/prepare to fetch the signing digest,
 * then prompts MetaMask via window.ethereum.request to sign, then
 * POSTs to /api/v1/auth/eip7702/authorize.
 *
 * Renders active authorizations via GET /api/v1/auth/eip7702/{wallet}.
 */
interface Eip7702Authorization {
  auth_id?: string;
  impl_addr: string;
  chain_id: number;
  nonce: number;
  created_at?: string;
  revoked_at?: string | null;
  expired_at?: string | null;
}

interface Eip7702OptInPanelProps {
  userWallet: string;
}

export default function Eip7702OptInPanel({ userWallet }: Eip7702OptInPanelProps) {
  const [auths, setAuths] = useState<Eip7702Authorization[]>([]);
  const [impl, setImpl] = useState<"nexus" | "kernel">("nexus");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = async () => {
    try {
      const r = await fetch(`/api/v1/auth/eip7702/${userWallet}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setAuths((data.authorizations ?? []) as Eip7702Authorization[]);
      setError(null);
    } catch (e: any) {
      setError(e?.message || "Failed to load authorizations");
    }
  };

  useEffect(() => {
    void reload();
  }, [userWallet]);

  const optIn = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. fetch digest
      const prepResp = await fetch("/api/v1/auth/eip7702/prepare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          wallet: userWallet,
          chain_id: 1,
          nonce: auths.length, // simple: next slot
          impl,
        }),
      });
      const prep = await prepResp.json();
      if (!prep.ok) throw new Error(prep.error || "prepare failed");

      // 2. user signs digest in MetaMask
      const ethereum = (window as any).ethereum;
      if (!ethereum) throw new Error("MetaMask not detected");
      const sig: string = await ethereum.request({
        method: "personal_sign",
        params: [prep.digest, userWallet],
      });

      // 3. send signature back to server
      const authResp = await fetch("/api/v1/auth/eip7702/authorize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          wallet: userWallet,
          chain_id: prep.chain_id,
          nonce: prep.nonce,
          impl,
          signature_hex: sig,
        }),
      });
      const out = await authResp.json();
      if (!out.ok) throw new Error(out.error || "authorize failed");
      await reload();
    } catch (e: any) {
      setError(e?.message || "Authorization failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <GlassCard className="mb-6">
      <div className="flex items-center gap-2 mb-4">
        <Key className="h-5 w-5 text-emerald-500" />
        <h2 className="font-semibold">Smart Account Opt-In (EIP-7702)</h2>
      </div>

      <p className="text-sm text-muted-foreground mb-3">
        Upgrade your EOA into a smart account via Biconomy Nexus or ZeroDev
        Kernel. One signature unlocks autonomous flows guarded by your
        session-key policies above.
      </p>

      <div className="flex gap-2 mb-3">
        <Button
          variant={impl === "nexus" ? "default" : "outline"}
          onClick={() => setImpl("nexus")}
          size="sm"
        >
          Biconomy Nexus
        </Button>
        <Button
          variant={impl === "kernel" ? "default" : "outline"}
          onClick={() => setImpl("kernel")}
          size="sm"
        >
          ZeroDev Kernel
        </Button>
      </div>

      <Button onClick={optIn} disabled={loading} className="w-full">
        <Zap className="h-4 w-4 mr-2" />
        {loading ? "Awaiting signature…" : `Sign ${impl === "nexus" ? "Nexus" : "Kernel"} authorization`}
      </Button>

      {error ? (
        <div className="mt-3 text-sm text-red-500">{error}</div>
      ) : null}

      <div className="mt-4">
        <div className="text-xs text-muted-foreground mb-2">
          Active authorizations ({auths.length})
        </div>
        {auths.length === 0 ? (
          <div className="text-xs text-muted-foreground/70">
            No active authorizations.
          </div>
        ) : (
          <ul className="space-y-1 font-mono text-xs">
            {auths.map((a, i) => (
              <li
                key={a.auth_id ?? `${a.chain_id}-${a.nonce}-${i}`}
                className="flex justify-between rounded-md border border-border/30 p-2"
              >
                <span>
                  chain {a.chain_id} · nonce {a.nonce}
                </span>
                <span className="text-muted-foreground">
                  {a.impl_addr.slice(0, 8)}…
                </span>
                <Badge variant={a.revoked_at ? "destructive" : "safe"}>
                  {a.revoked_at ? "revoked" : "active"}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </div>
    </GlassCard>
  );
}
