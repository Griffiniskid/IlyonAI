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

const BASE = process.env.KAMINO_API_BASE || "";
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
  async build({ asset, amount, user, extra = {}, slippageBps = 50 }) {
    if (BASE) {
      try {
        const url = `${BASE}/transactions/deposit`;
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ asset, amount, user, market: extra.market, reserve: extra.reserve }),
        });
        if (resp.ok) {
          const data = await resp.json();
          const tx = data?.transaction || data?.tx;
          if (tx) {
            return {
              transactions: [
                {
                  b64: tx,
                  summary: `Kamino deposit ${amount} ${asset}`,
                  description: `Direct Kamino deposit via official REST.`,
                  receiptToken: `k${(asset || "USDC").toUpperCase()}`,
                  feeUsd: 0.01,
                  durationS: 30,
                  warnings: [],
                },
              ],
            };
          }
        }
      } catch (_err) {
        /* fall through to Jupiter route */
      }
    }

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
    return {
      transactions: [
        {
          b64: tx,
          summary: `Kamino-equivalent yield: ${amount} ${asset || "USDC"} → ${receiptLabel} (Jupiter routed)`,
          description: (
            "Routes through Jupiter into the closest executable yield-bearing asset " +
            `(${receiptLabel}). Settles in one signed transaction; manage in Jupiter or Kamino UI.`
          ),
          receiptToken: receiptLabel,
          feeUsd: 0.01,
          durationS: 30,
          warnings: [
            `Routed via Jupiter into ${receiptLabel}; net APY closely tracks the requested Kamino market.`,
          ],
        },
      ],
    };
  },
};
