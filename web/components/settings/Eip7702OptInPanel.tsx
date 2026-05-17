"use client";

import { useEffect, useState } from "react";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Key, Zap, ExternalLink } from "lucide-react";
import {
  sendTransaction as evmSendTx,
  signMessage as evmSignMessage,
  waitForReceipt as evmWaitReceipt,
  getChainId as evmGetChainId,
} from "@/lib/wallets/metamask";
import { getEvmExplorerTxUrlByChainId } from "@/lib/utils";

/**
 * §11 D.1 — Phase 7 smart-account opt-in panel.
 *
 * Flow:
 *   1. POST /api/v1/eip7702/prepare         → { digest, chain_id, nonce, impl }
 *   2. wallet personal_sign(digest)          → 65-byte sig
 *   3. POST /api/v1/eip7702/authorize        → persists auth row, returns { auth_id, impl_addr }
 *   4. POST /api/v1/eip7702/install-module-calldata → { calldata }
 *   5. wallet eth_sendTransaction({ to: impl_addr, data: calldata, value: 0 })
 *   6. waitForReceipt(txHash) — poll until confirmed
 *   7. POST /api/v1/eip7702/broadcast        → registers tx_hash on the auth row
 *   8. UI updates to "Authorized" with explorer link
 */
interface Eip7702Authorization {
  auth_id?: string;
  impl_addr: string;
  chain_id: number;
  nonce: number;
  created_at?: string;
  revoked_at?: string | null;
  expired_at?: string | null;
  broadcast_tx_hash?: string | null;
}

interface Eip7702OptInPanelProps {
  userWallet: string;
  /** ERC-7579 validator-module address that backs the session-key policy.
   *  Defaults to the Biconomy SessionKeyManager validator (`0x000000…`).
   *  Pass an override for tenant-specific deployments. */
  validatorModule?: string;
  /** Override the EVM chain id used for the auth (defaults to whatever the
   *  wallet currently reports via eth_chainId, falling back to 1). */
  chainIdOverride?: number;
}

// Canonical Biconomy SessionKeyManager validator module (ERC-7579 type 1)
// — same address across every chain Biconomy supports per their docs.
const DEFAULT_VALIDATOR_MODULE =
  "0x0000000000F8c1deDD7D60ce4e2B1b9D7f78f3a6";

export default function Eip7702OptInPanel({
  userWallet,
  validatorModule = DEFAULT_VALIDATOR_MODULE,
  chainIdOverride,
}: Eip7702OptInPanelProps) {
  const [auths, setAuths] = useState<Eip7702Authorization[]>([]);
  const [impl, setImpl] = useState<"nexus" | "kernel">("nexus");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");
  const [lastTxHash, setLastTxHash] = useState<string | null>(null);
  const [lastChainId, setLastChainId] = useState<number | null>(null);

  const reload = async () => {
    try {
      const r = await fetch(`/api/v1/eip7702/${userWallet}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setAuths((data.authorizations ?? []) as Eip7702Authorization[]);
      setError(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load authorizations";
      setError(msg);
    }
  };

  useEffect(() => {
    void reload();
  }, [userWallet]);

  const optIn = async () => {
    setLoading(true);
    setError(null);
    setStatus("");
    setLastTxHash(null);
    try {
      // Resolve chain id from the wallet (so e.g. Base / Arbitrum auths
      // don't get force-pinned to mainnet by a stale literal).
      let chainId = chainIdOverride ?? null;
      if (chainId === null) {
        try {
          chainId = await evmGetChainId();
        } catch {
          chainId = 1;
        }
      }
      setLastChainId(chainId);

      // 1. fetch digest
      setStatus("Preparing authorization digest…");
      const prepResp = await fetch("/api/v1/eip7702/prepare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          wallet: userWallet,
          chain_id: chainId,
          nonce: auths.length, // next slot
          impl,
        }),
      });
      const prep = await prepResp.json();
      if (!prep.ok) throw new Error(prep.error || "prepare failed");

      // 2. user signs digest in MetaMask / Phantom-EVM
      setStatus("Awaiting authorization signature…");
      const sig = await evmSignMessage(prep.digest);

      // 3. send signature back to server → persists auth row
      setStatus("Persisting authorization…");
      const authResp = await fetch("/api/v1/eip7702/authorize", {
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
      const auth = await authResp.json();
      if (!auth.ok) throw new Error(auth.error || "authorize failed");

      // 4. fetch installModule calldata for the validator module that
      // enforces session-key spend caps / selector allowlists.
      // Spend cap + allowlist + expiry are placeholder defaults; the
      // SessionKeyPanel pipeline will refine these per-policy.
      setStatus("Fetching installModule calldata…");
      const expiryUnix = Math.floor(Date.now() / 1000) + 30 * 24 * 3600;
      const cdResp = await fetch("/api/v1/eip7702/install-module-calldata", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          validator_module: validatorModule,
          session_signer: userWallet,
          // 1e21 wei (1000 ETH) — bounded later by policy-framework hooks.
          spend_cap_wei: "1000000000000000000000",
          selector_allowlist: ["0xa9059cbb"], // ERC-20 transfer as a safe default
          expiry_unix: expiryUnix,
        }),
      });
      const cd = await cdResp.json();
      if (!cd.ok) throw new Error(cd.error || "calldata fetch failed");

      // 5. broadcast installModule via eth_sendTransaction
      setStatus("Broadcasting installModule…");
      const txHash = await evmSendTx({
        to: auth.impl_addr,
        data: cd.calldata,
        value: "0x0",
        from: userWallet,
      });
      setLastTxHash(txHash);

      // 6. poll receipt
      setStatus(`Waiting for receipt ${txHash.slice(0, 10)}…`);
      await evmWaitReceipt(txHash, { intervalMs: 2500, timeoutMs: 180_000 });

      // 7. register broadcast tx_hash with backend
      setStatus("Registering broadcast…");
      await fetch("/api/v1/eip7702/broadcast", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          auth_id: auth.auth_id,
          tx_hash: txHash,
          chain_id: prep.chain_id,
        }),
      });

      setStatus("Authorized.");
      await reload();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Authorization failed";
      setError(msg);
      setStatus("");
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
        Kernel. One signature + one broadcast tx installs the session-key
        validator module that enforces your policies on-chain.
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
        {loading
          ? status || "Working…"
          : `Sign + install ${impl === "nexus" ? "Nexus" : "Kernel"} validator`}
      </Button>

      {error ? (
        <div className="mt-3 text-sm text-red-500">{error}</div>
      ) : null}

      {lastTxHash && lastChainId ? (
        <div className="mt-3 text-xs">
          <a
            href={getEvmExplorerTxUrlByChainId(lastChainId, lastTxHash) ?? "#"}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-emerald-500 underline"
          >
            {lastTxHash.slice(0, 12)}…<ExternalLink className="h-3 w-3" />
          </a>
        </div>
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
                {a.broadcast_tx_hash ? (
                  <a
                    href={
                      getEvmExplorerTxUrlByChainId(a.chain_id, a.broadcast_tx_hash) ?? "#"
                    }
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-emerald-500 underline"
                  >
                    tx
                  </a>
                ) : null}
                <Badge variant={a.revoked_at ? "destructive" : "safe"}>
                  {a.revoked_at
                    ? "revoked"
                    : a.broadcast_tx_hash
                      ? "authorized"
                      : "signed"}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </div>
    </GlassCard>
  );
}
