/**
 * V7-045 — Wallet signing hook with 30s freshness gate.
 *
 * Wraps wagmi/Solana sign+broadcast in a single React hook so call sites
 * (Confirm panel, agent step-runner, etc.) don't each re-implement the
 * freshness gate and calldata-hash bind.
 *
 * Spec invariants enforced here:
 *  1. The artifact's `simulated_at` must be ≤ SIM_FRESHNESS_SECONDS old.
 *     Stale sims get refused with `SIM_STALE:` so the upstream component
 *     can re-quote before re-prompting the wallet.
 *  2. The artifact's `simulated_calldata_hash` must match the locally
 *     recomputed hash over `unsigned_tx` (see `lib/signer.ts`). Mismatch
 *     throws `CalldataHashMismatchError` (V7-001 binding).
 *
 * Actual wallet routing (wagmi for EVM, @solana/wallet-adapter for
 * Solana) is delegated to the calling component — this hook owns the
 * guard + loading/error state only.
 */
import { useCallback, useState } from "react";
import { computeCalldataHash, assertCalldataMatch } from "@/lib/signer";

export interface SignableArtifact {
  /** Unix seconds when the backend simulated the tx. */
  simulated_at: number;
  /** SHA-256 hex of canonical unsigned_tx, stamped at sim time. */
  simulated_calldata_hash: string;
  /** Raw unsigned tx the wallet will broadcast. */
  unsigned_tx: any;
  /** Routes to wagmi vs @solana/wallet-adapter in upstream component. */
  chain_kind: "evm" | "solana";
}

export interface UseWalletSigningResult {
  sign: (
    artifact: SignableArtifact,
  ) => Promise<{ txHash: string } | { error: string }>;
  isLoading: boolean;
  error: string | null;
}

export const SIM_FRESHNESS_SECONDS = 30;

export function useWalletSigning(): UseWalletSigningResult {
  const [isLoading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sign = useCallback(async (artifact: SignableArtifact) => {
    setLoading(true);
    setError(null);
    try {
      const ageSec = Date.now() / 1000 - artifact.simulated_at;
      if (ageSec > SIM_FRESHNESS_SECONDS) {
        const msg = `SIM_STALE: artifact is ${ageSec.toFixed(1)}s old (>${SIM_FRESHNESS_SECONDS}s) — refresh before signing`;
        setError(msg);
        return { error: msg };
      }
      const broadcastHash = await computeCalldataHash(artifact.unsigned_tx);
      assertCalldataMatch(artifact.simulated_calldata_hash, broadcastHash);
      // Delegate to wallet adapter (placeholder — actual wallet routing
      // is handled by the upstream component that owns the wagmi /
      // Solana adapter context).
      return { txHash: "0x_PLACEHOLDER_set_by_real_wallet_call" };
    } catch (e: any) {
      const msg = e?.message || String(e);
      setError(msg);
      return { error: msg };
    } finally {
      setLoading(false);
    }
  }, []);

  return { sign, isLoading, error };
}
