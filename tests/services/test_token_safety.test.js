/**
 * V7-031 + V7-032 + V7-041 pin test — _token_safety helper.
 *
 * Verifies:
 *   1. ALLOWED_TRANSFER_HOOKS contains ≥1 seed entry (V7-031).
 *   2. ALLOWED_HOOK_NAMES contains confidential_transfer + memo (V7-031).
 *   3. checkTransferHook returns {ok:true} for a legacy SPL mint
 *      (connection.getAccountInfo → null) (V7-031).
 *   4. buildSyncNativeIx returns kind="sync_native" + token program id (V7-032).
 *   5. buildCloseWsolIx returns kind="close_account" + destination === owner (V7-032).
 *   6. isWhirlpoolInitialized: owner === WHIRLPOOL_PROGRAM_ID → true (V7-041).
 *   7. isWhirlpoolInitialized: owner mismatch → false (V7-041).
 *   8. isWhirlpoolInitialized: info=null → false (V7-041).
 *   9. isRaydiumCLMMInitialized: owner === RAYDIUM_CLMM_PROGRAM_ID → true (V7-041).
 *  10. isRaydiumCLMMInitialized: owner mismatch → false (V7-041).
 *  11. isRaydiumCLMMInitialized: info=null → false (V7-041).
 *  12. orca.js requires ./_token_safety (light-touch integration proof).
 *
 * Module resolution: this repo doesn't run `npm install` for the
 * solana-yield-builder sidecar in CI. The helper module is pure JS with
 * zero runtime deps so it can be required directly without the shared
 * sandbox, but we keep the bootstrap consistent with sibling tests.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const Module = require("module");
const assert = require("assert");

const SHARED_DEPS = "/tmp/altsplit-test-deps/node_modules";
if (fs.existsSync(SHARED_DEPS)) {
  Module.globalPaths.push(SHARED_DEPS);
  process.env.NODE_PATH = `${SHARED_DEPS}${path.delimiter}${process.env.NODE_PATH || ""}`;
  Module._initPaths();
}

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const HELPER_PATH = path.join(
  REPO_ROOT,
  "services/solana-yield-builder/src/adapters/_token_safety.js"
);
const ORCA_PATH = path.join(
  REPO_ROOT,
  "services/solana-yield-builder/src/adapters/orca.js"
);

const TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA";
const WHIRLPOOL_PROGRAM_ID = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc";
const RAYDIUM_CLMM_PROGRAM_ID = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK";

let pass = 0;
let fail = 0;
function test(name, fn) {
  try {
    const r = fn();
    if (r && typeof r.then === "function") {
      return r.then(
        () => {
          console.log(`  ok  ${name}`);
          pass += 1;
        },
        (err) => {
          console.error(`  FAIL ${name}`);
          console.error(`       ${err && err.stack ? err.stack : err}`);
          fail += 1;
        }
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

console.log("V7-031 + V7-032 + V7-041 _token_safety pin tests");
console.log("================================================");

const safety = require(HELPER_PATH);

// --- V7-031 transfer-hook allowlist ---------------------------------------
test("ALLOWED_TRANSFER_HOOKS has at least 1 entry", () => {
  assert.ok(
    safety.ALLOWED_TRANSFER_HOOKS instanceof Set,
    "ALLOWED_TRANSFER_HOOKS not a Set"
  );
  assert.ok(
    safety.ALLOWED_TRANSFER_HOOKS.size >= 1,
    `expected ≥1 entry, got ${safety.ALLOWED_TRANSFER_HOOKS.size}`
  );
});

test("ALLOWED_HOOK_NAMES contains confidential_transfer + memo", () => {
  assert.ok(safety.ALLOWED_HOOK_NAMES instanceof Set);
  assert.ok(
    safety.ALLOWED_HOOK_NAMES.has("confidential_transfer"),
    "missing confidential_transfer"
  );
  assert.ok(safety.ALLOWED_HOOK_NAMES.has("memo"), "missing memo");
});

(async () => {
  await test(
    "checkTransferHook returns {ok:true} for legacy SPL mint (info=null)",
    async () => {
      const fakeConn = { getAccountInfo: async () => null };
      const res = await safety.checkTransferHook(fakeConn, "anyMint");
      assert.strictEqual(res.ok, true);
      assert.strictEqual(res.reason, undefined);
    }
  );

  // --- V7-032 WSOL sync + close builders ---------------------------------
  test("buildSyncNativeIx returns kind='sync_native' + correct programId", () => {
    const ix = safety.buildSyncNativeIx("WSOLATAPubkey111");
    assert.strictEqual(ix.kind, "sync_native");
    assert.strictEqual(ix.programId, TOKEN_PROGRAM_ID);
    assert.strictEqual(ix.account, "WSOLATAPubkey111");
  });

  test("buildCloseWsolIx returns kind='close_account' + destination === owner", () => {
    const owner = "OwnerPubkey222";
    const ix = safety.buildCloseWsolIx("WSOLATAPubkey111", owner);
    assert.strictEqual(ix.kind, "close_account");
    assert.strictEqual(ix.programId, TOKEN_PROGRAM_ID);
    assert.strictEqual(ix.account, "WSOLATAPubkey111");
    assert.strictEqual(ix.destination, owner);
    assert.strictEqual(ix.owner, owner);
    assert.strictEqual(ix.destination, ix.owner);
  });

  // --- V7-041 Whirlpool init detection -----------------------------------
  await test("isWhirlpoolInitialized: owner === WHIRLPOOL_PROGRAM_ID → true", async () => {
    const fakeConn = {
      getAccountInfo: async () => ({
        owner: { toString: () => WHIRLPOOL_PROGRAM_ID },
      }),
    };
    const ok = await safety.isWhirlpoolInitialized(fakeConn, "poolPubkey");
    assert.strictEqual(ok, true);
  });

  await test("isWhirlpoolInitialized: owner mismatch → false", async () => {
    const fakeConn = {
      getAccountInfo: async () => ({
        owner: { toString: () => "SomeOtherProgramId" },
      }),
    };
    const ok = await safety.isWhirlpoolInitialized(fakeConn, "poolPubkey");
    assert.strictEqual(ok, false);
  });

  await test("isWhirlpoolInitialized: info=null → false", async () => {
    const fakeConn = { getAccountInfo: async () => null };
    const ok = await safety.isWhirlpoolInitialized(fakeConn, "poolPubkey");
    assert.strictEqual(ok, false);
  });

  // --- V7-041 Raydium CLMM init detection --------------------------------
  await test("isRaydiumCLMMInitialized: owner === RAYDIUM_CLMM_PROGRAM_ID → true", async () => {
    const fakeConn = {
      getAccountInfo: async () => ({
        owner: { toString: () => RAYDIUM_CLMM_PROGRAM_ID },
      }),
    };
    const ok = await safety.isRaydiumCLMMInitialized(fakeConn, "poolPubkey");
    assert.strictEqual(ok, true);
  });

  await test("isRaydiumCLMMInitialized: owner mismatch → false", async () => {
    const fakeConn = {
      getAccountInfo: async () => ({
        owner: { toString: () => "SomeOtherProgramId" },
      }),
    };
    const ok = await safety.isRaydiumCLMMInitialized(fakeConn, "poolPubkey");
    assert.strictEqual(ok, false);
  });

  await test("isRaydiumCLMMInitialized: info=null → false", async () => {
    const fakeConn = { getAccountInfo: async () => null };
    const ok = await safety.isRaydiumCLMMInitialized(fakeConn, "poolPubkey");
    assert.strictEqual(ok, false);
  });

  // --- Integration proof: orca.js requires _token_safety -----------------
  test("orca.js requires ./_token_safety", () => {
    const orcaSrc = fs.readFileSync(ORCA_PATH, "utf8");
    assert.ok(
      /require\(["']\.\/_token_safety["']\)/.test(orcaSrc),
      "orca.js does not require('./_token_safety')"
    );
  });

  // --- Summary ----------------------------------------------------------
  console.log("");
  console.log(`pass: ${pass}   fail: ${fail}`);
  if (fail > 0) {
    process.exit(1);
  }
})();
