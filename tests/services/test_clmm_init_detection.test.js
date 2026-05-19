/**
 * V7-041 pin test — CLMM pool-init detection wired into the orca + raydium
 * adapter callsites.
 *
 * Verifies:
 *   1. orca.buildOpen returns a typed POOL_NOT_INITIALIZED blocker when
 *      connection.getAccountInfo(whirlpoolPubkey) returns null (mainnet
 *      pool never created, or wrong pubkey).
 *   2. orca.buildOpen returns the same blocker when the account exists
 *      but is owned by a non-Whirlpool program (e.g. raw System program
 *      account stuffed into a whirlpool slot).
 *   3. raydium.buildCloseChecked returns a POOL_NOT_INITIALIZED blocker
 *      when the position PDA derived from the NFT mint is not owned by
 *      the canonical CLMM program (CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK).
 *      Wrong-program close on-chain reverts opaquely; the gate surfaces
 *      a clean typed recovery before the IX is even built.
 *   4. raydium.buildCloseChecked returns the IX (no blocker) when the
 *      position PDA IS owned by the CLMM program.
 *
 * Deterministic — no network calls. Both connections are inline mocks
 * whose getAccountInfo returns a fixture chosen by the pubkey passed in.
 *
 * Module resolution: mirrors test_kamino_native.test.js + sibling tests —
 * NODE_PATH points at /tmp/altsplit-test-deps/node_modules which has the
 * runtime deps the adapters import at module load (@solana/web3.js, bn.js).
 */
"use strict";

const fs = require("fs");
const path = require("path");
const Module = require("module");
const assert = require("assert");

// ── Shared deps sandbox bootstrap ──────────────────────────────────────────
// CI prefers the shared `/tmp/altsplit-test-deps/node_modules` sandbox so the
// repo doesn't ship a fat node_modules tree. When running locally (Windows,
// dev laptops) we transparently fall back to the sidecar's own node_modules
// after `npm install` inside services/solana-yield-builder/.
const SHARED_DEPS = "/tmp/altsplit-test-deps/node_modules";
const REPO_ROOT_BOOT = path.resolve(__dirname, "..", "..");
const LOCAL_DEPS = path.join(REPO_ROOT_BOOT, "services/solana-yield-builder/node_modules");
let depsRoot = null;
if (fs.existsSync(SHARED_DEPS)) {
  depsRoot = SHARED_DEPS;
} else if (fs.existsSync(LOCAL_DEPS)) {
  depsRoot = LOCAL_DEPS;
}
if (depsRoot) {
  Module.globalPaths.push(depsRoot);
  process.env.NODE_PATH = `${depsRoot}${path.delimiter}${process.env.NODE_PATH || ""}`;
  Module._initPaths();
} else {
  console.error(
    `[fatal] no deps tree found — looked for ${SHARED_DEPS} (CI) and ${LOCAL_DEPS} (local).`
  );
  process.exit(2);
}

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const ORCA_PATH = path.join(REPO_ROOT, "services/solana-yield-builder/src/adapters/orca.js");
const RAYDIUM_PATH = path.join(REPO_ROOT, "services/solana-yield-builder/src/adapters/raydium.js");

const WHIRLPOOL_PROGRAM_ID = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc";
const RAYDIUM_CLMM_PROGRAM_ID = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK";
const SYSTEM_PROGRAM_ID = "11111111111111111111111111111111";

// A plausible mainnet whirlpool address (SOL-USDC tier-1). The owner is
// always overridden by our mock so the literal value is just illustrative.
const FAKE_WHIRLPOOL = "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtL45EHRJ5Y3UQ8";
const FAKE_USER = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM";
const FAKE_POSITION_NFT = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM";

let pass = 0;
let fail = 0;
function test(name, fn) {
  try {
    const r = fn();
    if (r && typeof r.then === "function") {
      return r.then(
        () => { console.log(`  ok  ${name}`); pass += 1; },
        (err) => { console.error(`  FAIL ${name}`); console.error(`       ${err && err.stack ? err.stack : err}`); fail += 1; },
      );
    }
    console.log(`  ok  ${name}`);
    pass += 1;
  } catch (err) {
    console.error(`  FAIL ${name}`);
    console.error(`       ${err && err.stack ? err.stack : err}`);
    fail += 1;
  }
}

console.log("V7-041 CLMM pool-init detection pin tests");
console.log("=========================================");

const orca = require(ORCA_PATH);
const raydium = require(RAYDIUM_PATH);

// ── Mock-connection factory ────────────────────────────────────────────────
// `lookups` maps base58 pubkey → fixture (or null). Anything not in the map
// returns null (treated as missing account).
function makeConn(lookups) {
  return {
    getAccountInfo: async (pubkey) => {
      const key =
        typeof pubkey === "string"
          ? pubkey
          : (typeof pubkey.toBase58 === "function" ? pubkey.toBase58() : String(pubkey));
      return Object.prototype.hasOwnProperty.call(lookups, key) ? lookups[key] : null;
    },
    // orca.buildOpen calls getLatestBlockhash after the gates pass; we never
    // reach that branch in these tests so the stub returns a no-op.
    getLatestBlockhash: async () => ({ blockhash: "11111111111111111111111111111111", lastValidBlockHeight: 0 }),
  };
}

// ── orca tests ─────────────────────────────────────────────────────────────
(async () => {
  await test("orca.buildOpen returns POOL_NOT_INITIALIZED blocker when getAccountInfo → null", async () => {
    const conn = makeConn({}); // every getAccountInfo returns null → pool missing
    const res = await orca.buildOpen(
      {
        user: FAKE_USER,
        whirlpool: FAKE_WHIRLPOOL,
        inputSymbol: "USDC",
        inputAmount: "10",
        tickLowerIndex: -443636,
        tickUpperIndex: 443636,
      },
      { connection: conn },
    );
    assert.ok(res && typeof res === "object", "expected blocker object");
    assert.strictEqual(res.code, "POOL_NOT_INITIALIZED", `expected code=POOL_NOT_INITIALIZED, got ${res.code}`);
    assert.strictEqual(res.blocker, "POOL_NOT_INITIALIZED");
    assert.strictEqual(res.kind, "blocker");
    assert.ok(Array.isArray(res.transactions) && res.transactions.length === 0, "blocker.transactions must be []");
    assert.ok(String(res.message || "").includes(FAKE_WHIRLPOOL), "blocker.message must name the offending whirlpool");
  });

  await test("orca.buildOpen returns POOL_NOT_INITIALIZED when whirlpool account is owned by wrong program", async () => {
    const conn = makeConn({
      [FAKE_WHIRLPOOL]: {
        owner: { toString: () => SYSTEM_PROGRAM_ID }, // wrong owner
        data: Buffer.alloc(0),
      },
    });
    const res = await orca.buildOpen(
      {
        user: FAKE_USER,
        whirlpool: FAKE_WHIRLPOOL,
        inputSymbol: "USDC",
        inputAmount: "10",
        tickLowerIndex: -443636,
        tickUpperIndex: 443636,
      },
      { connection: conn },
    );
    assert.strictEqual(res.code, "POOL_NOT_INITIALIZED", `expected POOL_NOT_INITIALIZED, got ${res.code} (msg: ${res.message})`);
    assert.strictEqual(res.whirlpool, FAKE_WHIRLPOOL);
  });

  // ── raydium tests ────────────────────────────────────────────────────────
  await test("raydium exports buildCloseChecked (V7-041 wrapper)", () => {
    assert.strictEqual(typeof raydium.buildCloseChecked, "function", "raydium.buildCloseChecked missing");
  });

  // Derive the actual personalPosition PDA for the chosen NFT mint so the
  // mock can dispatch on it. The wrapper computes the same PDA so the mock
  // hits whichever fixture we wire up.
  const { PublicKey } = require("@solana/web3.js");
  const CLMM_PROGRAM_PK = new PublicKey(RAYDIUM_CLMM_PROGRAM_ID);
  const nftMintPk = new PublicKey(FAKE_POSITION_NFT);
  const [positionPda] = PublicKey.findProgramAddressSync(
    [Buffer.from("position"), nftMintPk.toBuffer()],
    CLMM_PROGRAM_PK,
  );
  const positionPdaStr = positionPda.toBase58();

  await test("raydium.buildCloseChecked returns POOL_NOT_INITIALIZED blocker when PDA owner is not CLMM program", async () => {
    const conn = makeConn({
      [positionPdaStr]: {
        owner: { toString: () => SYSTEM_PROGRAM_ID }, // wrong-owner
        data: Buffer.alloc(0),
      },
    });
    const res = await raydium.buildCloseChecked(FAKE_POSITION_NFT, { owner: FAKE_USER }, { connection: conn });
    assert.ok(res && typeof res === "object", "expected blocker object");
    assert.strictEqual(res.code, "POOL_NOT_INITIALIZED", `expected POOL_NOT_INITIALIZED, got ${res.code} (msg: ${res.message})`);
    assert.strictEqual(res.kind, "blocker");
    assert.ok(Array.isArray(res.transactions) && res.transactions.length === 0, "blocker.transactions must be []");
    assert.ok(String(res.message || "").includes(RAYDIUM_CLMM_PROGRAM_ID), "blocker.message must name the expected CLMM program");
  });

  await test("raydium.buildCloseChecked returns POOL_NOT_INITIALIZED when PDA account missing (null)", async () => {
    const conn = makeConn({}); // PDA lookup → null
    const res = await raydium.buildCloseChecked(FAKE_POSITION_NFT, { owner: FAKE_USER }, { connection: conn });
    assert.strictEqual(res.code, "POOL_NOT_INITIALIZED");
  });

  await test("raydium.buildCloseChecked returns IX (no blocker) when PDA owner === CLMM program", async () => {
    const conn = makeConn({
      [positionPdaStr]: {
        owner: { toString: () => RAYDIUM_CLMM_PROGRAM_ID }, // correct owner
        data: Buffer.alloc(0),
      },
    });
    const ix = await raydium.buildCloseChecked(FAKE_POSITION_NFT, { owner: FAKE_USER }, { connection: conn });
    // Returned object must be a TransactionInstruction (programId === CLMM program),
    // NOT a blocker.
    assert.ok(ix && ix.programId, "expected IX, got blocker or undefined");
    assert.strictEqual(ix.programId.toBase58(), RAYDIUM_CLMM_PROGRAM_ID);
    assert.ok(!ix.code, "should not carry a blocker code");
  });

  // ── Summary ───────────────────────────────────────────────────────────────
  console.log("");
  console.log(`pass: ${pass}   fail: ${fail}`);
  if (fail > 0) {
    process.exit(1);
  }
})();
