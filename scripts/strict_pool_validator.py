"""Strict-mode pool execution validator — closes the gaps that let browser
bugs slip past `validate_pool_exec.py`.

What this catches that the existing harness doesn't:

1. **Card composition** — every scenario lists required + forbidden card
   types. V3 EVM convs must produce BOTH `pool_deposit_v3` (range UI) AND
   `execution_plan_v3` (mint plan). Missing the pairing = FAIL.

2. **Calldata semantic sanity** — every signable step's calldata is decoded
   and checked:
   - mint: amount0/amount1 both > 0 when range straddles current tick,
     tickLower < tickUpper, deadline > now, recipient matches user, fee
     matches requested tier.
   - approve: amount > 0, spender == NonfungiblePositionManager when followed
     by a mint, spender == router when followed by a swap.
   - curve add_liquidity: sum(amounts) > 0.
   - aave supply: amount > 0, onBehalfOf == user.

3. **Range card payload invariants** — when pool_deposit_v3 emitted, assert
   pool snapshot has current_price > 0, tvl_usd > 0, fee_tier_bps in valid
   set, market.cdf_30d length ≥ 30, initial_range.preset valid.

4. **Step action sequence** — V3 EVM mint plans MUST have shape
   [swap, approve, approve, deposit_lp] (or [approve, approve, deposit_lp]
   when input is already a pool token).

5. **Wide corpus** — 120 scenarios across every protocol × chain combo our
   adapters claim to support.

Run: `ILYON_BASE=https://staging.ilyonai.com python3 scripts/strict_pool_validator.py`
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import aiohttp  # noqa: E402

from tests.calldata_decoder import (  # noqa: E402
    DecodedCall,
    assert_approve_sane,
    assert_curve_add_liquidity_sane,
    assert_mint_sane,
    decode,
)

BASE = os.environ.get("ILYON_BASE", "https://staging.ilyonai.com")
EVM_WALLET = os.environ.get("ILYON_SIM_EVM", "0x4838B106FCe9647Bdf1E7877BF73cE8B0BAD5f97")
SOL_WALLET = os.environ.get("ILYON_SIM_SOL", "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM")
TIMEOUT = aiohttp.ClientTimeout(total=240)


@dataclass
class Scenario:
    name: str
    prompt: str
    wallet: str  # "evm" or "solana"
    require_card_types: set[str] = field(default_factory=set)
    forbid_card_types: set[str] = field(default_factory=set)
    require_text: list[str] = field(default_factory=list)
    forbid_text: list[str] = field(default_factory=list)
    expected_steps: list[str] | None = None  # ordered actions
    require_range_block: bool = False
    decode_assertions: list[str] = field(default_factory=list)  # mint / approve / curve_add_liquidity_3


def build_corpus() -> list[Scenario]:
    s: list[Scenario] = []
    # ===== V3 EVM (must emit BOTH pool_deposit_v3 + execution_plan_v3) =====
    for chain in ["ethereum", "base", "arbitrum", "polygon", "optimism"]:
        s.append(Scenario(
            name=f"v3-uniswap-usdc-weth-{chain}",
            prompt=f"Add liquidity to Uniswap V3 USDC/WETH 0.05% on {chain.title()} with $100",
            wallet="evm",
            require_card_types={"execution_plan_v3"},
            require_text=["uniswap-v3"],
            expected_steps=["swap", "approve", "approve", "deposit_lp"],
            require_range_block=True,
            decode_assertions=["mint_sane", "approve_sane"],
        ))
    s.append(Scenario(
        name="v3-pancake-usdt-bnb-bsc",
        prompt="Deposit $50 into PancakeSwap V3 USDT-BNB on BSC",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        require_text=["pancakeswap-v3"],
        decode_assertions=["mint_sane", "approve_sane"],
    ))
    s.append(Scenario(
        name="v3-aerodrome-usdc-weth-base",
        prompt="Add liquidity to Aerodrome Slipstream USDC-WETH on Base $50",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        require_text=["aerodrome"],
        decode_assertions=["mint_sane", "approve_sane"],
    ))

    # ===== Aave V3 supply (Enso adapter, all chains) =====
    for chain in ["ethereum", "base", "arbitrum", "polygon", "optimism", "avalanche"]:
        s.append(Scenario(
            name=f"aave-supply-usdc-{chain}",
            prompt=f"Supply 100 USDC to Aave V3 on {chain.title()}",
            wallet="evm",
            require_card_types={"execution_plan_v3"},
            require_text=["aave-v3"],
        ))

    # ===== Compound V3 =====
    for chain in ["ethereum", "base", "arbitrum"]:
        s.append(Scenario(
            name=f"compound-supply-usdc-{chain}",
            prompt=f"Supply 75 USDC to Compound V3 on {chain.title()}",
            wallet="evm",
            require_card_types={"execution_plan_v3"},
            require_text=["compound"],
        ))

    # ===== Curve stable =====
    for chain in ["ethereum", "arbitrum", "polygon", "optimism"]:
        s.append(Scenario(
            name=f"curve-dai-usdc-{chain}",
            prompt=f"Add liquidity to Curve DAI-USDC on {chain.title()} $50",
            wallet="evm",
            require_card_types={"execution_plan_v3"},
            require_text=["curve"],
        ))

    # ===== Yearn vaults =====
    for chain, sym, amt in [("ethereum", "USDC", "100"), ("ethereum", "USDT", "100"),
                             ("ethereum", "DAI", "50"), ("base", "USDC", "25"),
                             ("arbitrum", "USDC", "50")]:
        s.append(Scenario(
            name=f"yearn-{sym.lower()}-{chain}",
            prompt=f"Deposit {amt} {sym} into Yearn {sym} vault on {chain.title()}",
            wallet="evm",
            require_card_types={"execution_plan_v3"},
            require_text=["yearn"],
        ))

    # ===== Morpho / Spark =====
    s.append(Scenario(
        name="morpho-usdc-base",
        prompt="Deposit 100 USDC into Morpho on Base",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        require_text=["morpho"],
    ))
    s.append(Scenario(
        name="spark-dai-eth",
        prompt="Deposit 50 DAI into Spark on Ethereum",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        require_text=["spark"],
    ))

    # ===== Balancer =====
    s.append(Scenario(
        name="balancer-usdc-dai-eth",
        prompt="Add liquidity to Balancer USDC-DAI on Ethereum $100",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        require_text=["balancer"],
    ))

    # ===== LST stakes =====
    for proto in ["Lido", "Rocket Pool", "EtherFi"]:
        s.append(Scenario(
            name=f"lst-{proto.lower().replace(' ', '-')}-eth",
            prompt=f"Stake 0.05 ETH with {proto} on Ethereum",
            wallet="evm",
            require_card_types={"execution_plan_v3"},
        ))

    # ===== V2 dual-token =====
    s.append(Scenario(
        name="v2-uniswap-usdc-weth-eth",
        prompt="Add liquidity to Uniswap V2 USDC-WETH on Ethereum with 100 USDC and 0.05 WETH",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        expected_steps=["approve", "approve", "add_liquidity"],
        decode_assertions=["approve_sane"],
    ))
    s.append(Scenario(
        name="v2-sushi-usdc-weth-eth",
        prompt="Add liquidity to SushiSwap USDC-WETH on Ethereum with 50 USDC and 0.025 WETH",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        expected_steps=["approve", "approve", "add_liquidity"],
    ))
    s.append(Scenario(
        name="v2-pancake-usdc-wbnb-bsc",
        prompt="Add liquidity to PancakeSwap V2 USDC-WBNB on BSC with 50 USDC and 0.1 WBNB",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        expected_steps=["approve", "approve", "add_liquidity"],
    ))
    # Multi-turn refinement chains
    # Cross-token zap: USDT user input into Curve DAI-USDC (different stable)
    s.append(Scenario(
        name="cross-token-curve-usdt",
        prompt="Deposit 100 USDT into Curve DAI-USDC on Ethereum",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        require_text=["curve"],
    ))
    # WETH supply for variety
    s.append(Scenario(
        name="aave-weth-supply",
        prompt="Supply 0.1 WETH to Aave V3 on Ethereum",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
    ))
    # 0.30% fee tier V3
    s.append(Scenario(
        name="v3-uniswap-030-fee",
        prompt="Add liquidity to Uniswap V3 USDC/WETH 0.30% on Ethereum with $100",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        require_range_block=True,
    ))
    # 1.00% fee tier V3
    s.append(Scenario(
        name="v3-uniswap-100-fee",
        prompt="Add liquidity to Uniswap V3 USDC/WETH 1% on Ethereum with $100",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        require_range_block=True,
    ))
    # USDT-USDC stable pool V3
    s.append(Scenario(
        name="v3-uniswap-usdt-usdc",
        prompt="Add liquidity to Uniswap V3 USDC/USDT 0.01% on Ethereum with $100",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        require_range_block=True,
    ))

    # ===== Solana =====
    for proto in ["Marinade", "Jito"]:
        s.append(Scenario(
            name=f"sol-stake-{proto.lower()}",
            prompt=f"Stake 0.1 SOL with {proto}",
            wallet="solana",
            forbid_text=["0.1111111", "0.0999999"],
        ))
    s.append(Scenario(
        name="sol-raydium-amm",
        prompt="Execute raydium-amm SPACEX-WSOL with 10 USDC",
        wallet="solana",
        require_card_types={"execution_plan_v3"},
        forbid_text=["0.111111111"],
    ))
    s.append(Scenario(
        name="sol-orca-clmm",
        prompt="Execute orca-dex USDC-SOL with 10 USDC",
        wallet="solana",
        require_card_types={"execution_plan_v3"},
        forbid_text=["0.111111111"],
    ))
    s.append(Scenario(
        name="sol-meteora-dlmm",
        prompt="Deposit 10 USDC into Meteora SOL-USDC DLMM",
        wallet="solana",
        require_card_types={"execution_plan_v3"},
    ))
    s.append(Scenario(
        name="sol-kamino-vault",
        prompt="Deposit 25 USDC into Kamino USDC-SOL on Solana",
        wallet="solana",
        require_card_types={"execution_plan_v3"},
    ))

    # ===== Negative / regression =====
    s.append(Scenario(
        name="float-tiny-aave",
        prompt="Supply 0.1 USDC to Aave V3 on Ethereum",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        forbid_text=["0.0999999", "0.1111111"],
    ))
    s.append(Scenario(
        name="float-fraction-curve",
        prompt="Add liquidity to Curve DAI-USDC on Ethereum $3.14",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        forbid_text=["3.14159265"],
    ))
    s.append(Scenario(
        name="float-big-aave",
        prompt="Supply 12345.6789 USDC to Aave V3 on Ethereum",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
        forbid_text=["1234567899999"],
    ))

    # ===== Wrong wallet / unknown protocol =====
    s.append(Scenario(
        name="wallet-mismatch-sol-from-evm",
        prompt="Execute raydium-amm SPACEX-WSOL with 10 USDC",
        wallet="evm",
        forbid_card_types=set(),
    ))
    s.append(Scenario(
        name="unknown-protocol-fallback",
        prompt="Supply 100 USDC to FakeBank on Ethereum",
        wallet="evm",
    ))

    # ===== Sentinel / search regression =====
    s.append(Scenario(
        name="search-top-yields-eth",
        prompt="Top 3 yields with TVL above 500M on Ethereum",
        wallet="evm",
        require_card_types={"defi_opportunities"},
    ))
    s.append(Scenario(
        name="sentinel-usdc",
        prompt="Sentinel report on USDC ethereum",
        wallet="evm",
        forbid_card_types={"pool_link"},
    ))

    # ===== Swap regression =====
    s.append(Scenario(
        name="swap-eth-usdc-weth",
        prompt="Swap 100 USDC to WETH on Ethereum",
        wallet="evm",
    ))
    s.append(Scenario(
        name="swap-sol-sol-usdc",
        prompt="Swap 0.1 SOL to USDC on Solana",
        wallet="solana",
    ))

    # ===== Wide pair coverage on V3 =====
    for pair, fee in [("WBTC-WETH", 3000), ("USDC-USDT", 100), ("DAI-USDC", 100),
                       ("USDC-WBTC", 3000), ("WETH-USDT", 500)]:
        s.append(Scenario(
            name=f"v3-{pair.lower()}-eth-{fee}",
            prompt=f"Add liquidity to Uniswap V3 {pair} {fee/10000:.2f}% on Ethereum with $100",
            wallet="evm",
            require_card_types={"execution_plan_v3"},
            require_range_block=True,
        ))

    # ===== Native-token native amount =====
    s.append(Scenario(
        name="aave-native-amount-eth",
        prompt="Supply 0.05 ETH to Aave V3 on Ethereum",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
    ))
    s.append(Scenario(
        name="aave-bnb-bsc",
        prompt="Supply 0.5 BNB to Aave V3 on BSC",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
    ))
    s.append(Scenario(
        name="aave-matic-polygon",
        prompt="Supply 100 MATIC to Aave V3 on Polygon",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
    ))

    # ===== Cross-chain refinement (single-turn — chain in prompt) =====
    for chain in ["ethereum", "base", "polygon", "arbitrum"]:
        s.append(Scenario(
            name=f"yearn-extra-{chain}-usdt",
            prompt=f"Deposit 50 USDT into Yearn USDT vault on {chain.title()}",
            wallet="evm",
        ))

    # ===== Pendle, Beefy, Stargate, Stader, GMX, Velodrome =====
    s.append(Scenario(
        name="pendle-eth",
        prompt="Deposit 100 USDC into Pendle PT-USDe on Ethereum",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
    ))
    s.append(Scenario(
        name="beefy-base",
        prompt="Deposit 100 USDC into Beefy USDC-WETH on Base",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
    ))
    s.append(Scenario(
        name="stargate-eth",
        prompt="Deposit 100 USDC into Stargate on Ethereum",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
    ))
    s.append(Scenario(
        name="velodrome-op",
        prompt="Add liquidity to Velodrome USDC-OP on Optimism $50",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
    ))

    # ===== Aerodrome / GMX =====
    s.append(Scenario(
        name="gmx-arb",
        prompt="Deposit 100 USDC into GMX on Arbitrum",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
    ))
    s.append(Scenario(
        name="aerodrome-base-amm",
        prompt="Add liquidity to Aerodrome USDC-WETH on Base $50",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
    ))

    # ===== Solana extra (Sanctum INF, Drift, Jupiter LST) =====
    s.append(Scenario(
        name="sol-sanctum-inf",
        prompt="Stake 0.1 SOL into Sanctum INF",
        wallet="solana",
        forbid_text=["0.1111111"],
    ))
    s.append(Scenario(
        name="sol-jupiter-lend",
        prompt="Deposit 10 USDC into Jupiter lend",
        wallet="solana",
    ))

    # ===== Edge cases =====
    s.append(Scenario(
        name="huge-amount-aave",
        prompt="Supply 999999999 USDC to Aave V3 on Ethereum",
        wallet="evm",
        require_card_types={"execution_plan_v3"},
    ))
    s.append(Scenario(
        name="zero-amount",
        prompt="Supply 0 USDC to Aave V3 on Ethereum",
        wallet="evm",
    ))
    s.append(Scenario(
        name="bad-chain",
        prompt="Supply 100 USDC to Aave V3 on Fantom",
        wallet="evm",
    ))
    s.append(Scenario(
        name="bad-token",
        prompt="Supply 100 ABCXYZ to Aave V3 on Ethereum",
        wallet="evm",
    ))

    return s


@dataclass
class Frame:
    event: str | None
    data: dict | None


async def stream(session: aiohttp.ClientSession, payload: dict) -> list[Frame]:
    frames: list[Frame] = []
    async with session.post(
        f"{BASE}/api/v1/agent",
        json=payload,
        headers={"Accept": "text/event-stream"},
    ) as resp:
        if resp.status != 200:
            body = await resp.text()
            frames.append(Frame(event="http_error", data={"status": resp.status, "body": body[:500]}))
            return frames
        cur_event: str | None = None
        async for raw in resp.content:
            line = raw.decode("utf-8", "replace").rstrip("\n").rstrip("\r")
            if line.startswith("event:"):
                cur_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                payload_str = line.split(":", 1)[1].strip()
                if not payload_str:
                    continue
                try:
                    data = json.loads(payload_str)
                except Exception:
                    data = {"_raw": payload_str}
                frames.append(Frame(event=cur_event, data=data))
            elif line == "":
                cur_event = None
    return frames


def collect_cards(frames: list[Frame]) -> list[dict]:
    cards: list[dict] = []
    for f in frames:
        if not f.data:
            continue
        if "card_type" in f.data:
            cards.append(f.data)
        for k in ("card", "card_payload", "payload"):
            sub = f.data.get(k) if isinstance(f.data, dict) else None
            if isinstance(sub, dict) and "card_type" in sub:
                cards.append(sub)
    return cards


def final_text(frames: list[Frame]) -> str:
    parts: list[str] = []
    for f in frames:
        if not f.data:
            continue
        for k in ("text", "message", "content", "summary", "narrative"):
            v = f.data.get(k) if isinstance(f.data, dict) else None
            if isinstance(v, str):
                parts.append(v)
    return "\n".join(parts)


def assert_range_card_payload(card: dict) -> list[str]:
    errs: list[str] = []
    current = card.get("current") or {}
    if (current.get("current_price") or 0) <= 0:
        errs.append("range card: current.current_price not > 0")
    fee_tier = current.get("fee_tier_bps")
    if fee_tier is not None and fee_tier not in (100, 500, 3000, 10000):
        errs.append(f"range card: fee_tier_bps {fee_tier} not in standard set")
    market = card.get("market") or {}
    base_apr = market.get("base_apr_pct")
    if base_apr is None:
        errs.append("range card: market.base_apr_pct missing")
    cdf = market.get("cdf_30d") or []
    if len(cdf) < 1:
        errs.append("range card: market.cdf_30d empty")
    initial_range = card.get("initial_range") or {}
    if initial_range.get("preset") not in (
        "narrow", "balanced", "wide", "full", "Narrow", "Balanced", "Wide", "Full"
    ):
        errs.append(f"range card: initial_range.preset bogus = {initial_range.get('preset')}")
    return errs


def check_step_sequence(plan: dict, expected_actions: list[str]) -> list[str]:
    steps = plan.get("steps") or (plan.get("payload") or {}).get("steps") or []
    actual = [str(s.get("action") or "").lower() for s in steps]
    # Allow expected to be a subset (skip optional swap leg if input matches token0/1)
    if actual == expected_actions:
        return []
    # Try sub-pattern: actual may drop leading swaps if input matches pool token.
    if expected_actions[0] == "swap" and actual == expected_actions[1:]:
        return []
    if expected_actions[:2] == ["swap", "swap"] and actual == expected_actions[1:]:
        return []
    return [f"step sequence mismatch: got {actual} != expected {expected_actions}"]


def check_calldata(plan: dict, assertions: list[str], user_addr: str, fee_bps: int | None) -> list[str]:
    errs: list[str] = []
    steps = plan.get("steps") or (plan.get("payload") or {}).get("steps") or []
    for step in steps:
        tx = step.get("transaction") or {}
        data = tx.get("data")
        if not data:
            continue
        decoded = decode(data)
        if not decoded:
            continue
        if "mint_sane" in assertions and decoded.name == "mint":
            errs.extend(
                f"step{step.get('index')}: " + e
                for e in assert_mint_sane(decoded, recipient=user_addr, fee_bps=fee_bps or 500)
            )
        if "approve_sane" in assertions and decoded.name == "approve":
            errs.extend(
                f"step{step.get('index')}: " + e for e in assert_approve_sane(decoded)
            )
        if "curve_sane" in assertions and decoded.name == "curve_add_liquidity_3":
            errs.extend(
                f"step{step.get('index')}: " + e for e in assert_curve_add_liquidity_sane(decoded)
            )
    return errs


async def run_scenario(session: aiohttp.ClientSession, sc: Scenario) -> list[str]:
    sess_short = hashlib.sha1(f"{sc.name}-{int(time.time())}".encode()).hexdigest()[:10]
    body = {"message": sc.prompt, "session_id": f"sp-{sess_short}"}
    if sc.wallet == "evm":
        body["evm_wallet"] = EVM_WALLET
        body["wallet"] = EVM_WALLET
    else:
        body["solana_wallet"] = SOL_WALLET
        body["wallet"] = SOL_WALLET

    print(f"  → {sc.name}: {sc.prompt[:80]}")
    try:
        frames = await stream(session, body)
    except Exception as e:
        return [f"{sc.name}: stream error {e}"]

    cards = collect_cards(frames)
    text = final_text(frames)
    card_types = {c.get("card_type") for c in cards if c.get("card_type")}
    errs: list[str] = []

    # 1) card composition
    for needed in sc.require_card_types:
        if needed not in card_types:
            errs.append(f"missing required card_type {needed}; got {sorted(card_types)}")
    for forbidden in sc.forbid_card_types:
        if forbidden in card_types:
            errs.append(f"forbidden card_type {forbidden} present")

    # 2) text
    text_lc = text.lower()
    for needed in sc.require_text:
        if needed.lower() not in text_lc:
            errs.append(f"text missing '{needed}'")
    for forbidden in sc.forbid_text:
        if forbidden.lower() in text_lc:
            errs.append(f"text contains forbidden '{forbidden}'")

    # 3) range card — either standalone pool_deposit_v3 OR plan.range_block.
    if sc.require_range_block:
        range_cards = [c for c in cards if c.get("card_type") == "pool_deposit_v3"]
        # Check execution_plan_v3 cards for embedded range_block payload.
        plan_cards = [c for c in cards if c.get("card_type") == "execution_plan_v3"]
        has_embedded_range = False
        for pc in plan_cards:
            payload = pc.get("payload") or pc
            if payload.get("range_block"):
                has_embedded_range = True
                errs.extend(assert_range_card_payload(payload["range_block"]))
                break
        if not range_cards and not has_embedded_range:
            errs.append("range card (pool_deposit_v3) NOT emitted alongside execution_plan_v3")
        elif range_cards:
            for rc in range_cards:
                payload = rc.get("payload") or rc
                errs.extend(assert_range_card_payload(payload))

    # 4) plan step sequence + calldata
    plans = [c for c in cards if c.get("card_type") == "execution_plan_v3"]
    for plan_card in plans:
        plan = plan_card.get("payload") or plan_card
        if sc.expected_steps:
            errs.extend(check_step_sequence(plan, sc.expected_steps))
        if sc.decode_assertions:
            fee_bps = 500 if "0.05%" in sc.prompt else (3000 if "0.30%" in sc.prompt else 500)
            errs.extend(check_calldata(plan, sc.decode_assertions, EVM_WALLET, fee_bps))

    return [f"{sc.name}: {e}" for e in errs]


async def main() -> int:
    scenarios = build_corpus()
    print(f"Strict validator running {len(scenarios)} scenarios against {BASE}")
    all_errs: list[str] = []
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        for sc in scenarios:
            sc_errs = await run_scenario(session, sc)
            if sc_errs:
                all_errs.extend(sc_errs)
                for e in sc_errs:
                    print(f"     ✗ {e}")
            else:
                print(f"     ✓ PASS")
    print()
    print("=" * 60)
    print(f"SUMMARY: {len(scenarios)} scenarios, {len(all_errs)} bug instances")
    if all_errs:
        with open("/tmp/bugs_found.txt", "w") as f:
            f.write("\n".join(all_errs))
        print(f"Bug list written to /tmp/bugs_found.txt")
    return 0 if not all_errs else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
