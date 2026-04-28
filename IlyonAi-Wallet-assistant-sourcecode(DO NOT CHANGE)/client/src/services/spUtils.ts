import { Client, SpStatus } from '@bnb-chain/greenfield-js-sdk';
import { ReedSolomon } from '@bnb-chain/reed-solomon';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type GreenfieldClient = ReturnType<typeof Client.create>;

/** Raw SP shape returned by client.sp.getStorageProviders() */
export interface StorageProvider {
  operatorAddress: string;
  endpoint: string;
  sealAddress: string;
  approvalAddress: string;
  gcAddress: string;
  status: SpStatus;
  description: {
    moniker: string;
    identity: string;
    website: string;
    details: string;
  };
}

/** An active SP augmented with the measured probe latency */
export interface SpCandidate {
  operatorAddress: string;
  endpoint: string;
  name: string;
  latencyMs: number;
}

/** Output of computeChecksums — ready to pass straight to createObject() */
export interface ChecksumResult {
  /** Base64-encoded Reed-Solomon segment checksums for `expectChecksums` */
  expectChecksums: string[];
  /** Exact byte length for `payloadSize` (Long.fromNumber-ready) */
  payloadSize: number;
}

// ---------------------------------------------------------------------------
// Step 1 — Fetch active Storage Providers
// ---------------------------------------------------------------------------

/**
 * Returns only the SPs that are currently `STATUS_IN_SERVICE`.
 * All other statuses (maintenance, jailed, graceful-exiting) are excluded.
 */
export async function getActiveStorageProviders(
  client: GreenfieldClient,
): Promise<StorageProvider[]> {
  const { storageProviders } = await client.sp.getStorageProviders();

  return (storageProviders as StorageProvider[]).filter(
    (sp) => sp.status === SpStatus.STATUS_IN_SERVICE,
  );
}

// ---------------------------------------------------------------------------
// Step 2 — Select the optimal SP
// ---------------------------------------------------------------------------

/** Milliseconds to wait before declaring an SP endpoint unreachable */
const PROBE_TIMEOUT_MS = 3_000;

/**
 * Probes `endpoint` with a HEAD request and returns the round-trip latency.
 * Resolves to `null` if the request times out or fails.
 */
async function probeLatency(endpoint: string): Promise<number | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  const start = performance.now();

  try {
    // Greenfield SPs expose a REST gateway; a HEAD to the root is lightweight
    await fetch(endpoint, {
      method: 'HEAD',
      signal: controller.signal,
    });
    return Math.round(performance.now() - start);
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Probes all active SPs in parallel and returns the one with the lowest
 * measured latency.  Falls back to the first SP in the list if every probe
 * fails (e.g. CORS blocks all HEAD requests in the extension context).
 *
 * @throws if there are no active SPs at all.
 */
export async function selectOptimalSp(
  client: GreenfieldClient,
): Promise<SpCandidate> {
  const activeSps = await getActiveStorageProviders(client);

  if (activeSps.length === 0) {
    throw new Error('No active Greenfield storage providers found on-chain');
  }

  // Probe all SPs concurrently
  const probeResults = await Promise.all(
    activeSps.map(async (sp) => ({
      sp,
      latencyMs: await probeLatency(sp.endpoint),
    })),
  );

  // Keep only reachable SPs, sort by latency ascending
  const reachable = probeResults
    .filter((r): r is { sp: StorageProvider; latencyMs: number } =>
      r.latencyMs !== null,
    )
    .sort((a, b) => a.latencyMs - b.latencyMs);

  // If all probes failed (e.g. CORS) fall back to first in-service SP
  const best = reachable[0] ?? { sp: activeSps[0], latencyMs: -1 };

  return {
    operatorAddress: best.sp.operatorAddress,
    endpoint: best.sp.endpoint,
    name: best.sp.description.moniker,
    latencyMs: best.latencyMs,
  };
}

// ---------------------------------------------------------------------------
// Step 3 — Reed-Solomon checksum calculation
// ---------------------------------------------------------------------------

/**
 * Encodes `data` with Reed-Solomon and converts the resulting segment hashes
 * to the base64 strings expected by `createObject({ expectChecksums })`.
 *
 * Greenfield's EC-4+2 scheme produces 7 checksums:
 *   [0-3] = data segment SHA256s
 *   [4-5] = parity segment SHA256s
 *   [6]   = combined root hash
 *
 * The spread-operator approach (`btoa(String.fromCharCode(...bytes))`) is
 * avoided here because it can overflow the call stack for large segments.
 */
export async function computeChecksums(data: Uint8Array): Promise<ChecksumResult> {
  const rs = new ReedSolomon();
  const segments: Uint8Array[] = await rs.encode(data);

  const expectChecksums = segments.map(uint8ArrayToBase64);

  return {
    expectChecksums,
    payloadSize: data.byteLength,
  };
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function uint8ArrayToBase64(bytes: Uint8Array): string {
  let binary = '';
  // Iterate manually — avoids stack overflow from spread on large arrays
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}
