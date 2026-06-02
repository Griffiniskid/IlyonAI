/**
 * V7-001 — Confirm-button calldata-hash binding (client side).
 *
 * Spec: "One Confirm button: produces an artifact hash; the wallet
 * popup's calldata must hash-match this artifact, or signing is
 * refused. Enforces simulated_calldata_hash == broadcast_calldata_hash"
 *
 * The frontend Confirm button hands a SimulatedArtifact to
 * `signWithHashBind`. Before invoking the wallet, we recompute the hash
 * over the broadcast calldata we're about to send and refuse if it
 * diverges from the artifact's `simulated_calldata_hash`. This catches:
 *  - server-side plan rebuilds that didn't refresh the artifact
 *  - in-flight calldata tampering between simulation and sign
 *  - stale tx objects re-used after a quote refresh
 */
import { sendTransaction } from "./wallets/metamask";

export class CalldataHashMismatchError extends Error {
  readonly simHash: string;
  readonly broadcastHash: string;
  constructor(simHash: string, broadcastHash: string) {
    super(
      `calldata hash mismatch: simulated=${simHash} broadcast=${broadcastHash} ` +
        `— refusing to sign (spec V7-001)`,
    );
    this.name = "CalldataHashMismatchError";
    this.simHash = simHash;
    this.broadcastHash = broadcastHash;
  }
}

export interface SimulatedArtifact {
  /** Hex digest (lowercase, no `0x`) stamped at simulation time. */
  simulated_calldata_hash: string;
  /** Stable display label so the user knows what they're confirming. */
  step_id?: string;
}

export interface BroadcastTx {
  to: string;
  data?: string;
  value?: string;
  from?: string;
  // Sent to the wallet but NOT hashed (computeCalldataHash uses only
  // {to,data,value}). `chainId` triggers a pre-send chain switch.
  gas?: string;
  chainId?: number;
}

/** Normalize a hex digest for comparison (lowercase, strip `0x`). */
function normalizeHash(h: string): string {
  const lower = h.trim().toLowerCase();
  return lower.startsWith("0x") ? lower.slice(2) : lower;
}

/** SHA-256 hex digest over the canonical JSON-stringified tx payload.
 *  Mirrors `src/defi/execution/state_machine.py::compute_calldata_hash`
 *  so backend-stamped artifact hashes match client-side recomputed
 *  hashes byte-for-byte. */
export async function computeCalldataHash(tx: BroadcastTx): Promise<string> {
  // Hash ONLY the fields the backend stamps — `{to, data, value?}` (see
  // `src/defi/execution/models.py::UnsignedStepTransaction.stamp_simulation`).
  // The wallet layer often adds `from`/`gas`/`chainId`/`nonce` to the
  // broadcast tx; hashing those would diverge from the backend-stamped hash
  // and reject EVERY signature with CalldataHashMismatch. Keys are inserted in
  // alphabetical order to match the Python `sort_keys=True` serialization.
  const ordered: Record<string, string> = {};
  for (const k of ["data", "to", "value"] as Array<keyof BroadcastTx>) {
    const v = tx[k];
    if (v !== undefined && v !== null) ordered[k] = String(v);
  }
  const blob = JSON.stringify(ordered);
  const enc = new TextEncoder().encode(blob);
  // Browser SubtleCrypto path; falls back to Node `crypto` for SSR/test.
  if (typeof crypto !== "undefined" && crypto.subtle) {
    const buf = await crypto.subtle.digest("SHA-256", enc);
    return Array.from(new Uint8Array(buf))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const nodeCrypto = require("crypto");
  return nodeCrypto.createHash("sha256").update(blob).digest("hex");
}

/** Refuse the broadcast when sim and broadcast calldata diverge. */
export function assertCalldataMatch(
  simHash: string,
  broadcastHash: string,
): void {
  if (!simHash || !broadcastHash) {
    throw new CalldataHashMismatchError(simHash || "<empty>", broadcastHash || "<empty>");
  }
  if (normalizeHash(simHash) !== normalizeHash(broadcastHash)) {
    throw new CalldataHashMismatchError(simHash, broadcastHash);
  }
}

/**
 * Wrap `wallet.sendTransaction` with a hash-bind check. Computes the
 * broadcast-side hash, compares it to the artifact's simulated hash,
 * and only forwards to the wallet popup when they match. The wallet
 * popup is therefore guaranteed to display the same calldata bytes the
 * user previewed in the Confirm panel.
 */
export async function signWithHashBind(
  artifact: SimulatedArtifact,
  tx: BroadcastTx,
): Promise<string> {
  const broadcastHash = await computeCalldataHash(tx);
  assertCalldataMatch(artifact.simulated_calldata_hash, broadcastHash);
  return sendTransaction(tx);
}
