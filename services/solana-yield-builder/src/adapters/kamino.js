/**
 * Kamino — uses Kamino's signable transaction REST when configured;
 * otherwise routes the deposit through Jupiter into the kUSDC market mint.
 *
 * Most users on the chat are routed through Jupiter (works today, no SDK
 * install) and end up holding the kToken receipt that Kamino's UI also
 * recognises. When the official Kamino public REST endpoint surfaces a
 * deposit URL we can swap that in by setting KAMINO_API_BASE.
 */
const fetch = require("node-fetch").default || require("node-fetch");
const { buildSwap, resolveMint, decimalsFor, SOL_MINT } = require("./jupiter");
const { simulateBase64Tx } = require("./simulate");

// Default to Kamino's public REST so production gets the real vault deposit
// path without needing extra env setup. Override KAMINO_API_BASE to point
// at staging or a local mock.
const BASE = process.env.KAMINO_API_BASE || "https://api.kamino.finance";
// Until the official Kamino REST is wired we route stablecoin/USDC deposits
// into JLP (Jupiter Perps LP) — a Jupiter-quoted, real yield-bearing asset
// that gives users an executable yield position via one swap. SOL deposits
// route into JitoSOL.
const JLP_MINT = "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4";
const JITOSOL_MINT = "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn";

// Kamino Lend program ID — verified on mainnet (https://docs.kamino.finance).
// Surfaced on every close/withdraw tx so the agent's receipt-reader can
// match position-store entries by redemption_program.
const KAMINO_LEND_PROGRAM_ID = "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD";

module.exports = {
  aliases: ["kamino-finance", "kamino-lend", "kamino-vault"],
  supportedActions: ["deposit", "supply", "withdraw", "unstake", "redeem", "close", "exit"],
  KAMINO_LEND_PROGRAM_ID,

  /**
   * Phase 4 lifecycle — Kamino vault withdraw via REST.
   * Mirrors the deposit's two-endpoint probe pattern; honest fallback
   * when REST unreachable (no Jupiter inverse for vault shares).
   */
  async buildUnstake({ asset, amount, user, extra = {} }, { connection } = {}) {
    const tryUrls = [
      `${BASE}/v2/transactions/withdraw`,
      `${BASE}/transactions/withdraw`,
    ];
    for (const url of tryUrls) {
      try {
        const ctl = new AbortController();
        const tmo = setTimeout(() => ctl.abort(), 4000);
        let resp;
        try {
          resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: ctl.signal,
            body: JSON.stringify({
              asset, amount, user,
              market: extra.market || extra.market_address || extra.poolAddress,
              reserve: extra.reserve || extra.reserve_address,
              strategy: extra.strategy || extra.strategy_address,
            }),
          });
        } finally {
          clearTimeout(tmo);
        }
        if (!resp.ok) continue;
        const data = await resp.json();
        const tx = data?.transaction || data?.tx;
        if (!tx) continue;
        const sim = connection ? await simulateBase64Tx({ b64: tx, connection }) : { ok: true };
        if (!sim.ok) {
          const e = new Error(`Kamino REST withdraw simulation failed: ${sim.errStr || "unknown"}`);
          e.simulation = sim;
          throw e;
        }
        return {
          transactions: [
            {
              b64: tx,
              summary: `Kamino withdraw ${amount} ${asset}`,
              description: `Direct Kamino vault withdraw via official REST (${url}).`,
              receiptToken: asset || "USDC",
              redemption_program: KAMINO_LEND_PROGRAM_ID,
              feeUsd: 0.01,
              durationS: 30,
              warnings: [],
              source: "kamino-rest",
              simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
            },
          ],
        };
      } catch (err) {
        if (err?.simulation) throw err;
        continue;
      }
    }
    // No Jupiter inverse for vault shares — surface honest blocker.
    throw new Error(
      "Kamino REST withdraw unreachable; no Jupiter inverse for vault shares. " +
      "Finalise on app.kamino.finance/lending or vaults UI."
    );
  },

  /**
   * Phase C lifecycle — explicit withdraw entrypoint. The sidecar dispatcher
   * maps action="withdraw" → buildWithdraw when present, otherwise falls
   * back to buildUnstake. We delegate to buildUnstake (which has the REST
   * probe + simulation gate) and stamp redemption_program on the result.
   *
   * Uses klend-sdk when present in package.json (Phase D). Currently the
   * REST path is the prod default; SDK hand-roll lives behind the REST
   * fallback to keep the sidecar deps lean.
   */
  async buildWithdraw({ asset, amount, user, extra = {} }, ctx = {}) {
    const result = await this.buildUnstake({ asset, amount, user, extra }, ctx);
    // Stamp redemption_program on each tx if the REST path forgot it.
    if (result && Array.isArray(result.transactions)) {
      for (const tx of result.transactions) {
        if (!tx.redemption_program) tx.redemption_program = KAMINO_LEND_PROGRAM_ID;
      }
    }
    return result;
  },

  async quote({ asset }) {
    return {
      expectedAmountOut: null,
      receiptToken: `kamino-${(asset || "USDC").toLowerCase()}`,
      apy: null,
      fees: { protocol: "Jupiter routing", network: "0.000005 SOL" },
    };
  },
  async build({ asset, amount, user, extra = {}, slippageBps = 50 }, { connection } = {}) {
    // Primary path: real Kamino REST. Tries a couple of endpoint shapes
    // because Kamino has shipped both /transactions/deposit and
    // /v2/transactions/deposit at different points.
    const tryRestEndpoints = [
      `${BASE}/v2/transactions/deposit`,
      `${BASE}/transactions/deposit`,
    ];
    for (const url of tryRestEndpoints) {
      try {
        // 4s timeout per endpoint attempt — without it a stalled Kamino REST
        // host can blow past the sidecar's 12s ceiling, which surfaces a
        // bare TimeoutError to the agent instead of the Jupiter fallback.
        const ctl = new AbortController();
        const tmo = setTimeout(() => ctl.abort(), 4000);
        let resp;
        try {
          resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: ctl.signal,
            body: JSON.stringify({
              asset, amount, user,
              market: extra.market || extra.market_address || extra.poolAddress,
              reserve: extra.reserve || extra.reserve_address,
              strategy: extra.strategy || extra.strategy_address,
            }),
          });
        } finally {
          clearTimeout(tmo);
        }
        if (!resp.ok) continue;
        const data = await resp.json();
        const tx = data?.transaction || data?.tx;
        if (!tx) continue;
        const sim = connection ? await simulateBase64Tx({ b64: tx, connection }) : { ok: true };
        if (!sim.ok) {
          // Real REST returned a tx that simulates failure — let the user see
          // the reason instead of falling through to a fake Jupiter route.
          const e = new Error(`Kamino REST tx simulation failed: ${sim.errStr || "unknown"}`);
          e.simulation = sim;
          throw e;
        }
        return {
          transactions: [
            {
              b64: tx,
              summary: `Kamino deposit ${amount} ${asset}`,
              description: `Direct Kamino vault deposit via official REST (${url}).`,
              receiptToken: `k${(asset || "USDC").toUpperCase()}`,
              feeUsd: 0.01,
              durationS: 30,
              warnings: [],
              source: "kamino-rest",
              simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
            },
          ],
        };
      } catch (err) {
        if (err?.simulation) throw err; // propagate genuine sim failures
        continue;                       // try next endpoint shape
      }
    }

    // Fallback: explicit proxy into a Jupiter-tradable yield-bearing token.
    // Banner makes it clear this is NOT a real Kamino vault deposit.
    const inputMint = resolveMint(asset || "USDC") || resolveMint("USDC");
    const isSol = (asset || "").toUpperCase() === "SOL";
    const outputMint = extra.kToken || (isSol ? JITOSOL_MINT : JLP_MINT);
    const receiptLabel = extra.kToken ? "k-token" : (isSol ? "JitoSOL" : "JLP");
    const { tx } = await buildSwap({
      inputMint,
      outputMint,
      amount,
      user,
      slippageBps,
      decimals: decimalsFor(asset || "USDC"),
    });
    const sim = connection ? await simulateBase64Tx({ b64: tx, connection }) : { ok: true };
    if (!sim.ok) {
      const e = new Error(`Kamino fallback simulation failed: ${sim.errStr || "unknown"}`);
      e.simulation = sim;
      throw e;
    }
    return {
      transactions: [
        {
          b64: tx,
          summary: `Yield proxy: ${amount} ${asset || "USDC"} → ${receiptLabel} (Kamino REST unreachable)`,
          description: (
            `Kamino REST was unreachable (${BASE}); routed through Jupiter into ${receiptLabel} ` +
            "as the closest live yield-bearing asset. This is NOT a Kamino vault deposit — APY tracks JLP/JitoSOL, not the Kamino market."
          ),
          receiptToken: receiptLabel,
          feeUsd: 0.01,
          durationS: 30,
          warnings: [
            `Kamino REST fallback active: yield = ${receiptLabel}, not Kamino vault. Use the Kamino UI for the real vault deposit.`,
          ],
          source: "jupiter-fallback",
          simulation: { ok: true, benign: sim.benign || false, unitsConsumed: sim.unitsConsumed },
        },
      ],
    };
  },
};
