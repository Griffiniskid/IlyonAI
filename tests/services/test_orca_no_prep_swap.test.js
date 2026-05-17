/**
 * V7-050 pin test — Orca native open_position + increaseLiquidity path
 * (legacy prep_swap two-tx handoff removed).
 *
 * Verifies:
 *   1. The literal substring `prep_swap(` no longer appears in orca.js
 *      (covers both action-string emissions and any helper invocations).
 *   2. No `require()` call pulls in jupiter / pairAware specifically for
 *      a prep_swap helper (legacy `planPrepSwap` import is gone).
 *   3. The public surface still exposes the prior contract — `build`,
 *      `buildClose`, `quote`, `aliases`, `supportedActions` — plus the
 *      new native entry points `buildOpen` + `buildIncrease`.
 *   4. WHIRLPOOL_PROGRAM_ID is surfaced for tx-validation callers.
 *   5. The `tokenSafety = require("./_token_safety")` import is preserved
 *      (V7-031/032/041 contract).
 *
 * Pure source-string + module-load asserts — no Whirlpool SDK on disk in
 * CI, so we don't try to invoke the live builder.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const Module = require("module");
const assert = require("assert");

// Wire up the shared deps sandbox first so the adapter resolves
// @solana/web3.js + bn.js at module load.
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
const ADAPTER_PATH = path.join(
  REPO_ROOT,
  "services/solana-yield-builder/src/adapters/orca.js"
);

const WHIRLPOOL_PROGRAM_ID = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc";

let pass = 0;
let fail = 0;
function test(name, fn) {
  try {
    fn();
    console.log(`  ok  ${name}`);
    pass += 1;
  } catch (err) {
    console.error(`  FAIL ${name}`);
    console.error(`       ${err && err.stack ? err.stack : err}`);
    fail += 1;
  }
}

console.log("V7-050 Orca prep_swap removal + native open/increase");
console.log("====================================================");

// --- 1. Source-level greps -------------------------------------------------
const source = fs.readFileSync(ADAPTER_PATH, "utf8");

test("prep_swap( substring no longer in orca.js", () => {
  assert.ok(
    !source.includes("prep_swap("),
    "orca.js still contains literal `prep_swap(` — V7-050 not complete"
  );
});

test("legacy planPrepSwap require import is gone", () => {
  assert.ok(
    !/require\(["']\.\/pairAware["']\)/.test(source) || !/planPrepSwap/.test(source),
    "planPrepSwap is still imported from ./pairAware"
  );
});

test("no jupiter import line whose only purpose is prep_swap", () => {
  // The native path still legitimately uses jupiter helpers (buildSwap,
  // resolveMint, decimalsFor, humanToAtoms) for the AMM v1 LP-mint
  // route + atom conversion. We only disallow the legacy prep_swap
  // require shape — i.e. a require call whose surrounding context
  // names `prep_swap`. The literal substring assert above is the
  // primary guard; this is belt-and-braces.
  const lines = source.split(/\r?\n/);
  const offenders = lines.filter(
    (l) => /require\(/.test(l) && /prep_swap/i.test(l)
  );
  assert.strictEqual(
    offenders.length,
    0,
    `found ${offenders.length} require() lines mentioning prep_swap: ${offenders.join(" | ")}`
  );
});

test("tokenSafety = require('./_token_safety') import is preserved", () => {
  assert.ok(
    /const\s+tokenSafety\s*=\s*require\(["']\.\/_token_safety["']\)/.test(source),
    "tokenSafety _token_safety import was dropped — V7-031/032/041 contract broken"
  );
});

test("buildSyncNativeIx + buildCloseWsolIx are wired in the native path", () => {
  assert.ok(
    /tokenSafety\.buildSyncNativeIx\s*\(/.test(source),
    "buildSyncNativeIx call missing from orca.js"
  );
  assert.ok(
    /tokenSafety\.buildCloseWsolIx\s*\(/.test(source),
    "buildCloseWsolIx call missing from orca.js"
  );
});

// --- 2. Module-load surface -----------------------------------------------
const orca = require(ADAPTER_PATH);

test("module.exports preserves prior public surface (build, buildClose, quote)", () => {
  assert.strictEqual(typeof orca.build, "function", "missing export: build");
  assert.strictEqual(typeof orca.buildClose, "function", "missing export: buildClose");
  assert.strictEqual(typeof orca.quote, "function", "missing export: quote");
  assert.ok(Array.isArray(orca.aliases), "missing export: aliases");
  assert.ok(Array.isArray(orca.supportedActions), "missing export: supportedActions");
});

test("native entry points buildOpen + buildIncrease are exported", () => {
  assert.strictEqual(typeof orca.buildOpen, "function", "missing export: buildOpen");
  assert.strictEqual(typeof orca.buildIncrease, "function", "missing export: buildIncrease");
});

test("WHIRLPOOL_PROGRAM_ID constant surfaced for tx validation", () => {
  assert.strictEqual(orca.WHIRLPOOL_PROGRAM_ID, WHIRLPOOL_PROGRAM_ID);
});

test("supportedActions advertises open_position + increase_liquidity", () => {
  assert.ok(
    orca.supportedActions.includes("open_position"),
    "supportedActions missing open_position"
  );
  assert.ok(
    orca.supportedActions.includes("increase_liquidity"),
    "supportedActions missing increase_liquidity"
  );
});

test("_internals exposes buildOpenPositionTx + buildIncreaseLiquidityTx", () => {
  assert.ok(orca._internals, "_internals missing");
  assert.strictEqual(
    typeof orca._internals.buildOpenPositionTx,
    "function",
    "missing _internals.buildOpenPositionTx"
  );
  assert.strictEqual(
    typeof orca._internals.buildIncreaseLiquidityTx,
    "function",
    "missing _internals.buildIncreaseLiquidityTx"
  );
});

// --- 3. build() with no whirlpool surfaces a clean blocker, not a swap ----
// Async test — run inside the IIFE below so rejections propagate.
async function asyncTest(name, fn) {
  try {
    await fn();
    console.log(`  ok  ${name}`);
    pass += 1;
  } catch (err) {
    console.error(`  FAIL ${name}`);
    console.error(`       ${err && err.stack ? err.stack : err}`);
    fail += 1;
  }
}

(async () => {
  await asyncTest(
    "build() with no extra.whirlpool throws missing_whirlpool_or_ticks",
    async () => {
      try {
        await orca.build({
          asset: "USDC",
          amount: "10",
          user: "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
          extra: {},
        });
        throw new Error("expected build() to throw without whirlpool");
      } catch (err) {
        assert.strictEqual(
          err.code,
          "missing_whirlpool_or_ticks",
          `expected code=missing_whirlpool_or_ticks, got code=${err.code} msg=${err.message}`
        );
      }
    }
  );

  // --- Summary --------------------------------------------------------------
  console.log("");
  console.log(`pass: ${pass}   fail: ${fail}`);
  if (fail > 0) {
    process.exit(1);
  }
})();
