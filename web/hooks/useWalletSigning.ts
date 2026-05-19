/**
 * V7-045 — Centralized wallet signing hook.
 *
 * Wraps the three wallet code paths (EVM eth_sendTransaction, EVM
 * eth_signTypedData_v4 / Permit2, Solana signAndSendTransaction) behind
 * a single React hook so every Confirm / Sign-step button shares the
 * same spec-mandated pre-flight checks:
 *
 *  1. **Freshness gate** — refuses to sign when the sim artifact is
 *     older than `SIM_FRESHNESS_SECONDS` (30s). Stale sims must be
 *     re-quoted before re-prompting the wallet so the user signs the
 *     same calldata they previewed. Throws `SimStaleError` (code
 *     `SIM_STALE`).
 *
 *  2. **Calldata-hash bind** — recomputes SHA-256 over the canonical
 *     broadcast tx (or serialized Solana message) and refuses if it
 *     differs from the artifact's `expectedCalldataHash`. Throws
 *     `CalldataMismatchError` (code `CALLDATA_MISMATCH`).
 *
 * After both gates pass, dispatches to the underlying wallet primitive
 * (`signPermit2Typed` / `sendTransaction` for EVM, Phantom-style
 * `signAndSendTransaction` for Solana). The underlying wallet hooks are
 * NOT modified — this hook only composes them.
 *
 * Call-sites:
 *  - `components/agent/cards/Permit2SigButton.tsx` (EVM typed-data)
 *  - `components/agent/cards/ExecutionPlanV3Card.tsx` (pre-flight wrap
 *    around upward `onSignStep` callback)
 *  - `components/agent-app/MainApp.tsx::handleSignStep` (broadcast)
 */
import { useCallback, useState } from "react";
import {
  sendTransaction as evmSendTx,
  signPermit2Typed,
  type Permit2Domain,
  type Permit2PermitSingleMessage,
} from "@/lib/wallets/metamask";
import {
  computeCalldataHash,
  assertCalldataMatch,
  type BroadcastTx,
} from "@/lib/signer";

export const SIM_FRESHNESS_SECONDS = 30;

export class SimStaleError extends Error {
  readonly code = "SIM_STALE" as const;
  readonly ageSec: number;
  constructor(ageSec: number) {
    super(
      `SIM_STALE: Simulation is ${ageSec.toFixed(1)}s old (>${SIM_FRESHNESS_SECONDS}s). Re-quote before signing.`,
    );
    this.name = "SimStaleError";
    this.ageSec = ageSec;
  }
}

export class CalldataMismatchError extends Error {
  readonly code = "CALLDATA_MISMATCH" as const;
  readonly expected: string;
  readonly actual: string;
  constructor(expected: string, actual: string) {
    super(
      `CALLDATA_MISMATCH: expected=${expected || "<empty>"} actual=${actual || "<empty>"} — refusing to sign.`,
    );
    this.name = "CalldataMismatchError";
    this.expected = expected;
    this.actual = actual;
  }
}

/* ─── Argument shapes ───────────────────────────────────────────────── */

interface BaseSignArgs {
  /** POSIX seconds (NOT ms) when the backend simulated the tx. */
  simTimestamp: number;
  /** SHA-256 hex digest stamped at simulation time. Lowercase, may
   *  include the leading `0x`. */
  expectedCalldataHash: string;
}

export interface EvmSendArgs extends BaseSignArgs {
  mode: "evm_send";
  tx: BroadcastTx;
}

export interface EvmTypedDataArgs extends BaseSignArgs {
  mode: "evm_typed_data";
  domain: Permit2Domain;
  message: Permit2PermitSingleMessage;
}

export interface SolanaSendArgs extends BaseSignArgs {
  mode: "solana_send";
  /** Base64-encoded serialized VersionedTransaction. */
  serialized: string;
}

export type SignArgs = EvmSendArgs | EvmTypedDataArgs | SolanaSendArgs;

export interface SignResult {
  /** ECDSA / wallet signature (EVM typed-data path) or `null` when the
   *  underlying flow sends the tx directly (broadcast paths). */
  signature: string | null;
  /** On-chain tx hash (EVM) or signature (Solana). `null` for typed
   *  data signing that does not broadcast. */
  txId: string | null;
  /** Raw wallet-provider response in case the caller needs e.g. block
   *  number or status. */
  raw?: unknown;
}

export interface UseWalletSigningResult {
  sign: (args: SignArgs) => Promise<SignResult>;
  isPending: boolean;
  error: Error | null;
}

/* ─── Helpers ───────────────────────────────────────────────────────── */

/** SHA-256(serialized bytes) hex — Solana analogue of
 *  `computeCalldataHash` for EVM. Mirrors the backend hashing of the
 *  Solana serialized message so the wallet popup is hash-bound. */
async function hashSerializedBytes(b64: string): Promise<string> {
  let bytes: Uint8Array;
  if (typeof atob === "function") {
    const bin = atob(b64);
    bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  } else {
    // Node fallback for jsdom env where atob exists, but kept defensive.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const buf = Buffer.from(b64, "base64");
    bytes = new Uint8Array(buf);
  }
  if (typeof crypto !== "undefined" && crypto.subtle) {
    // Cast through BufferSource — Uint8Array satisfies the runtime
    // contract but TS 5.4's BufferSource overload is fussy about the
    // backing buffer being ArrayBuffer (not SharedArrayBuffer).
    const buf = await crypto.subtle.digest(
      "SHA-256",
      bytes as unknown as BufferSource,
    );
    return Array.from(new Uint8Array(buf))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const nodeCrypto = require("crypto");
  return nodeCrypto.createHash("sha256").update(bytes).digest("hex");
}

/** Throws `SimStaleError` if `simTimestamp` (POSIX seconds) is older
 *  than `SIM_FRESHNESS_SECONDS`. */
function assertFresh(simTimestamp: number): void {
  if (!Number.isFinite(simTimestamp) || simTimestamp <= 0) {
    throw new SimStaleError(Number.POSITIVE_INFINITY);
  }
  const ageSec = Date.now() / 1000 - simTimestamp;
  if (ageSec > SIM_FRESHNESS_SECONDS) {
    throw new SimStaleError(ageSec);
  }
}

/** Throws `CalldataMismatchError` if the recomputed hash diverges from
 *  the simulator-stamped expected hash. */
function assertHashMatch(expected: string, actual: string): void {
  try {
    assertCalldataMatch(expected, actual);
  } catch {
    throw new CalldataMismatchError(expected, actual);
  }
}

/* ─── Hook ──────────────────────────────────────────────────────────── */

export function useWalletSigning(): UseWalletSigningResult {
  const [isPending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const sign = useCallback(async (args: SignArgs): Promise<SignResult> => {
    setPending(true);
    setError(null);
    try {
      // 1. Freshness gate — same threshold as backend
      //    src/defi/freshness.py::is_simulation_fresh.
      assertFresh(args.simTimestamp);

      // 2. Calldata-hash bind (V7-001). Compute hash of the *broadcast*
      //    payload the wallet is about to see and refuse on mismatch.
      if (args.mode === "evm_send") {
        const broadcastHash = await computeCalldataHash(args.tx);
        assertHashMatch(args.expectedCalldataHash, broadcastHash);
        const txHash = await evmSendTx(args.tx);
        return { signature: null, txId: txHash, raw: { txHash } };
      }
      if (args.mode === "evm_typed_data") {
        // Permit2 typed-data: canonicalize the message + domain into a
        // stable JSON blob and hash that — matches how the backend
        // stamps Permit2 artifact hashes.
        const payload: BroadcastTx = {
          to: args.domain.verifyingContract,
          data: JSON.stringify({ domain: args.domain, message: args.message }),
        };
        const broadcastHash = await computeCalldataHash(payload);
        assertHashMatch(args.expectedCalldataHash, broadcastHash);
        const sig = await signPermit2Typed(args.domain, args.message);
        return { signature: sig, txId: null, raw: { signature: sig } };
      }
      if (args.mode === "solana_send") {
        const broadcastHash = await hashSerializedBytes(args.serialized);
        assertHashMatch(args.expectedCalldataHash, broadcastHash);
        // Delegate to Phantom-style provider. We intentionally probe
        // window.phantom.solana / window.solana lazily so this hook stays
        // SSR-safe and importable from non-Solana surfaces.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const w: any = typeof window !== "undefined" ? window : {};
        const sol = w?.phantom?.solana ?? w?.solana;
        if (!sol || typeof sol.signAndSendTransaction !== "function") {
          throw new Error("Solana wallet (Phantom) not detected.");
        }
        const { VersionedTransaction } = await import("@solana/web3.js");
        const bytes = Uint8Array.from(atob(args.serialized), (c) =>
          c.charCodeAt(0),
        );
        const vtx = VersionedTransaction.deserialize(bytes);
        const result = await sol.signAndSendTransaction(vtx);
        const signature: string =
          (result && typeof result === "object" && "signature" in result
            ? (result as { signature: string }).signature
            : (result as unknown as string)) ?? "";
        return { signature, txId: signature, raw: result };
      }
      // Exhaustiveness — TS infers `never` here at compile time.
      const _exhaust: never = args;
      throw new Error(
        `Unsupported sign mode: ${(_exhaust as { mode: string }).mode}`,
      );
    } catch (e: unknown) {
      const err = e instanceof Error ? e : new Error(String(e));
      setError(err);
      throw err;
    } finally {
      setPending(false);
    }
  }, []);

  return { sign, isPending, error };
}

/* ─── Legacy compat aliases ─────────────────────────────────────────── */

/** @deprecated Use the discriminated `sign()` API instead. Kept so
 *  the prior `SignableArtifact` shape (if anything ever imported it)
 *  still type-checks. */
export interface SignableArtifact {
  simulated_at: number;
  simulated_calldata_hash: string;
  unsigned_tx: BroadcastTx;
  chain_kind: "evm" | "solana";
}
