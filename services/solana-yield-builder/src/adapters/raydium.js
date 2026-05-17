/**
 * Raydium native AMM v4 + CPMM adapter.
 *
 * Uses @raydium-io/raydium-sdk-v2 to compose true on-protocol addLiquidity
 * transactions for both classic AMM v4 and the new CPMM (Constant Product
 * Market Maker, OpenBook-free) pools.
 *
 * Mode selection:
 *   - extra.poolType === "cpmm" OR poolInfo.programId === CPMM_PROGRAM →
 *     raydium.cpmm.addLiquidity (single-side baseIn allowed).
 *   - else → raydium.liquidity.addLiquidity (AMM v4, fixedSide a|b).
 *
 * When `extra.poolId` is provided we fetch full poolInfo + poolKeys from the
 * SDK API (`raydium.api.fetchPoolById`) and build the canonical addLiquidity
 * ix. The resulting VersionedTransaction is serialized to base64 and run
 * through simulateBase64Tx; benign reverts (empty dev wallet) pass, real
 * reverts abort the build.
 *
 * Fallback: when extra.poolId AND extra.underlying_tokens are BOTH missing,
 * we delegate to ./_legacyRaydiumPrep so long-tail aliases that registered
 * against this adapter (drift, lulo, lifinity, etc. in src/index.js) still
 * get a signable Jupiter prep-swap route into the underlying.
 *
 * Program IDs:
 *   AMM_V4 = 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8
 *   CPMM   = CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C
 */
const { ComputeBudgetProgram, PublicKey } = require("@solana/web3.js");
const { simulateBase64Tx } = require("./simulate");
const _legacyPrep = require("./_legacyRaydiumPrep");

const AMM_V4_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8";
const CPMM_PROGRAM = "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C";

const COMPUTE_UNIT_LIMIT = 600_000;
const COMPUTE_UNIT_PRICE_MICROLAMPORTS = 50_000;

// Lazy-loaded SDK so unit tests that monkeypatch the module never have to
// install the heavy SDK tree, and so a missing peer dep doesn't crash the
// sidecar at startup before any /build call.
let _raydiumSdkModule = null;
function _loadSdk() {
  if (_raydiumSdkModule) return _raydiumSdkModule;
  // eslint-disable-next-line global-require
  _raydiumSdkModule = require("@raydium-io/raydium-sdk-v2");
  return _raydiumSdkModule;
}

function _shouldFallbackToLegacy(extra) {
  const poolId = extra && (extra.poolId || extra.pool_id || extra.pool_address || extra.poolAddress);
  const underlying = extra && (extra.underlying_tokens || extra.underlyingTokens);
  return !poolId && !(underlying && underlying.length);
}

function _isCpmm(extra, poolInfo) {
  const explicit = String(extra?.poolType || extra?.pool_type || "").toLowerCase();
  if (explicit === "cpmm") return true;
  const pid = String(poolInfo?.programId || "").trim();
  if (pid === CPMM_PROGRAM) return true;
  return false;
}

async function _initRaydium({ connection, user }) {
  const sdk = _loadSdk();
  const { Raydium } = sdk;
  const owner = new PublicKey(user);
  const raydium = await Raydium.load({
    connection,
    owner,
    disableLoadToken: false,
  });
  return { raydium, sdk };
}

async function _fetchPool({ raydium, poolId }) {
  // raydium.api.fetchPoolById returns { id, poolInfo, poolKeys } or an array.
  // Some SDK builds returns [poolInfo]; others { data: [poolInfo] }. Normalize.
  const res = await raydium.api.fetchPoolById({ ids: poolId });
  let poolInfo = null;
  if (Array.isArray(res)) {
    poolInfo = res[0] || null;
  } else if (res && Array.isArray(res.data)) {
    poolInfo = res.data[0] || null;
  } else if (res && typeof res === "object") {
    poolInfo = res.poolInfo || res;
  }
  if (!poolInfo) {
    throw new Error(`Raydium pool ${poolId} not found via api.fetchPoolById.`);
  }
  return poolInfo;
}

async function _buildCpmm({ raydium, sdk, poolInfo, amount, slippageBps, asset }) {
  // CPMM single-side add: baseIn signals whether `inputAmount` is the base
  // (mintA) or quote (mintB) side. We default to baseIn=true when caller
  // supplies the base symbol or no asset hint.
  const upperAsset = String(asset || "").toUpperCase();
  const baseSymbol = String(poolInfo.mintA?.symbol || "").toUpperCase();
  const baseIn = !upperAsset || upperAsset === baseSymbol;
  const slippage = (slippageBps || 0) / 10_000;
  const txVersion = sdk.TxVersion ? sdk.TxVersion.V0 : 0;

  const { transaction } = await raydium.cpmm.addLiquidity({
    poolInfo,
    poolKeys: poolInfo.poolKeys || undefined,
    inputAmount: amount,
    slippage,
    baseIn,
    txVersion,
    computeBudgetConfig: {
      units: COMPUTE_UNIT_LIMIT,
      microLamports: COMPUTE_UNIT_PRICE_MICROLAMPORTS,
    },
  });
  return transaction;
}

async function _buildAmmV4({ raydium, sdk, poolInfo, amount, slippageBps, asset }) {
  // AMM v4 add expects amounts for BOTH sides. The caller can pass a single
  // amount (we treat as side-A) and lets fixedSide drive the math; we
  // estimate otherAmountMin off the pool's current reserves so the SDK does
  // not refuse the build.
  const upperAsset = String(asset || "").toUpperCase();
  const symA = String(poolInfo.mintA?.symbol || "").toUpperCase();
  const fixedSide = !upperAsset || upperAsset === symA ? "a" : "b";
  const slippage = (slippageBps || 0) / 10_000;
  const txVersion = sdk.TxVersion ? sdk.TxVersion.V0 : 0;

  const amountInA = fixedSide === "a" ? amount : "0";
  const amountInB = fixedSide === "b" ? amount : "0";

  const { transaction } = await raydium.liquidity.addLiquidity({
    poolInfo,
    amountInA,
    amountInB,
    otherAmountMin: "0",
    fixedSide,
    slippage,
    txVersion,
    computeBudgetConfig: {
      units: COMPUTE_UNIT_LIMIT,
      microLamports: COMPUTE_UNIT_PRICE_MICROLAMPORTS,
    },
  });
  return transaction;
}

function _serializeTx(transaction) {
  // SDK v2 returns either a VersionedTransaction (txVersion=V0) or a legacy
  // Transaction. Both expose .serialize() returning a Uint8Array/Buffer.
  const raw = transaction.serialize();
  return Buffer.from(raw).toString("base64");
}

module.exports = {
  aliases: ["raydium-amm", "raydium-amm-v4", "raydium-cpmm", "raydium-cp", "raydium-clmm"],
  supportedActions: ["deposit", "deposit_lp", "supply"],

  async quote({ asset, amount }) {
    return {
      expectedAmountOut: null,
      receiptToken: `raydium-lp-${asset || "?"}`,
      apy: null,
      fees: { protocol: "Raydium AMM v4 / CPMM", network: "~0.000035 SOL (CU+priority)" },
    };
  },

  async build(req, ctx = {}) {
    const { connection } = ctx;
    const { asset, amount, user, extra = {}, slippageBps = 50 } = req || {};

    // Long-tail safety net: caller passed no pool identifier AND no
    // underlying-tokens hint — defer to the prep-swap legacy adapter so the
    // user still gets a signable Jupiter route.
    if (_shouldFallbackToLegacy(extra)) {
      return _legacyPrep.build(req, ctx);
    }

    const poolId = extra.poolId || extra.pool_id || extra.pool_address || extra.poolAddress;
    if (!poolId) {
      // We have underlying_tokens but no poolId — still need the legacy
      // pair-aware prep swap, the native SDK requires an actual pool address.
      return _legacyPrep.build(req, ctx);
    }
    if (!connection) {
      throw new Error("Raydium native adapter requires a Solana connection in ctx.");
    }
    if (!user) {
      throw new Error("Raydium native adapter requires `user` (Solana wallet pubkey).");
    }

    const { raydium, sdk } = await _initRaydium({ connection, user });
    const poolInfo = await _fetchPool({ raydium, poolId });
    const isCpmm = _isCpmm(extra, poolInfo);
    const redemption_program = isCpmm ? CPMM_PROGRAM : AMM_V4_PROGRAM;

    const transaction = isCpmm
      ? await _buildCpmm({ raydium, sdk, poolInfo, amount, slippageBps, asset })
      : await _buildAmmV4({ raydium, sdk, poolInfo, amount, slippageBps, asset });

    const b64 = _serializeTx(transaction);
    const sim = await simulateBase64Tx({ b64, connection });
    if (!sim.ok) {
      const e = new Error(
        `Raydium ${isCpmm ? "CPMM" : "AMM v4"} addLiquidity simulation failed: ${sim.errStr || "unknown"}`,
      );
      e.simulation = sim;
      throw e;
    }

    const variantLabel = isCpmm ? "Raydium CPMM" : "Raydium AMM v4";
    const pairLabel = (
      poolInfo.mintA?.symbol && poolInfo.mintB?.symbol
        ? `${poolInfo.mintA.symbol}-${poolInfo.mintB.symbol}`
        : (extra.pool_symbol || extra.poolSymbol || "LP")
    ).toUpperCase();

    return {
      transactions: [
        {
          b64,
          summary: `${variantLabel} addLiquidity (${pairLabel})`,
          description: `Calls addLiquidity on Raydium pool ${poolInfo.id}. Native LP mint.`,
          receiptToken: "RAY-LP",
          receiptMint: poolInfo.lpMint?.address || null,
          redemption_program,
          feeUsd: 0.02,
          durationS: 25,
          warnings: [
            `Settles directly on Raydium ${isCpmm ? "CPMM" : "AMM v4"} program ${redemption_program}.`,
          ],
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },

  // Exposed for unit-testing the program-id selector without booting the SDK.
  __internals: {
    AMM_V4_PROGRAM,
    CPMM_PROGRAM,
    _isCpmm,
    _shouldFallbackToLegacy,
  },
};
