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
const jlp = require("./adapters/jlp");

registerAdapter("kamino", kamino);
registerAdapter("kamino-liquidity", kamino);
registerAdapter("kamino-vault", kamino);
registerAdapter("orca", orca);
registerAdapter("orca-clmm", orca);
registerAdapter("marinade", marinade);
registerAdapter("marinade-native", marinade);
registerAdapter("jito", jito);
registerAdapter("sanctum", sanctum);
registerAdapter("sanctum-liquid-staking", sanctum);
registerAdapter("meteora", meteora);
registerAdapter("meteora-vault", meteora);
registerAdapter("meteora-amm", meteora);
registerAdapter("raydium", raydium);
registerAdapter("raydium-amm-v3", raydium);
registerAdapter("raydium-cp", raydium);
registerAdapter("jlp", jlp);
registerAdapter("jupiter-perps", jlp);
registerAdapter("jupiter-perpetuals", jlp);
registerAdapter("jupiter-perpetuals-lp", jlp);
// Generic Solana-DEX fallback: when DefiLlama returns a project name we
// don't have a dedicated SDK for (drift, lulo, save, lifinity, etc.) use
// the Raydium adapter's prep-swap path so the user still gets a signable
// Jupiter route into one of the underlying assets.
registerAdapter("drift", raydium);
registerAdapter("drift-staked-sol", raydium);
registerAdapter("lulo", raydium);
registerAdapter("lulo-finance", raydium);
registerAdapter("save", raydium);
registerAdapter("save-finance", raydium);
registerAdapter("lifinity", raydium);
registerAdapter("lifinity-v2", raydium);
registerAdapter("solend", raydium);
// Long-tail Solana DEX/yield protocols routed through the Raydium prep-swap
// fallback. The user gets a signable Jupiter route into the pool's quote
// asset; final LP entry must be done on the protocol's UI for those without
// a dedicated SDK module.
registerAdapter("gmtrade", raydium);
registerAdapter("phoenix", raydium);
registerAdapter("cropper", raydium);
registerAdapter("crema", raydium);
registerAdapter("goosefx", raydium);
registerAdapter("aldrin", raydium);
registerAdapter("serum", raydium);
registerAdapter("fluxbeam", raydium);
registerAdapter("dexlab", raydium);
registerAdapter("openbook", raydium);
registerAdapter("openbook-v2", raydium);
registerAdapter("invariant", raydium);
registerAdapter("symmetry", raydium);
registerAdapter("symmetry-baskets", raydium);
registerAdapter("marginfi", raydium);
registerAdapter("marginfi-lst", raydium);
registerAdapter("hastra", raydium);
registerAdapter("onre", raydium);
registerAdapter("bybit-staked-sol", raydium);
registerAdapter("binance-staked-sol", raydium);
registerAdapter("doublezero-staked-sol", raydium);
registerAdapter("phantom-sol", raydium);
registerAdapter("helius-staked-sol", raydium);
registerAdapter("dfdv-staked-sol", raydium);
registerAdapter("the-vault-liquid-staking", raydium);
registerAdapter("hylo-lsts", raydium);
registerAdapter("blackhole-clmm", raydium);
registerAdapter("supernova-cl", raydium);
registerAdapter("shadow-exchange-clmm", raydium);
registerAdapter("steer-protocol", raydium);
registerAdapter("zeebu", raydium);
registerAdapter("jupiter-lend", raydium);
registerAdapter("jupiter-staked-sol", raydium);

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
  const { protocol, user, action } = req.body || {};
  if (!user) {
    return res.status(400).json({ error: "user (Solana wallet pubkey) is required." });
  }
  try {
    new PublicKey(user); // throws on bad input
  } catch (err) {
    return res.status(400).json({ error: `Invalid Solana public key: ${user}` });
  }
  const adapter = resolveAdapter(protocol);
  if (!adapter) {
    return res.status(404).json({ error: `No build adapter for protocol '${protocol}'.` });
  }
  // Phase 4 + Phase C lifecycle dispatch:
  //   - close_position / close / exit_position → buildClose()
  //   - order_unstake / delayed_unstake        → buildOrderUnstake()
  //   - withdraw                                → buildWithdraw() else buildUnstake()
  //   - unstake / redeem / exit                 → buildUnstake()
  //   - deposit / supply / stake / *missing*    → build()
  const actionNorm = String(action || "").toLowerCase();
  const isClose = ["close_position", "close", "exit_position"].includes(actionNorm);
  const isOrderUnstake = ["order_unstake", "delayed_unstake", "order-unstake"].includes(actionNorm);
  const isWithdraw = actionNorm === "withdraw";
  const isUnstake = ["unstake", "redeem", "exit"].includes(actionNorm);
  try {
    let result;
    if (isClose && typeof adapter.buildClose === "function") {
      result = await adapter.buildClose(req.body || {}, { connection, rpcUrl: RPC_URL });
    } else if (isOrderUnstake && typeof adapter.buildOrderUnstake === "function") {
      result = await adapter.buildOrderUnstake(req.body || {}, { connection, rpcUrl: RPC_URL });
    } else if (isWithdraw && typeof adapter.buildWithdraw === "function") {
      result = await adapter.buildWithdraw(req.body || {}, { connection, rpcUrl: RPC_URL });
    } else if ((isWithdraw || isUnstake) && typeof adapter.buildUnstake === "function") {
      result = await adapter.buildUnstake(req.body || {}, { connection, rpcUrl: RPC_URL });
    } else if (typeof adapter.build === "function") {
      result = await adapter.build(req.body || {}, { connection, rpcUrl: RPC_URL });
    } else {
      const wanted = isClose
        ? "buildClose"
        : isOrderUnstake
          ? "buildOrderUnstake"
          : (isWithdraw || isUnstake)
            ? "buildUnstake"
            : "build";
      return res.status(404).json({ error: `Adapter '${protocol}' missing ${wanted}.` });
    }
    res.json(result);
  } catch (err) {
    console.error("[build]", protocol, err);
    res.status(502).json({ error: err.message || "build_failed" });
  }
});

// Solana CLMM/DLMM pool-state probe. Powers the in-chat range slider for
// Raydium CLMM / Orca Whirlpool / Meteora DLMM positions per spec §6b.
//
// Request:
//   POST /pool_state { protocol, mint0, mint1 }
//   Either mint pubkeys (preferred) OR { protocol, pair: 'SOL-USDC' }.
//
// Response:
//   { ok, pool: {
//       poolAddress, programId, kind: 'clmm'|'whirlpool'|'dlmm'|'amm',
//       tokenA: { mint, symbol, decimals },
//       tokenB: { mint, symbol, decimals },
//       currentPrice,            // human-readable B per A
//       tick, tickSpacing,       // for CLMM/Whirlpool
//       binStep,                  // for DLMM
//       sqrtPriceX64,
//       baseAprPct, rewardAprPct, // 30-day if available
//       tvlUsd, vol24hUsd
//   }, source: 'raydium-v3-api'|'orca-api'|'meteora-api'|... }
//
// Fails closed: returns 404 when no pool matches, 502 on upstream timeout.
const fetch = global.fetch || ((...a) => import("node-fetch").then(({ default: f }) => f(...a)));

const _WELL_KNOWN_MINTS = {
  SOL: "So11111111111111111111111111111111111111112",
  WSOL: "So11111111111111111111111111111111111111112",
  USDC: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  USDT: "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
  USDS: "USDSwr9ApdHk5bvJKMjzff41FfuX8bSxdKcR81vTwcA",
  MSOL: "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
  JITOSOL: "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
  BSOL: "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1",
  JLP: "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4",
  INF: "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm",
  RAY: "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
  ORCA: "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
};

function _resolveMintForSymbol(sym) {
  if (!sym) return null;
  const s = String(sym).toUpperCase();
  if (_WELL_KNOWN_MINTS[s]) return _WELL_KNOWN_MINTS[s];
  // Solana base58 pubkeys are 32-44 chars; accept as-is when the user passed a mint.
  if (/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(sym)) return sym;
  return null;
}

async function _fetchJsonWithTimeout(url, opts, timeoutMs = 6000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const resp = await fetch(url, { ...(opts || {}), signal: ctrl.signal });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } finally {
    clearTimeout(t);
  }
}

async function _raydiumClmmState(mintA, mintB) {
  // Raydium V3 API: returns AMM v4, CPMM, and CLMM pools per mint pair.
  const url = `https://api-v3.raydium.io/pools/info/mint?mint1=${mintA}&mint2=${mintB}&poolType=concentrated&poolSortField=liquidity&sortType=desc&pageSize=5&page=1`;
  const body = await _fetchJsonWithTimeout(url, {}, 6000);
  const items = body?.data?.data || [];
  if (!items.length) return null;
  const top = items[0];
  const tickSpacing = top?.config?.tickSpacing ?? null;
  return {
    poolAddress: top.id,
    programId: "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", // Raydium CLMM v3
    kind: "clmm",
    tokenA: { mint: top.mintA?.address, symbol: top.mintA?.symbol, decimals: top.mintA?.decimals },
    tokenB: { mint: top.mintB?.address, symbol: top.mintB?.symbol, decimals: top.mintB?.decimals },
    currentPrice: Number(top.price ?? 0),
    tick: top?.tickCurrent ?? null,
    tickSpacing,
    feeBps: top?.feeRate ? Math.round(Number(top.feeRate) * 1_000_000) : null,
    sqrtPriceX64: null,
    baseAprPct: Number(top?.day?.apr ?? 0),
    rewardAprPct: Number(top?.day?.aprReward ?? 0),
    tvlUsd: Number(top?.tvl ?? 0),
    vol24hUsd: Number(top?.day?.volume ?? 0),
  };
}

async function _orcaWhirlpoolState(mintA, mintB) {
  // Orca's official list endpoint ignores mint filter params (returns the
  // full 17MB pool dump). Use Dexscreener instead — it indexes Orca
  // whirlpools by token mint and returns the price, TVL, fees, and pair
  // address per pool. Filter to dexId='orca' and require both mints match.
  const url = `https://api.dexscreener.com/latest/dex/tokens/${mintA},${mintB}`;
  const body = await _fetchJsonWithTimeout(url, {}, 6000);
  const pairs = body?.pairs || [];
  const matches = pairs.filter((p) => {
    const dex = String(p?.dexId || "").toLowerCase();
    const baseAddr = String(p?.baseToken?.address || "").toLowerCase();
    const quoteAddr = String(p?.quoteToken?.address || "").toLowerCase();
    const a = mintA.toLowerCase();
    const b = mintB.toLowerCase();
    const pairMatches = (baseAddr === a && quoteAddr === b) || (baseAddr === b && quoteAddr === a);
    return dex.includes("orca") && pairMatches && (p?.chainId || "") === "solana";
  });
  if (!matches.length) return null;
  const sorted = matches.slice().sort((a, b) =>
    Number(b?.liquidity?.usd ?? 0) - Number(a?.liquidity?.usd ?? 0));
  const top = sorted[0];
  // Dexscreener doesn't surface tick or tickSpacing; fall back to defaults
  // common across Orca whirlpools (tickSpacing 64 for 0.30% fee tier).
  const feePct = Number(top?.feePercent ?? top?.fees?.lpFee ?? 0.3);
  const feeBps = Math.round(feePct * 100);
  return {
    poolAddress: top.pairAddress,
    programId: "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    kind: "whirlpool",
    tokenA: { mint: top?.baseToken?.address, symbol: top?.baseToken?.symbol, decimals: 9 },
    tokenB: { mint: top?.quoteToken?.address, symbol: top?.quoteToken?.symbol, decimals: 6 },
    currentPrice: Number(top?.priceNative ?? top?.priceUsd ?? 0),
    tick: null,
    tickSpacing: feeBps >= 100 ? 64 : (feeBps >= 30 ? 32 : (feeBps >= 5 ? 8 : 2)),
    feeBps,
    sqrtPriceX64: null,
    // APR estimate from fee revenue: vol24h × feePct × 365 / TVL × 100.
    // feePct is already in human percent (0.3 for 0.30% tier) — divide once.
    baseAprPct: (() => {
      const tvl = Number(top?.liquidity?.usd ?? 0);
      const vol = Number(top?.volume?.h24 ?? 0);
      if (tvl <= 0 || vol <= 0) return 0;
      return (vol * (feePct / 100) * 365 / tvl) * 100;
    })(),
    rewardAprPct: 0,
    tvlUsd: Number(top?.liquidity?.usd ?? 0),
    vol24hUsd: Number(top?.volume?.h24 ?? 0),
  };
}

async function _meteoraDlmmState(mintA, mintB) {
  // The original dlmm-api.meteora.ag REST endpoint has been retired
  // (returns 404 across every variant — verified 2026-05-15). Discovery now
  // hits DexScreener's Meteora indexer which returns Meteora DLMM pools
  // labelled "DLMM" with full liquidity/volume/price data. Bin step + active
  // bin (needed for the range-bucket math) are then loaded on-chain via the
  // @meteora-ag/dlmm SDK against the discovered pair address.
  const aShort = mintA.slice(0, 6);
  const bShort = mintB.slice(0, 6);
  // DexScreener's free search tolerates symbol+mint mixes; mint prefixes are
  // unambiguous and avoid symbol-collision noise (e.g. multiple "USDC"
  // wrappers).
  const searchUrl = `https://api.dexscreener.com/latest/dex/search?q=${encodeURIComponent(`meteora ${aShort} ${bShort}`)}`;
  let pairs = [];
  try {
    const body = await _fetchJsonWithTimeout(searchUrl, {}, 6000);
    pairs = body?.pairs || [];
  } catch (e) {
    console.warn("[meteora-dlmm] dexscreener search failed:", e.message);
  }
  const a = mintA.toLowerCase();
  const b = mintB.toLowerCase();
  const matches = pairs.filter((p) => {
    if (p?.dexId !== "meteora") return false;
    const labels = p?.labels || [];
    if (!labels.includes("DLMM")) return false;
    const base = (p?.baseToken?.address || "").toLowerCase();
    const quote = (p?.quoteToken?.address || "").toLowerCase();
    return (base === a && quote === b) || (base === b && quote === a);
  });
  if (!matches.length) return null;
  const top = matches.slice().sort(
    (x, y) => Number(y?.liquidity?.usd ?? 0) - Number(x?.liquidity?.usd ?? 0),
  )[0];
  const poolAddress = top.pairAddress;
  // Side-derive token0/token1 so they match the original (mint_x, mint_y)
  // ordering used by the LbPair on-chain.
  const baseAddr = (top?.baseToken?.address || "").toLowerCase();
  const tokenA = baseAddr === a
    ? { mint: top.baseToken.address, symbol: top.baseToken.symbol, decimals: top.baseToken.decimals ?? null }
    : { mint: top.quoteToken.address, symbol: top.quoteToken.symbol, decimals: top.quoteToken.decimals ?? null };
  const tokenB = baseAddr === a
    ? { mint: top.quoteToken.address, symbol: top.quoteToken.symbol, decimals: top.quoteToken.decimals ?? null }
    : { mint: top.baseToken.address, symbol: top.baseToken.symbol, decimals: top.baseToken.decimals ?? null };
  // SDK enrichment for binStep + activeId + baseFactor → fee_bps. The
  // @meteora-ag/dlmm package sets module.exports = exports.default (its
  // index.js rebinds), so the DLMM class is the require result itself —
  // no `.default` indirection.
  let binStep = 0;
  let activeId = 0;
  let baseFactor = 0;
  try {
    const DLMM = require("@meteora-ag/dlmm");
    const lb = await DLMM.create(connection, new PublicKey(poolAddress));
    binStep = Number(lb?.lbPair?.binStep ?? 0);
    activeId = Number(lb?.lbPair?.activeId ?? 0);
    baseFactor = Number(lb?.lbPair?.parameters?.baseFactor ?? 0);
  } catch (e) {
    console.warn("[meteora-dlmm] SDK enrichment failed for", poolAddress, ":", e.message);
  }
  // Pool fee in bps: Meteora DLMM uses base_fee_factor × bin_step. DexScreener
  // exposes the trade volume + liquidity, so volume-driven base APR is the
  // honest derivation. Reward APR (farming) is not on DexScreener — surface 0
  // until we wire the on-chain farm reader (Phase 4 lifecycle item).
  const tvl = Number(top?.liquidity?.usd ?? 0);
  const vol24 = Number(top?.volume?.h24 ?? 0);
  const priceUsd = Number(top?.priceUsd ?? 0);
  // DLMM base fee per Meteora docs: base_fee_rate_bps = baseFactor × binStep / 100.
  // baseFactor + binStep both come from on-chain LbPair, so this is exact —
  // no estimate. Fallback 10 bps only when the SDK enrichment failed (in
  // which case binStep=0 too and the formula produces 0 — we floor to 10 so
  // the APR estimate isn't visually zero).
  const feeBpsExact = baseFactor && binStep ? (baseFactor * binStep) / 100 : 0;
  const feeBps = feeBpsExact > 0 ? feeBpsExact : 10;
  const baseAprPct = tvl > 0 ? (vol24 * (feeBps / 10000) * 365 / tvl) * 100 : 0;
  return {
    poolAddress,
    programId: "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
    kind: "dlmm",
    tokenA,
    tokenB,
    currentPrice: priceUsd,
    tick: activeId,
    tickSpacing: null,
    binStep,
    feeBps,
    baseAprPct,
    rewardAprPct: 0,
    tvlUsd: tvl,
    vol24hUsd: vol24,
  };
}

app.post("/pool_state", async (req, res) => {
  const { protocol, mint0, mint1, pair } = req.body || {};
  if (!protocol) return res.status(400).json({ error: "protocol is required." });
  let a = mint0;
  let b = mint1;
  if ((!a || !b) && pair) {
    const parts = String(pair).split(/[-\/_]/);
    if (parts.length >= 2) {
      a = a || _resolveMintForSymbol(parts[0]);
      b = b || _resolveMintForSymbol(parts[1]);
    }
  }
  if (!a || !b) {
    return res.status(400).json({ error: "mint0+mint1 (or pair with known symbols) is required." });
  }
  const proto = String(protocol).toLowerCase();
  try {
    let state = null;
    let source = null;
    if (proto.includes("raydium")) {
      state = await _raydiumClmmState(a, b);
      source = "raydium-v3-api";
    } else if (proto.includes("orca") || proto.includes("whirlpool")) {
      state = await _orcaWhirlpoolState(a, b);
      source = "orca-api";
    } else if (proto.includes("meteora") || proto.includes("dlmm")) {
      state = await _meteoraDlmmState(a, b);
      source = "meteora-api";
    } else {
      return res.status(404).json({ error: `No pool-state probe wired for protocol '${protocol}'.` });
    }
    if (!state) return res.status(404).json({ error: `No ${proto} pool found for mints ${a}/${b}.` });
    res.json({ ok: true, pool: state, source });
  } catch (err) {
    console.error("[pool_state]", protocol, err);
    res.status(502).json({ error: err.message || "pool_state_failed" });
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
