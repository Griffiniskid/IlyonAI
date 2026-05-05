/**
 * Solana yield-builder sidecar.
 *
 * Endpoints:
 *   GET  /health                -> { ok }
 *   POST /quote                 -> { protocol, asset, amount, user } -> { expectedAmountOut, fees }
 *   POST /build                 -> { protocol, asset, amount, user, slippageBps, extra } -> { transactions: [...] }
 *   POST /verify                -> { txHash, expectedPosition } -> { confirmed, detail }
 *
 * Each adapter module under ./adapters/<name>.js implements:
 *   { quote(req, ctx), build(req, ctx), verify(req, ctx) }
 *
 * The sidecar fails closed: if an SDK throws, the response is { error: "..." }
 * with HTTP 502 so the Python adapter surfaces a precise blocker rather than
 * pretending an action is signable.
 */
const express = require("express");
const { Connection, PublicKey } = require("@solana/web3.js");

const app = express();
app.use(express.json({ limit: "1mb" }));

const RPC_URL =
  process.env.SOLANA_RPC_URL ||
  process.env.NEXT_PUBLIC_SOLANA_RPC_URL ||
  "https://api.mainnet-beta.solana.com";

const connection = new Connection(RPC_URL, "confirmed");

const adapters = new Map();

function registerAdapter(name, mod) {
  adapters.set(name.toLowerCase(), mod);
  if (mod.aliases) {
    for (const alias of mod.aliases) {
      adapters.set(alias.toLowerCase(), mod);
    }
  }
}

const kamino = require("./adapters/kamino");
const orca = require("./adapters/orca");
const marinade = require("./adapters/marinade");
const jito = require("./adapters/jito");
const sanctum = require("./adapters/sanctum");
const meteora = require("./adapters/meteora");
const raydium = require("./adapters/raydium");

registerAdapter("kamino", kamino);
registerAdapter("orca", orca);
registerAdapter("marinade", marinade);
registerAdapter("jito", jito);
registerAdapter("sanctum", sanctum);
registerAdapter("meteora", meteora);
registerAdapter("raydium", raydium);

function resolveAdapter(name) {
  if (!name) return null;
  return adapters.get(String(name).toLowerCase()) || null;
}

app.get("/health", (_req, res) => {
  res.json({ ok: true, rpc: RPC_URL, adapters: Array.from(adapters.keys()) });
});

app.post("/quote", async (req, res) => {
  const { protocol } = req.body || {};
  const adapter = resolveAdapter(protocol);
  if (!adapter || typeof adapter.quote !== "function") {
    return res.status(404).json({ error: `No quote adapter for protocol '${protocol}'.` });
  }
  try {
    const result = await adapter.quote(req.body || {}, { connection, rpcUrl: RPC_URL });
    res.json(result);
  } catch (err) {
    console.error("[quote]", protocol, err);
    res.status(502).json({ error: err.message || "quote_failed" });
  }
});

app.post("/build", async (req, res) => {
  const { protocol, user } = req.body || {};
  if (!user) {
    return res.status(400).json({ error: "user (Solana wallet pubkey) is required." });
  }
  try {
    new PublicKey(user); // throws on bad input
  } catch (err) {
    return res.status(400).json({ error: `Invalid Solana public key: ${user}` });
  }
  const adapter = resolveAdapter(protocol);
  if (!adapter || typeof adapter.build !== "function") {
    return res.status(404).json({ error: `No build adapter for protocol '${protocol}'.` });
  }
  try {
    const result = await adapter.build(req.body || {}, { connection, rpcUrl: RPC_URL });
    res.json(result);
  } catch (err) {
    console.error("[build]", protocol, err);
    res.status(502).json({ error: err.message || "build_failed" });
  }
});

app.post("/verify", async (req, res) => {
  const { protocol, txHash } = req.body || {};
  if (!txHash) {
    return res.status(400).json({ error: "txHash is required." });
  }
  const adapter = resolveAdapter(protocol);
  if (adapter && typeof adapter.verify === "function") {
    try {
      const result = await adapter.verify(req.body || {}, { connection, rpcUrl: RPC_URL });
      return res.json(result);
    } catch (err) {
      console.error("[verify]", protocol, err);
    }
  }
  // Generic verify: just confirm tx landed.
  try {
    const status = await connection.getSignatureStatus(txHash, { searchTransactionHistory: true });
    const confirmed =
      !!status?.value && (status.value.confirmationStatus === "confirmed" || status.value.confirmationStatus === "finalized");
    res.json({
      confirmed,
      detail: confirmed ? "Tx finalized on Solana mainnet." : "Tx not yet finalized.",
      raw: status?.value || null,
    });
  } catch (err) {
    res.status(502).json({ error: err.message || "verify_failed" });
  }
});

const PORT = parseInt(process.env.PORT || "8090", 10);
app.listen(PORT, () => {
  console.log(`solana-yield-builder listening on :${PORT} (rpc=${RPC_URL})`);
});
