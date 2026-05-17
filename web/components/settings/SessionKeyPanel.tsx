"use client";

import { useEffect, useState } from "react";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ExternalLink } from "lucide-react";
import {
  sendTransaction as evmSendTx,
  waitForReceipt as evmWaitReceipt,
  getChainId as evmGetChainId,
} from "@/lib/wallets/metamask";
import { getEvmExplorerTxUrlByChainId } from "@/lib/utils";

/**
 * §11 D.2 — SessionKeyPanel with on-chain revoke.
 *
 * Revoke flow:
 *   1. POST /api/v1/sessions/{policy_id}/revoke (off-chain DB flip)
 *   2. POST /api/v1/eip7702/uninstall-module-calldata { validator_module }
 *   3. eth_sendTransaction({ to: smart_account_address, data, value: 0 })
 *      (selector 0xa71763a8 = uninstallModule(uint256,address,bytes))
 *   4. waitForReceipt → on success, POST /api/v1/eip7702/broadcast registers
 *      the revoke tx_hash on the audit chain.
 */
interface Policy {
  policy_id: string;
  scope: string;
  spend_cap_24h_usd?: string | null;
  expires_at?: string | null;
  revoked_at?: string | null;
  /** Smart account that holds the validator module (the EOA after EIP-7702
   *  delegation). Defaults to the connected wallet when absent. */
  smart_account_address?: string | null;
  /** ERC-7579 validator module to uninstall. Backend may pin this per-policy;
   *  if absent the panel falls back to the canonical SessionKeyManager. */
  validator_module?: string | null;
}

interface SessionKeyPanelProps {
  userWallet: string;
}

const DEFAULT_VALIDATOR_MODULE =
  "0x0000000000F8c1deDD7D60ce4e2B1b9D7f78f3a6";

interface RevokeRecord {
  revokedAt: string;
  txHash?: string | null;
  chainId?: number | null;
  error?: string | null;
}

export default function SessionKeyPanel({ userWallet }: SessionKeyPanelProps) {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revoked, setRevoked] = useState<Record<string, RevokeRecord>>({});
  const [busyPolicy, setBusyPolicy] = useState<string | null>(null);

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
        const seed: Record<string, RevokeRecord> = {};
        for (const [pid, ts] of Object.entries(data.revoked_cache || {})) {
          seed[pid] = { revokedAt: String(ts) };
        }
        setRevoked(seed);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : "Failed to load policies";
        setError(msg);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [userWallet]);

  const revoke = async (p: Policy) => {
    setBusyPolicy(p.policy_id);
    try {
      // 1. off-chain flip first — guarantees the agent stops issuing new
      // actions even if the on-chain broadcast fails.
      const resp = await fetch(`/api/v1/sessions/${p.policy_id}/revoke`, {
        method: "POST",
      });
      const data = await resp.json();
      if (!data.ok) throw new Error(data.error || "off-chain revoke failed");
      const baseRecord: RevokeRecord = { revokedAt: data.revoked_at };
      setRevoked((r) => ({ ...r, [p.policy_id]: baseRecord }));

      // 2/3/4. on-chain uninstallModule broadcast
      const validator = p.validator_module || DEFAULT_VALIDATOR_MODULE;
      const target = p.smart_account_address || userWallet;
      let chainId: number | null = null;
      try {
        chainId = await evmGetChainId();
      } catch {
        chainId = null;
      }

      const cdResp = await fetch(
        "/api/v1/eip7702/uninstall-module-calldata",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ validator_module: validator }),
        },
      );
      const cd = await cdResp.json();
      if (!cd.ok) throw new Error(cd.error || "uninstall calldata failed");

      const txHash = await evmSendTx({
        to: target,
        data: cd.calldata,
        value: "0x0",
        from: userWallet,
      });
      setRevoked((r) => ({
        ...r,
        [p.policy_id]: { ...baseRecord, txHash, chainId },
      }));

      await evmWaitReceipt(txHash, { intervalMs: 2500, timeoutMs: 180_000 });

      // Best-effort tx-hash registration on the audit chain — the backend
      // route accepts an auth_id; we pass policy_id so deployments that
      // share the table can still correlate. Failure is non-fatal.
      try {
        await fetch("/api/v1/eip7702/broadcast", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            auth_id: p.policy_id,
            tx_hash: txHash,
            chain_id: chainId ?? 1,
          }),
        });
      } catch {
        // swallow — UI already shows the explorer link
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "revoke failed";
      setRevoked((r) => ({
        ...r,
        [p.policy_id]: {
          ...(r[p.policy_id] ?? { revokedAt: new Date().toISOString() }),
          error: msg,
        },
      }));
    } finally {
      setBusyPolicy(null);
    }
  };

  return (
    <GlassCard className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-semibold">Session keys</h2>
          <p className="text-sm text-muted-foreground">
            Per-position policies that authorise autonomous actions on your
            behalf. Revoke flips the policy off-chain instantly and broadcasts
            the on-chain <code>uninstallModule</code> (selector{" "}
            <code>0xa71763a8</code>) so the validator can no longer co-sign new
            actions.
          </p>
        </div>
      </div>
      {loading && <p className="text-sm">Loading…</p>}
      {error && <p className="text-sm text-red-500">{error}</p>}
      {!loading && policies.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No active session keys for {userWallet.slice(0, 6)}…
          {userWallet.slice(-4)}.
        </p>
      )}
      <ul className="space-y-3 mt-4">
        {policies.map((p) => {
          const rec = revoked[p.policy_id];
          const revokedAt = p.revoked_at || rec?.revokedAt;
          const isActive = !revokedAt;
          const busy = busyPolicy === p.policy_id;
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
                  {rec?.txHash && rec?.chainId ? (
                    <a
                      href={
                        getEvmExplorerTxUrlByChainId(rec.chainId, rec.txHash) ??
                        "#"
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-emerald-500 underline"
                    >
                      revoke-tx <ExternalLink className="h-3 w-3" />
                    </a>
                  ) : null}
                </div>
                <p className="text-sm mt-1">{p.scope}</p>
                <p className="text-xs text-muted-foreground">
                  {p.spend_cap_24h_usd
                    ? `24h cap: $${p.spend_cap_24h_usd}`
                    : "no spend cap"}
                  {p.expires_at ? ` · expires ${p.expires_at}` : ""}
                </p>
                {rec?.error ? (
                  <p className="text-xs text-red-500 mt-1">{rec.error}</p>
                ) : null}
              </div>
              {isActive && (
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={busy}
                  onClick={() => revoke(p)}
                >
                  {busy ? "Revoking…" : "Revoke"}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </GlassCard>
  );
}
