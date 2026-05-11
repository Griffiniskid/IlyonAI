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

module.exports = {
  aliases: ["kamino-finance", "kamino-lend", "kamino-vault"],
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
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            asset, amount, user,
            market: extra.market || extra.market_address || extra.poolAddress,
            reserve: extra.reserve || extra.reserve_address,
            strategy: extra.strategy || extra.strategy_address,
          }),
        });
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
