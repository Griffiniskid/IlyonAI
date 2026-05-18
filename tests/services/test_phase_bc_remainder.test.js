/**
 * V7-059 + V7-060 + V7-061 pin test — Phase B/C remainder lifecycle exits.
 *
 * Verifies:
 *   V7-059  Raydium CLMM close — raydium.buildClose returns a TransactionInstruction
 *           whose programId is the canonical CLMM program
 *           CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK and whose data starts
 *           with the Anchor sighash for `close_position`.
 *
 *   V7-060  Meteora DLMM removeByRange — meteora.buildRemoveByRange returns a
 *           TransactionInstruction whose programId is LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo
 *           and whose data payload encodes binIdFrom + binIdTo as i32 LE +
 *           bpsToRemove as u16 LE (18 bytes total: 8 disc + 4 + 4 + 2).
 *
 *   V7-061  JLP withdraw lockup gating — jlp.buildWithdraw with lockup_end_ts
 *           in the future returns a `JLP_LOCKED` blocker WITHOUT building any
 *           transaction (no Solana connection needed). With lockup_end_ts in the
 *           past, it crosses the gate and tries to build the IX (we expect an
 *           error about the missing connection rather than the lockup blocker —
 *           that proves the gate let us through).
 *
 * Module resolution: mirrors test_kamino_native.test.js — NODE_PATH points at
 * /tmp/altsplit-test-deps/node_modules which has the four runtime deps
 * (@solana/web3.js, @solana/spl-token, bn.js, node-fetch) the adapters import
 * at module load.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const Module = require("module");
const crypto = require("crypto");
const assert = require("assert");

// ── Shared deps sandbox bootstrap ──────────────────────────────────────────
const SHARED_DEPS = "/tmp/altsplit-test-deps/node_modules";
if (fs.existsSync(SHARED_DEPS)) {
  Module.globalPaths.push(SHARED_DEPS);
  process.env.NODE_PATH = `${SHARED_DEPS}${path.delimiter}${process.env.NODE_PATH || ""}`;
  Module._initPaths();
} else {
  console.error(`[fatal] shared deps sandbox missing at ${SHARED_DEPS}`);
  process.exit(2);
}

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const RAYDIUM_PATH = path.join(REPO_ROOT, "services/solana-yield-builder/src/adapters/raydium.js");
const METEORA_PATH = path.join(REPO_ROOT, "services/solana-yield-builder/src/adapters/meteora.js");
const JLP_PATH = path.join(REPO_ROOT, "services/solana-yield-builder/src/adapters/jlp.js");

const CLMM_PROGRAM_ID = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK";
const DLMM_PROGRAM_ID = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo";

let pass = 0;
let fail = 0;
function test(name, fn) {
  try {
    const result = fn();
    if (result && typeof result.then === "function") {
      return result.then(
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

console.log("V7-059 + V7-060 + V7-061 Phase B/C remainder pin tests");
console.log("=======================================================");

const { PublicKey } = require("@solana/web3.js");

// ── V7-059 — Raydium CLMM close ────────────────────────────────────────────
const raydium = require(RAYDIUM_PATH);

test("V7-059 raydium exports buildClose + CLMM_PROGRAM constant", () => {
  assert.strictEqual(typeof raydium.buildClose, "function", "raydium.buildClose missing");
  assert.strictEqual(raydium.CLMM_PROGRAM, CLMM_PROGRAM_ID);
});

test("V7-059 raydium.buildClose returns IX with programId = CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", () => {
  // Use a plausible mainnet pubkey (USDC mint) as the stand-in position NFT.
  const positionNft = new PublicKey("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM");
  const owner = new PublicKey("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM");
  const ix = raydium.buildClose(positionNft, { owner, positionNftAccount: positionNft });
  assert.strictEqual(ix.programId.toBase58(), CLMM_PROGRAM_ID);
});

test("V7-059 raydium.buildClose data starts with sha256('global:close_position').slice(0,8)", () => {
  const expected = crypto.createHash("sha256").update("global:close_position").digest().slice(0, 8);
  const ix = raydium.buildClose("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM");
  assert.strictEqual(ix.data.length, 8, `close_position takes no args; expected 8-byte disc-only data, got ${ix.data.length}`);
  assert.strictEqual(ix.data.toString("hex"), expected.toString("hex"));
});

test("V7-059 raydium.buildClose includes owner (signer, writable) at key index 0", () => {
  const owner = new PublicKey("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM");
  const ix = raydium.buildClose("11111111111111111111111111111112", { owner });
  assert.ok(ix.keys.length >= 4, `expected ≥4 keys, got ${ix.keys.length}`);
  assert.strictEqual(ix.keys[0].pubkey.toBase58(), owner.toBase58());
  assert.strictEqual(ix.keys[0].isSigner, true);
  assert.strictEqual(ix.keys[0].isWritable, true);
});

// ── V7-060 — Meteora DLMM removeByRange ───────────────────────────────────
const meteora = require(METEORA_PATH);

test("V7-060 meteora exports buildRemoveByRange + DLMM_PROGRAM constant", () => {
  assert.strictEqual(typeof meteora.buildRemoveByRange, "function", "meteora.buildRemoveByRange missing");
  assert.strictEqual(meteora.DLMM_PROGRAM, DLMM_PROGRAM_ID);
});

test("V7-060 meteora.buildRemoveByRange returns IX with programId = LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", () => {
  const position = new PublicKey("11111111111111111111111111111112");
  const sender = new PublicKey("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM");
  const ix = meteora.buildRemoveByRange(position, -100, 100, { sender });
  assert.strictEqual(ix.programId.toBase58(), DLMM_PROGRAM_ID);
});

test("V7-060 meteora.buildRemoveByRange encodes binIdFrom + binIdTo as i32 LE + bps u16 LE in data", () => {
  const binIdFrom = -1234;
  const binIdTo = 5678;
  const bps = 7777;
  const ix = meteora.buildRemoveByRange("11111111111111111111111111111112", binIdFrom, binIdTo, { bpsToRemove: bps });
  // 8 disc + 4 (i32 LE) + 4 (i32 LE) + 2 (u16 LE) = 18 bytes total.
  assert.strictEqual(ix.data.length, 18, `expected 18-byte data, got ${ix.data.length}`);
  const disc = ix.data.slice(0, 8);
  const expectedDisc = crypto.createHash("sha256").update("global:remove_liquidity_by_range").digest().slice(0, 8);
  assert.strictEqual(disc.toString("hex"), expectedDisc.toString("hex"));
  assert.strictEqual(ix.data.readInt32LE(8), binIdFrom, "binIdFrom not encoded at offset 8");
  assert.strictEqual(ix.data.readInt32LE(12), binIdTo, "binIdTo not encoded at offset 12");
  assert.strictEqual(ix.data.readUInt16LE(16), bps, "bpsToRemove not encoded at offset 16");
});

test("V7-060 meteora.buildRemoveByRange rejects binIdTo < binIdFrom", () => {
  assert.throws(
    () => meteora.buildRemoveByRange("11111111111111111111111111111112", 100, 50),
    /binIdTo .* must be >= binIdFrom/,
  );
});

// ── V7-061 — JLP withdraw lockup gating ────────────────────────────────────
const jlp = require(JLP_PATH);

test("V7-061 jlp exports buildWithdraw", () => {
  assert.strictEqual(typeof jlp.buildWithdraw, "function", "jlp.buildWithdraw missing");
});

test("V7-061 jlp.buildWithdraw with lockup_end_ts in future → JLP_LOCKED blocker (no tx)", async () => {
  const futureTs = Math.floor(Date.now() / 1000) + 3600; // 1h from now
  const result = await jlp.buildWithdraw({
    asset: "USDC",
    amount: "1.0",
    user: "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
    lockup_end_ts: futureTs,
  }); // no connection passed — gate must short-circuit before connection check
  assert.ok(result, "buildWithdraw returned nothing");
  assert.strictEqual(result.blocker, "JLP_LOCKED", `expected blocker=JLP_LOCKED, got ${result.blocker}`);
  assert.strictEqual(result.code, "JLP_LOCKED");
  assert.strictEqual(result.lockup_end_ts, futureTs);
  assert.ok(result.remaining_seconds > 0, "remaining_seconds should be positive");
  assert.deepStrictEqual(result.transactions, [], "transactions array should be empty when locked");
});

test("V7-061 jlp.buildWithdraw with lockup_end_ts in past → gate opens (builds, then errs on missing connection)", async () => {
  const pastTs = Math.floor(Date.now() / 1000) - 3600; // 1h ago
  let threw = null;
  try {
    await jlp.buildWithdraw({
      asset: "USDC",
      amount: "1.0",
      user: "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
      lockup_end_ts: pastTs,
    }); // no connection — past-lockup path must reach the connection check
  } catch (err) {
    threw = err;
  }
  // Past-lockup must throw a "requires a Solana connection" error — this proves
  // the lockup gate let us through (locked path would have returned a blocker,
  // not thrown). It must NOT throw a JLP_LOCKED error.
  assert.ok(threw, "expected past-lockup path to throw (missing connection), got silent return");
  assert.ok(
    /requires a Solana connection/i.test(String(threw.message || threw)),
    `expected connection error, got: ${threw.message || threw}`,
  );
  assert.ok(
    !/JLP_LOCKED/.test(String(threw.message || threw)),
    "past-lockup should not surface JLP_LOCKED",
  );
});

test("V7-061 jlp.buildWithdraw with no lockup_end_ts → gate is permissive (errs on missing connection)", async () => {
  let threw = null;
  try {
    await jlp.buildWithdraw({
      asset: "USDC",
      amount: "1.0",
      user: "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
    });
  } catch (err) {
    threw = err;
  }
  assert.ok(threw, "expected missing-connection error when no lockup is set");
  assert.ok(/requires a Solana connection/i.test(String(threw.message || threw)));
});

// ── Summary ────────────────────────────────────────────────────────────────
process.on("beforeExit", () => {
  console.log("");
  console.log(`pass: ${pass}   fail: ${fail}`);
  if (fail > 0) process.exit(1);
});
