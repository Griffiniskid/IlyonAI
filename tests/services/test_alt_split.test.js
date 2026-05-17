/**
 * V7-036 pin test — Real Solana ALT splitter.
 *
 * Verifies the new `splitInstructionsAcrossTransactions` function in
 * services/solana-yield-builder/src/adapters/altSplit.js:
 *
 *   1. 35 ixs / default cap (28) → 2 transactions: [28, 7]
 *   2. 35 ixs / ledger=true (7) → 5 transactions: [7, 7, 7, 7, 7]
 *   3. 10 ixs / default cap → 1 transaction
 *   4. empty input → 0 transactions
 *   5. Instruction order preserved across splits (ix[0] always in tx[0],
 *      and the very last input ix lives in the very last tx).
 *   6. ledgerWarning flag reflects opts.ledger.
 *
 * Module resolution: this repo doesn't run `npm install` for the
 * solana-yield-builder sidecar in CI. The shared sandbox at
 * /tmp/altsplit-test-deps/node_modules/ has @solana/web3.js which the
 * adapter imports at module load. NODE_PATH is prepended before any
 * require() so the adapter resolves the dep.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const Module = require("module");
const assert = require("assert");

// Wire up the shared deps sandbox first — must happen before require()ing
// the adapter, which imports @solana/web3.js at module load.
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
  "services/solana-yield-builder/src/adapters/altSplit.js"
);

const altSplit = require(ADAPTER_PATH);
const { splitInstructionsAcrossTransactions } = altSplit;

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

console.log("V7-036 ALT splitter pin tests");
console.log("=============================");

// Build a synthetic list of N "instructions" — the splitter is structurally
// agnostic, it only chunks the array, so plain objects with a stable id are
// enough to assert ordering.
function makeIxs(n) {
  const out = new Array(n);
  for (let i = 0; i < n; i += 1) {
    out[i] = { id: i, programId: `prog_${i}` };
  }
  return out;
}

test("export exists: splitInstructionsAcrossTransactions is a function", () => {
  assert.strictEqual(typeof splitInstructionsAcrossTransactions, "function");
});

test("35 ixs / default (28) → 2 txs of [28, 7]", () => {
  const ixs = makeIxs(35);
  const out = splitInstructionsAcrossTransactions(ixs);
  assert.strictEqual(out.txCount, 2, `expected 2 txs, got ${out.txCount}`);
  assert.strictEqual(out.transactions.length, 2);
  assert.strictEqual(out.transactions[0].length, 28);
  assert.strictEqual(out.transactions[1].length, 7);
  assert.strictEqual(out.ledgerWarning, false);
});

test("35 ixs / ledger=true → 5 txs of 7 each", () => {
  const ixs = makeIxs(35);
  const out = splitInstructionsAcrossTransactions(ixs, { ledger: true });
  assert.strictEqual(out.txCount, 5, `expected 5 txs, got ${out.txCount}`);
  assert.strictEqual(out.transactions.length, 5);
  for (let i = 0; i < 5; i += 1) {
    assert.strictEqual(
      out.transactions[i].length,
      7,
      `tx[${i}] expected 7 ixs, got ${out.transactions[i].length}`
    );
  }
  assert.strictEqual(out.ledgerWarning, true);
});

test("10 ixs / default (28) → 1 tx of 10", () => {
  const ixs = makeIxs(10);
  const out = splitInstructionsAcrossTransactions(ixs);
  assert.strictEqual(out.txCount, 1);
  assert.strictEqual(out.transactions.length, 1);
  assert.strictEqual(out.transactions[0].length, 10);
});

test("empty input → { transactions: [], txCount: 0 }", () => {
  const out = splitInstructionsAcrossTransactions([]);
  assert.deepStrictEqual(out.transactions, []);
  assert.strictEqual(out.txCount, 0);
});

test("null/undefined input → { transactions: [], txCount: 0 }", () => {
  const a = splitInstructionsAcrossTransactions(null);
  const b = splitInstructionsAcrossTransactions(undefined);
  assert.strictEqual(a.txCount, 0);
  assert.strictEqual(b.txCount, 0);
});

test("instruction order preserved — ix[0] in tx[0][0], last ix in last tx", () => {
  const ixs = makeIxs(35);
  const out = splitInstructionsAcrossTransactions(ixs);
  assert.strictEqual(out.transactions[0][0].id, 0, "ix[0] must be in tx[0][0]");
  const lastTx = out.transactions[out.transactions.length - 1];
  assert.strictEqual(
    lastTx[lastTx.length - 1].id,
    34,
    "ix[34] must be the last ix of the last tx"
  );
  // Walk the full flattened result and confirm monotonic id sequence.
  const flat = out.transactions.reduce((acc, t) => acc.concat(t), []);
  for (let i = 0; i < flat.length; i += 1) {
    assert.strictEqual(flat[i].id, i, `order broke at flat[${i}]`);
  }
});

test("ledger=true preserves order across all 5 chunks", () => {
  const ixs = makeIxs(35);
  const out = splitInstructionsAcrossTransactions(ixs, { ledger: true });
  const flat = out.transactions.reduce((acc, t) => acc.concat(t), []);
  assert.strictEqual(flat.length, 35);
  for (let i = 0; i < flat.length; i += 1) {
    assert.strictEqual(flat[i].id, i);
  }
});

test("custom maxInstructionsPerTx override is honored (cap=10, 35 ixs → 4 txs)", () => {
  const ixs = makeIxs(35);
  const out = splitInstructionsAcrossTransactions(ixs, { maxInstructionsPerTx: 10 });
  assert.strictEqual(out.txCount, 4);
  assert.strictEqual(out.transactions[0].length, 10);
  assert.strictEqual(out.transactions[1].length, 10);
  assert.strictEqual(out.transactions[2].length, 10);
  assert.strictEqual(out.transactions[3].length, 5);
});

test("custom maxOuterIxForLedger override is honored (cap=4, ledger=true, 10 ixs → 3 txs)", () => {
  const ixs = makeIxs(10);
  const out = splitInstructionsAcrossTransactions(ixs, {
    ledger: true,
    maxOuterIxForLedger: 4,
  });
  assert.strictEqual(out.txCount, 3);
  assert.strictEqual(out.transactions[0].length, 4);
  assert.strictEqual(out.transactions[1].length, 4);
  assert.strictEqual(out.transactions[2].length, 2);
});

// --- Summary --------------------------------------------------------------
console.log("");
console.log(`pass: ${pass}   fail: ${fail}`);
if (fail > 0) {
  process.exit(1);
}
