/**
 * V7-031 pin test — Orca Token-2022 transfer-hook gate.
 *
 * The 5 other Solana adapters (jlp, raydium, kamino, meteora, sanctum,
 * marinade) already call _token_safety.checkTransferHook on every input
 * mint. Orca was the only adapter that imported the helper but never
 * invoked it. This test pins:
 *
 *   1. orca.buildOpen returns a typed TRANSFER_HOOK_NOT_ALLOWED blocker
 *      when the input mint is a Token-2022 mint with a transfer-hook
 *      extension pointing to a program id that is NOT in the sidecar's
 *      ALLOWED_TRANSFER_HOOKS allowlist.
 *   2. The same call returns NO transfer-hook blocker (passes the gate)
 *      when the hook program id IS on the allowlist — we inject one
 *      into the allowlist Set at test time to avoid having to construct
 *      a base58 string that matches a specific seed entry byte-for-byte.
 *   3. The blocker carries `code`, `blocker`, `kind: "blocker"`, an empty
 *      transactions array, and includes the offending mint string in the
 *      message — the typed-recovery contract the orchestrator depends on.
 *   4. The ALLOWED_TRANSFER_HOOKS + ALLOWED_HOOK_NAMES sets advertise the
 *      seed entries (`confidential_transfer`, `memo`) — mirrors
 *      test_token_safety.test.js. Belt-and-braces guard against the
 *      allowlist getting accidentally cleared during this work.
 *
 * Deterministic — no network calls. `connection.getAccountInfo` is an
 * inline mock that dispatches on pubkey.
 *
 * Module resolution: mirrors test_kamino_native.test.js — NODE_PATH points
 * at /tmp/altsplit-test-deps/node_modules which has @solana/web3.js + bn.js.
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
const SAFETY_PATH = path.join(REPO_ROOT, "services/solana-yield-builder/src/adapters/_token_safety.js");

const TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb";
const WHIRLPOOL_PROGRAM_ID = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc";

// USDC mainnet mint — resolveMint("USDC") returns this; orca.buildOpen
// then queries its account info, which our mock answers with the Token-2022
// hook-bearing fixture.
const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
const FAKE_WHIRLPOOL = "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtL45EHRJ5Y3UQ8";
const FAKE_USER = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM";

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

console.log("V7-031 Orca Token-2022 transfer-hook gate pin tests");
console.log("====================================================");

const orca = require(ORCA_PATH);
const safety = require(SAFETY_PATH);

// ── TLV fixture builder ─────────────────────────────────────────────────────
// Construct the bytes of a Token-2022 mint account that declares a TransferHook
// extension pointing at `hookProgramIdBytes` (32 bytes). Matches the layout
// the real Token-2022 program writes (see spl-token-2022 state.rs):
//   bytes 0..82    base Mint::LEN (we leave zeroed — irrelevant to the parser)
//   byte 165       account-type discriminator (1=Mint, also zeroed for test)
//   bytes 166..    TLV stream of (u16LE type, u16LE len, payload)
//                  TransferHook payload = programId(32) || authority(32)
//
// The parser in _token_safety.js walks from EXTENSIONS_START=166, reads the
// type+len header, and returns the first 32 payload bytes when type === 14.
function buildToken2022MintWithHook(hookProgramIdBytes) {
  if (!Buffer.isBuffer(hookProgramIdBytes) || hookProgramIdBytes.length !== 32) {
    throw new Error("hookProgramIdBytes must be a 32-byte Buffer");
  }
  // 166 (prefix) + 4 (TLV header) + 64 (transfer-hook payload) = 234 bytes
  const buf = Buffer.alloc(234);
  buf.writeUInt16LE(14, 166);     // ExtensionType::TransferHook = 14
  buf.writeUInt16LE(64, 168);     // payload length = 64
  hookProgramIdBytes.copy(buf, 170, 0, 32); // programId in first 32 bytes
  // bytes 202..233 = authority (32 bytes) — left zeroed; irrelevant to parser
  return buf;
}

function makeToken2022MintInfo(hookProgramIdBytes) {
  return {
    owner: { toString: () => TOKEN_2022_PROGRAM_ID },
    data: buildToken2022MintWithHook(hookProgramIdBytes),
  };
}

// Whirlpool fixture — passes isWhirlpoolInitialized so the orca.buildOpen
// flow reaches the input-mint hook gate (which is the surface under test).
const VALID_WHIRLPOOL_INFO = {
  owner: { toString: () => WHIRLPOOL_PROGRAM_ID },
  data: Buffer.alloc(0),
};

function makeConn(lookups) {
  return {
    getAccountInfo: async (pubkey) => {
      const key =
        typeof pubkey === "string"
          ? pubkey
          : (typeof pubkey.toBase58 === "function" ? pubkey.toBase58() : String(pubkey));
      return Object.prototype.hasOwnProperty.call(lookups, key) ? lookups[key] : null;
    },
    getLatestBlockhash: async () => ({ blockhash: "11111111111111111111111111111111", lastValidBlockHeight: 0 }),
  };
}

// Deterministic 32-byte "bad" hook program id — pattern 0x01..0x20 — its
// base58 encoding is computed via the helper's own parser so we can both
// assert the blocker carries the same string AND (in the pass case) inject
// it into ALLOWED_TRANSFER_HOOKS.
const badHookBytes = Buffer.alloc(32);
for (let i = 0; i < 32; i += 1) badHookBytes[i] = i + 1;
const expectedHookBase58 = safety._parseTransferHookProgramId(buildToken2022MintWithHook(badHookBytes));

(async () => {
  // ── allowlist sanity (mirrors test_token_safety.test.js) ─────────────────
  test("ALLOWED_TRANSFER_HOOKS has at least 1 seed entry", () => {
    assert.ok(safety.ALLOWED_TRANSFER_HOOKS instanceof Set);
    assert.ok(safety.ALLOWED_TRANSFER_HOOKS.size >= 1, "allowlist must seed at least one entry");
  });

  test("ALLOWED_HOOK_NAMES advertises confidential_transfer + memo", () => {
    assert.ok(safety.ALLOWED_HOOK_NAMES instanceof Set);
    assert.ok(safety.ALLOWED_HOOK_NAMES.has("confidential_transfer"), "missing confidential_transfer");
    assert.ok(safety.ALLOWED_HOOK_NAMES.has("memo"), "missing memo");
  });

  test("_parseTransferHookProgramId returns a non-null base58 string for our fixture", () => {
    assert.ok(typeof expectedHookBase58 === "string" && expectedHookBase58.length > 0,
      `parser returned ${expectedHookBase58} — fixture or parser broken`);
  });

  // ── fail case: non-allowlisted hook → blocker ────────────────────────────
  await test("orca.buildOpen returns TRANSFER_HOOK_NOT_ALLOWED when input mint declares non-allowlisted hook", async () => {
    // Belt-and-braces: ensure the fixture's hook is NOT already allowlisted
    // (a previous test must not have leaked an injection).
    safety.ALLOWED_TRANSFER_HOOKS.delete(expectedHookBase58);

    const conn = makeConn({
      [FAKE_WHIRLPOOL]: VALID_WHIRLPOOL_INFO,
      [USDC_MINT]: makeToken2022MintInfo(badHookBytes),
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
    assert.ok(res && typeof res === "object", "expected blocker object");
    assert.strictEqual(res.code, "TRANSFER_HOOK_NOT_ALLOWED",
      `expected code=TRANSFER_HOOK_NOT_ALLOWED, got ${res.code} (msg: ${res.message})`);
    assert.strictEqual(res.blocker, "TRANSFER_HOOK_NOT_ALLOWED");
    assert.strictEqual(res.kind, "blocker");
    assert.strictEqual(res.mint, USDC_MINT, "blocker.mint should name the offending input mint");
    assert.strictEqual(res.hookProgramId, expectedHookBase58, "blocker.hookProgramId mismatch");
    assert.ok(Array.isArray(res.transactions) && res.transactions.length === 0, "blocker.transactions must be []");
    assert.ok(String(res.message || "").includes(USDC_MINT), "blocker.message must name the offending mint");
  });

  // ── pass case: hook on allowlist → no transfer-hook blocker ──────────────
  await test("orca.buildOpen passes the hook gate when programId IS on the allowlist", async () => {
    // Inject our fixture hook into the allowlist for this single test.
    safety.ALLOWED_TRANSFER_HOOKS.add(expectedHookBase58);
    try {
      const conn = makeConn({
        [FAKE_WHIRLPOOL]: VALID_WHIRLPOOL_INFO,
        [USDC_MINT]: makeToken2022MintInfo(badHookBytes),
      });
      let res;
      let threw = null;
      try {
        res = await orca.buildOpen(
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
      } catch (err) {
        threw = err;
      }
      // After the hook gate passes, the next step is `_loadWhirlpoolSdk()` →
      // `client.getPool(...)`. In the CI sandbox the SDK may or may not be on
      // disk; either way, the failure mode we care about is the ABSENCE of a
      // TRANSFER_HOOK_NOT_ALLOWED blocker. Accept either:
      //   - a thrown error whose message is NOT a transfer-hook string
      //   - a returned object that is NOT a transfer-hook blocker
      const transferHookBlocker =
        (res && res.code === "TRANSFER_HOOK_NOT_ALLOWED") ||
        (threw && /TRANSFER_HOOK_NOT_ALLOWED/.test(String(threw.message || "")));
      assert.ok(!transferHookBlocker,
        `hook gate misfired — got blocker/error: ${res ? res.code : (threw && threw.message)}`);
    } finally {
      // Always clean up the allowlist injection so the file is idempotent.
      safety.ALLOWED_TRANSFER_HOOKS.delete(expectedHookBase58);
    }
  });

  // ── pass case 2: legacy SPL mint (info=null) bypasses the gate ──────────
  await test("orca.buildOpen does not emit a transfer-hook blocker when input mint info is null (legacy SPL)", async () => {
    const conn = makeConn({
      [FAKE_WHIRLPOOL]: VALID_WHIRLPOOL_INFO,
      // USDC_MINT not in lookup → getAccountInfo returns null → checkTransferHook → {ok:true}
    });
    let res;
    let threw = null;
    try {
      res = await orca.buildOpen(
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
    } catch (err) {
      threw = err;
    }
    const transferHookBlocker =
      (res && res.code === "TRANSFER_HOOK_NOT_ALLOWED") ||
      (threw && /TRANSFER_HOOK_NOT_ALLOWED/.test(String(threw.message || "")));
    assert.ok(!transferHookBlocker,
      `legacy SPL mint (null info) misclassified as hook-bearing: ${res ? res.code : (threw && threw.message)}`);
  });

  // ── Summary ───────────────────────────────────────────────────────────────
  console.log("");
  console.log(`pass: ${pass}   fail: ${fail}`);
  if (fail > 0) {
    process.exit(1);
  }
})();
