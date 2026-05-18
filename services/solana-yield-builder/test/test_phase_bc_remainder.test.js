"use strict";
/**
 * V7-061 — Meteora DLMM native `initialize_position` (open_position) IX pin test.
 *
 * Asserts the hand-rolled Anchor IX matches the on-chain IDL exactly:
 *
 *   1. Discriminator = sha256("global:initialize_position")[0..8]
 *      = [219, 192, 234, 71, 190, 191, 102, 80]  (verified against
 *      MeteoraAg/dlmm-sdk/idls/dlmm.json `initialize_position`)
 *   2. Account count = 8, in canonical IDL order:
 *      payer, position, lbPair, owner, systemProgram, rent,
 *      eventAuthority, program (self)
 *   3. Signer/writable flags match IDL.
 *   4. Args = lowerBinId (i32 LE) at offset 8, width (i32 LE) at offset 12.
 *   5. Event-authority PDA = findProgramAddress(["__event_authority"], DLMM).
 *
 * Companion test for the existing remove_liquidity_by_range hand-roll.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("crypto");
const { PublicKey, Keypair, SystemProgram, SYSVAR_RENT_PUBKEY } = require("@solana/web3.js");
const meteora = require("../src/adapters/meteora");

const {
  DLMM_PROGRAM,
  DLMM_EVENT_AUTHORITY,
  INITIALIZE_POSITION_DISC,
  buildOpenPosition,
} = meteora._internals;

const EXPECTED_DISC = Buffer.from([219, 192, 234, 71, 190, 191, 102, 80]);

test("DLMM initialize_position discriminator matches sha256('global:initialize_position')[0..8]", () => {
  const computed = crypto.createHash("sha256").update("global:initialize_position").digest().slice(0, 8);
  assert.equal(Buffer.compare(computed, EXPECTED_DISC), 0,
    `sha256 disc mismatch: got ${Array.from(computed)} expected ${Array.from(EXPECTED_DISC)}`);
  assert.equal(Buffer.compare(INITIALIZE_POSITION_DISC, EXPECTED_DISC), 0,
    "module-level INITIALIZE_POSITION_DISC does not equal IDL discriminator");
});

test("DLMM event-authority PDA derives correctly", () => {
  const [pda] = PublicKey.findProgramAddressSync(
    [Buffer.from("__event_authority")],
    DLMM_PROGRAM,
  );
  assert.equal(pda.toBase58(), DLMM_EVENT_AUTHORITY.toBase58(),
    "DLMM_EVENT_AUTHORITY PDA does not match findProgramAddress");
});

test("buildOpenPosition produces IDL-conformant instruction", () => {
  // Deterministic fixtures so the test is reproducible.
  const owner = new PublicKey("11111111111111111111111111111112");
  const lbPair = new PublicKey("So11111111111111111111111111111111111111112"); // wSOL pk reused as opaque fixture
  const positionKp = Keypair.generate();
  const lowerBinId = -1234;  // negative to exercise i32 LE sign-extension
  const width = 70;          // DLMM POSITION_MAX_LENGTH

  const ix = buildOpenPosition({
    lbPair,
    owner,
    lowerBinId,
    width,
    payer: owner,
    position: positionKp.publicKey,
  });

  // (1) programId
  assert.equal(ix.programId.toBase58(), DLMM_PROGRAM.toBase58(),
    "programId must be DLMM mainnet program");

  // (2) data layout: disc(8) || lowerBinId(i32 LE) || width(i32 LE) = 16 bytes
  assert.equal(ix.data.length, 16, `IX data length mismatch (got ${ix.data.length}, expected 16)`);
  assert.equal(Buffer.compare(ix.data.slice(0, 8), EXPECTED_DISC), 0,
    "IX data[0..8] != initialize_position discriminator");
  assert.equal(ix.data.readInt32LE(8), lowerBinId, "lowerBinId i32 LE encoding mismatch");
  assert.equal(ix.data.readInt32LE(12), width, "width i32 LE encoding mismatch");

  // (3) account count + order + flags — exactly 8 accounts in IDL order.
  assert.equal(ix.keys.length, 8, `account count mismatch (got ${ix.keys.length}, expected 8)`);

  const expected = [
    { name: "payer",          pubkey: owner.toBase58(),                       isSigner: true,  isWritable: true  },
    { name: "position",       pubkey: positionKp.publicKey.toBase58(),        isSigner: true,  isWritable: true  },
    { name: "lbPair",         pubkey: lbPair.toBase58(),                      isSigner: false, isWritable: false },
    { name: "owner",          pubkey: owner.toBase58(),                       isSigner: true,  isWritable: false },
    { name: "systemProgram",  pubkey: SystemProgram.programId.toBase58(),     isSigner: false, isWritable: false },
    { name: "rent",           pubkey: SYSVAR_RENT_PUBKEY.toBase58(),          isSigner: false, isWritable: false },
    { name: "eventAuthority", pubkey: DLMM_EVENT_AUTHORITY.toBase58(),        isSigner: false, isWritable: false },
    { name: "program",        pubkey: DLMM_PROGRAM.toBase58(),                isSigner: false, isWritable: false },
  ];
  for (let i = 0; i < expected.length; i += 1) {
    const exp = expected[i];
    const got = ix.keys[i];
    assert.equal(got.pubkey.toBase58(), exp.pubkey,    `keys[${i}] (${exp.name}) pubkey mismatch`);
    assert.equal(got.isSigner,          exp.isSigner,  `keys[${i}] (${exp.name}) isSigner mismatch`);
    assert.equal(got.isWritable,        exp.isWritable, `keys[${i}] (${exp.name}) isWritable mismatch`);
  }
});

test("buildOpenPosition rejects invalid inputs", () => {
  const owner = new PublicKey("11111111111111111111111111111112");
  const lbPair = new PublicKey("So11111111111111111111111111111111111111112");
  const positionKp = Keypair.generate();

  assert.throws(
    () => buildOpenPosition({ lbPair, owner, lowerBinId: 1.5, width: 70, position: positionKp.publicKey }),
    /lowerBinId must be an integer/,
  );
  assert.throws(
    () => buildOpenPosition({ lbPair, owner, lowerBinId: 0, width: 0, position: positionKp.publicKey }),
    /width must be a positive integer/,
  );
  assert.throws(
    () => buildOpenPosition({ lbPair, owner, lowerBinId: 0, width: 10 }),
    /position keypair pubkey required/,
  );
  assert.throws(
    () => buildOpenPosition({ owner, lowerBinId: 0, width: 10, position: positionKp.publicKey }),
    /lbPair required/,
  );
});

// ── Kamino klend bare `deposit_reserve_liquidity` IX pin tests ───────────────
//
// SPEC_COVERAGE: closes the klend.deposit_reserve_liquidity gap. Bare reserve
// supply (kToken minted to user wallet, no obligation parking) is the path
// that direct `klend.deposit_reserve_liquidity` callers hit; Kamino REST and
// the obligation-variant native fallback both bypass it.
//
// Asserts vs canonical IDL
// (programs/klend/src/handlers/handler_deposit_reserve_liquidity.rs):
//   1. Discriminator = sha256("global:deposit_reserve_liquidity")[0..8]
//      = a9c91e7e06cd6644
//   2. IX data = 8-byte disc || u64 LE liquidity_amount
//   3. Account order = owner, reserve, lending_market, lending_market_authority,
//      reserve_liquidity_mint, reserve_liquidity_supply, reserve_collateral_mint,
//      user_source_liquidity, user_destination_collateral,
//      collateral_token_program, liquidity_token_program, instruction_sysvar.
//   4. owner is signer & NOT writable (bare deposit; no SOL transfer).
//   5. build({extra.kind: 'klend_reserve'}) routes to bare deposit instead of
//      REST / obligation-variant fallback.
const { SYSVAR_INSTRUCTIONS_PUBKEY } = require("@solana/web3.js");
const BN = require("bn.js");
const kamino = require("../src/adapters/kamino.js");
const {
  DISC_DEPOSIT_RESERVE,
  KAMINO_LEND_PROGRAM_PK,
  buildDepositReserveLiquidity,
  encodeDepositReserveData,
  anchorSighash: kAnchorSighash,
} = kamino._internals;

// Deterministic real Ed25519 pubkeys (Keypair.fromSeed with seed[0]=1..9).
// Must be valid base58 — `_kaminoCheckHook` runs `new PublicKey()` on
// `reserveLiquidityMint`, which rejects non-base58 strings.
const KLEND_SYNTH = {
  owner:                     "EvFUfisEScFuZSqDXagC17m3bpP32B74dseMHtzQ5TNb",
  reserve:                   "8EYKVyNCsDFHkxos7V4kr8bMouYU2nPJ1QXk2ET8FBc7",
  lendingMarket:             "FjLHdH44f8uN3kxrnxEuuLyLqeR7mp6jZ4d8NT3bk5os",
  lendingMarketAuthority:    "BVX6PY3KWr9W3tdfjFbagugwt5gpSZVTJeWK3zvLsWGg",
  reserveLiquidityMint:      "HUMsgJ1UYJjbGDSE7tPdGygEd4kxk8nYiS9HP76CDPs3",
  reserveLiquiditySupply:    "4XqErRzD9n2DsuNqNjCGX1kStquh1RFSk6Ma8r6zvtkc",
  reserveCollateralMint:     "ByCK5UzUkhifVKW7FPDx1oSeMyP8w6nskqRspnmVq1NB",
  userSourceLiquidity:       "FKZgVHqRQt7hZMEKGEjkvfRpDFcVS5Edspeb6tpxVswd",
  userDestinationCollateral: "DcNxk4Kk7ZHV3iGsZWdPFgHFFPgRbcHKBMXQtTsoY3hT",
};
const TOKEN_PROGRAM_ID_STR = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA";

test("klend deposit_reserve_liquidity: discriminator pin", () => {
  const expected = crypto.createHash("sha256")
    .update("global:deposit_reserve_liquidity").digest().slice(0, 8);
  assert.equal(DISC_DEPOSIT_RESERVE.toString("hex"), expected.toString("hex"));
  // Canonical hex — if this ever changes, klend has shipped a breaking rename.
  assert.equal(DISC_DEPOSIT_RESERVE.toString("hex"), "a9c91e7e06cd6644");
  assert.equal(kAnchorSighash("deposit_reserve_liquidity").toString("hex"),
    DISC_DEPOSIT_RESERVE.toString("hex"));
});

test("klend deposit_reserve_liquidity: encoded data = disc || u64 LE", () => {
  const data = encodeDepositReserveData(new BN("1000000"));
  assert.equal(data.length, 16);
  assert.equal(data.slice(0, 8).toString("hex"), "a9c91e7e06cd6644");
  // 1_000_000 = 0xf4240 → LE = 40 42 0f 00 00 00 00 00
  assert.equal(data.slice(8).toString("hex"), "40420f0000000000");

  // max u64 sanity — no overflow
  const dataMax = encodeDepositReserveData(new BN("18446744073709551615"));
  assert.equal(dataMax.slice(8).toString("hex"), "ffffffffffffffff");
});

test("buildDepositReserveLiquidity: IDL-conformant 12-account IX", () => {
  const ix = buildDepositReserveLiquidity({
    owner: new PublicKey(KLEND_SYNTH.owner),
    liquidityAmount: new BN("1000000"),
    accounts: KLEND_SYNTH,
  });

  assert.equal(ix.programId.toBase58(), KAMINO_LEND_PROGRAM_PK.toBase58());
  assert.equal(ix.programId.toBase58(), "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD");
  assert.equal(ix.data.length, 16);
  assert.equal(ix.data.slice(0, 8).toString("hex"), "a9c91e7e06cd6644");
  assert.equal(ix.data.slice(8).toString("hex"), "40420f0000000000");
  assert.equal(ix.keys.length, 12);

  const expected = [
    { pubkey: KLEND_SYNTH.owner,                     isSigner: true,  isWritable: false },
    { pubkey: KLEND_SYNTH.reserve,                   isSigner: false, isWritable: true  },
    { pubkey: KLEND_SYNTH.lendingMarket,             isSigner: false, isWritable: false },
    { pubkey: KLEND_SYNTH.lendingMarketAuthority,    isSigner: false, isWritable: false },
    { pubkey: KLEND_SYNTH.reserveLiquidityMint,      isSigner: false, isWritable: false },
    { pubkey: KLEND_SYNTH.reserveLiquiditySupply,    isSigner: false, isWritable: true  },
    { pubkey: KLEND_SYNTH.reserveCollateralMint,     isSigner: false, isWritable: true  },
    { pubkey: KLEND_SYNTH.userSourceLiquidity,       isSigner: false, isWritable: true  },
    { pubkey: KLEND_SYNTH.userDestinationCollateral, isSigner: false, isWritable: true  },
    { pubkey: TOKEN_PROGRAM_ID_STR,                  isSigner: false, isWritable: false },
    { pubkey: TOKEN_PROGRAM_ID_STR,                  isSigner: false, isWritable: false },
    { pubkey: SYSVAR_INSTRUCTIONS_PUBKEY.toBase58(), isSigner: false, isWritable: false },
  ];
  for (let i = 0; i < expected.length; i += 1) {
    assert.equal(ix.keys[i].pubkey.toBase58(), expected[i].pubkey,    `slot ${i} pubkey`);
    assert.equal(ix.keys[i].isSigner,          expected[i].isSigner,  `slot ${i} isSigner`);
    assert.equal(ix.keys[i].isWritable,        expected[i].isWritable, `slot ${i} isWritable`);
  }
});

test("buildDepositReserveLiquidity: accepts shorthand args", () => {
  const accountsMin = {
    lendingMarketAuthority: KLEND_SYNTH.lendingMarketAuthority,
    reserveLiquidityMint:   KLEND_SYNTH.reserveLiquidityMint,
    reserveLiquiditySupply: KLEND_SYNTH.reserveLiquiditySupply,
    reserveCollateralMint:  KLEND_SYNTH.reserveCollateralMint,
  };
  const ix = buildDepositReserveLiquidity({
    owner: KLEND_SYNTH.owner,
    market: KLEND_SYNTH.lendingMarket,
    reserve: KLEND_SYNTH.reserve,
    userSource: KLEND_SYNTH.userSourceLiquidity,
    userDestination: KLEND_SYNTH.userDestinationCollateral,
    liquidityAmount: 1_000_000,
    accounts: accountsMin,
  });
  assert.equal(ix.keys[1].pubkey.toBase58(), KLEND_SYNTH.reserve);
  assert.equal(ix.keys[2].pubkey.toBase58(), KLEND_SYNTH.lendingMarket);
  assert.equal(ix.keys[7].pubkey.toBase58(), KLEND_SYNTH.userSourceLiquidity);
  assert.equal(ix.keys[8].pubkey.toBase58(), KLEND_SYNTH.userDestinationCollateral);
});

test("buildDepositReserveLiquidity: liquidityTokenProgram override (Token-2022 reserves)", () => {
  const TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb";
  const ix = buildDepositReserveLiquidity({
    owner: KLEND_SYNTH.owner,
    liquidityAmount: new BN("1"),
    accounts: { ...KLEND_SYNTH, liquidityTokenProgram: TOKEN_2022 },
  });
  // Slot 9 (collateral) classic, slot 10 (liquidity) overridden.
  assert.equal(ix.keys[9].pubkey.toBase58(), TOKEN_PROGRAM_ID_STR);
  assert.equal(ix.keys[10].pubkey.toBase58(), TOKEN_2022);
});

test("buildDepositReserveLiquidity: missing required account throws", () => {
  assert.throws(() => {
    buildDepositReserveLiquidity({
      owner: KLEND_SYNTH.owner,
      liquidityAmount: new BN("1"),
      accounts: { ...KLEND_SYNTH, reserve: undefined },
    });
  }, /missing required account/);
});

function _klendMockConnection() {
  return {
    async getLatestBlockhash() {
      return { blockhash: "11111111111111111111111111111111", lastValidBlockHeight: 0 };
    },
    async simulateTransaction() {
      return { value: { err: null, logs: [], unitsConsumed: 50_000 } };
    },
    async getAccountInfo() { return null; },
  };
}

test("build({extra.kind:'klend_reserve'}) routes to bare deposit_reserve_liquidity", async () => {
  const res = await kamino.build(
    {
      asset: "USDC",
      amount: 1_000_000,
      user: KLEND_SYNTH.owner,
      extra: {
        kind: "klend_reserve",
        liquidityAmountLamports: 1_000_000,
        accounts: KLEND_SYNTH,
      },
    },
    { connection: _klendMockConnection() }
  );
  assert.ok(Array.isArray(res.transactions));
  assert.equal(res.transactions.length, 1);
  const tx = res.transactions[0];
  assert.equal(tx.source, "kamino-native-reserve");
  assert.equal(tx.redemption_program, "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD");
  assert.equal(tx.receiptToken, "kUSDC");
  assert.ok(typeof tx.b64 === "string" && tx.b64.length > 0);
});

test("build({extra.kind:'klend_reserve'}) requires connection + extra.accounts", async () => {
  await assert.rejects(
    kamino.build(
      { asset: "USDC", amount: 1, user: KLEND_SYNTH.owner, extra: { kind: "klend_reserve" } },
      {}
    ),
    /requires a Solana connection/
  );
  await assert.rejects(
    kamino.build(
      { asset: "USDC", amount: 1, user: KLEND_SYNTH.owner, extra: { kind: "klend_reserve" } },
      { connection: _klendMockConnection() }
    ),
    /pass reserve\/lendingMarket/
  );
});
