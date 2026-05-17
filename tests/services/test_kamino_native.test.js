/**
 * V7-009 pin test — Kamino native build.
 *
 * Verifies:
 *   1. JLP_MINT + JITOSOL_MINT symbols are gone from kamino.js.
 *   2. The Jupiter proxy fallback (buildSwap → JLP/JitoSOL) is gone.
 *   3. The KAMINO_LEND_PROGRAM_ID is surfaced at least twice in kamino.js.
 *   4. The hand-rolled deposit IX is buildable, points at
 *      KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD, and carries the
 *      correct Anchor sighash discriminator + u64 LE amount payload.
 *   5. The hand-rolled withdraw IX behaves the same.
 *   6. @kamino-finance/klend-sdk is declared in package.json.
 *
 * Module resolution: this repo doesn't run `npm install` for the
 * solana-yield-builder sidecar in CI. The shared sandbox at
 * /tmp/altsplit-test-deps/node_modules/ has the four runtime deps the
 * adapter touches (@solana/web3.js, bn.js, node-fetch, bs58). NODE_PATH
 * is prepended before any require() so the adapter resolves them.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const Module = require("module");
const crypto = require("crypto");
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
  "services/solana-yield-builder/src/adapters/kamino.js"
);
const PACKAGE_JSON_PATH = path.join(
  REPO_ROOT,
  "services/solana-yield-builder/package.json"
);

const KAMINO_LEND_PROGRAM_ID = "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD";

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

console.log("V7-009 Kamino native build pin tests");
console.log("====================================");

// --- 1. Source-level greps -------------------------------------------------
const source = fs.readFileSync(ADAPTER_PATH, "utf8");

test("JLP_MINT symbol no longer referenced in kamino.js", () => {
  assert.ok(!/JLP_MINT/.test(source), "JLP_MINT still present in adapter source");
});

test("JITOSOL_MINT symbol no longer referenced in kamino.js", () => {
  assert.ok(!/JITOSOL_MINT/.test(source), "JITOSOL_MINT still present in adapter source");
});

test("Jupiter proxy fallback (buildSwap → JLP/JitoSOL outputMint) removed", () => {
  assert.ok(
    !/outputMint\s*[:=][^\n]*JITOSOL/i.test(source),
    "outputMint = JITOSOL_MINT branch still present"
  );
  assert.ok(
    !/outputMint\s*[:=][^\n]*JLP/i.test(source),
    "outputMint = JLP_MINT branch still present"
  );
  assert.ok(
    !/jupiter-fallback/i.test(source),
    "source = 'jupiter-fallback' branch still present"
  );
});

test("KAMINO_LEND_PROGRAM_ID appears at least twice in kamino.js", () => {
  const matches = source.match(/KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD/g) || [];
  assert.ok(
    matches.length >= 2,
    `expected ≥2 hits for program id, got ${matches.length}`
  );
});

// --- 2. Adapter loads + exposes the native IX builders --------------------
const kamino = require(ADAPTER_PATH);

test("adapter exports KAMINO_LEND_PROGRAM_ID", () => {
  assert.strictEqual(kamino.KAMINO_LEND_PROGRAM_ID, KAMINO_LEND_PROGRAM_ID);
});

test("adapter exposes _internals.buildKaminoDepositIx + buildKaminoWithdrawIx", () => {
  assert.ok(kamino._internals, "_internals missing");
  assert.strictEqual(typeof kamino._internals.buildKaminoDepositIx, "function");
  assert.strictEqual(typeof kamino._internals.buildKaminoWithdrawIx, "function");
});

// --- 3. Anchor sighash discriminators are correct -------------------------
test("DISC_DEPOSIT matches sha256('global:deposit_reserve_liquidity_and_obligation_collateral').slice(0,8)", () => {
  const expected = crypto
    .createHash("sha256")
    .update("global:deposit_reserve_liquidity_and_obligation_collateral")
    .digest()
    .slice(0, 8);
  const got = kamino._internals.DISC_DEPOSIT;
  assert.ok(Buffer.isBuffer(got), "DISC_DEPOSIT not a Buffer");
  assert.strictEqual(got.length, 8);
  assert.strictEqual(got.toString("hex"), expected.toString("hex"));
});

test("DISC_WITHDRAW matches sha256('global:withdraw_obligation_collateral_and_redeem_reserve_liquidity').slice(0,8)", () => {
  const expected = crypto
    .createHash("sha256")
    .update("global:withdraw_obligation_collateral_and_redeem_reserve_liquidity")
    .digest()
    .slice(0, 8);
  const got = kamino._internals.DISC_WITHDRAW;
  assert.strictEqual(got.toString("hex"), expected.toString("hex"));
});

// --- 4. Hand-rolled IX construction ---------------------------------------
const { PublicKey } = require("@solana/web3.js");
const BN = require("bn.js");

// Plausible mainnet-shaped pubkeys (32-byte base58, all on the ed25519 curve
// or off — Kamino accepts both since these are mostly PDAs anyway).
const OWNER = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"; // USDC mint as a stand-in pubkey
const DUMMY_ACCOUNTS = {
  obligation: "11111111111111111111111111111112",
  lendingMarket: "11111111111111111111111111111113",
  lendingMarketAuthority: "11111111111111111111111111111114",
  reserve: "11111111111111111111111111111115",
  reserveLiquiditySupply: "11111111111111111111111111111116",
  reserveCollateralMint: "11111111111111111111111111111117",
  reserveDestinationDepositCollateral: "11111111111111111111111111111118",
  userSourceLiquidity: "11111111111111111111111111111119",
  // Withdraw-only:
  reserveSourceCollateral: "1111111111111111111111111111111A",
  userDestinationLiquidity: "1111111111111111111111111111111B",
};

test("buildKaminoDepositIx returns IX with programId = KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD", () => {
  const ix = kamino._internals.buildKaminoDepositIx({
    owner: OWNER,
    amountLamports: new BN("123456789"),
    accounts: DUMMY_ACCOUNTS,
  });
  assert.strictEqual(ix.programId.toBase58(), KAMINO_LEND_PROGRAM_ID);
});

test("buildKaminoDepositIx data = DISC_DEPOSIT || u64 LE amount", () => {
  const amount = new BN("123456789");
  const ix = kamino._internals.buildKaminoDepositIx({
    owner: OWNER,
    amountLamports: amount,
    accounts: DUMMY_ACCOUNTS,
  });
  assert.strictEqual(ix.data.length, 16, `expected 16-byte data, got ${ix.data.length}`);
  const disc = ix.data.slice(0, 8);
  const amountBytes = ix.data.slice(8, 16);
  assert.strictEqual(disc.toString("hex"), kamino._internals.DISC_DEPOSIT.toString("hex"));
  const expectedLE = amount.toArrayLike(Buffer, "le", 8);
  assert.strictEqual(amountBytes.toString("hex"), expectedLE.toString("hex"));
});

test("buildKaminoDepositIx account list starts with owner (signer, writable)", () => {
  const ix = kamino._internals.buildKaminoDepositIx({
    owner: OWNER,
    amountLamports: new BN(1),
    accounts: DUMMY_ACCOUNTS,
  });
  assert.ok(ix.keys.length >= 13, `expected ≥13 keys, got ${ix.keys.length}`);
  assert.strictEqual(ix.keys[0].pubkey.toBase58(), new PublicKey(OWNER).toBase58());
  assert.strictEqual(ix.keys[0].isSigner, true);
  assert.strictEqual(ix.keys[0].isWritable, true);
});

test("buildKaminoDepositIx throws when a required account is missing", () => {
  const bad = Object.assign({}, DUMMY_ACCOUNTS);
  delete bad.reserve;
  assert.throws(() => {
    kamino._internals.buildKaminoDepositIx({
      owner: OWNER,
      amountLamports: new BN(1),
      accounts: bad,
    });
  }, /missing required account "reserve"/);
});

test("buildKaminoWithdrawIx returns IX with programId = KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD", () => {
  const ix = kamino._internals.buildKaminoWithdrawIx({
    owner: OWNER,
    collateralAmount: new BN("987654321"),
    accounts: DUMMY_ACCOUNTS,
  });
  assert.strictEqual(ix.programId.toBase58(), KAMINO_LEND_PROGRAM_ID);
});

test("buildKaminoWithdrawIx data = DISC_WITHDRAW || u64 LE collateral amount", () => {
  const amount = new BN("987654321");
  const ix = kamino._internals.buildKaminoWithdrawIx({
    owner: OWNER,
    collateralAmount: amount,
    accounts: DUMMY_ACCOUNTS,
  });
  assert.strictEqual(ix.data.length, 16);
  assert.strictEqual(
    ix.data.slice(0, 8).toString("hex"),
    kamino._internals.DISC_WITHDRAW.toString("hex")
  );
  assert.strictEqual(
    ix.data.slice(8, 16).toString("hex"),
    amount.toArrayLike(Buffer, "le", 8).toString("hex")
  );
});

// --- 5. package.json declares @kamino-finance/klend-sdk -------------------
test("package.json declares @kamino-finance/klend-sdk dependency", () => {
  const pkg = JSON.parse(fs.readFileSync(PACKAGE_JSON_PATH, "utf8"));
  assert.ok(
    pkg.dependencies && pkg.dependencies["@kamino-finance/klend-sdk"],
    "missing @kamino-finance/klend-sdk in dependencies"
  );
});

// --- Summary --------------------------------------------------------------
console.log("");
console.log(`pass: ${pass}   fail: ${fail}`);
if (fail > 0) {
  process.exit(1);
}
