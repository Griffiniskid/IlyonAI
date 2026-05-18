"""V4 multi-turn conversation matrix.

100+ named conversation chains, each ≥4 turns, exercising the full IlyonAI
spec surface end-to-end. Each chain carries a sticky session_id; turn N+1
must reuse the session_id and verify continuity (pool/protocol/chain/amount
carried across turns).

This is DATA. The runner (tests/harness/v4_runner.py) fires turns against
staging, dumps raw SSE to /tmp/v3-deep/v4/<chain_id>/turn_N.txt, and prints
per-turn assertion hints to remind the validator what to read for by hand.

NO mechanical pass/fail. Validator reads every SSE byte and writes verdict
prose to /tmp/v3-deep/_log.md.

Schema:
    Chain.id          unique short slug
    Chain.category    one of A/B/C/D/E/F/G/H/I (see categories below)
    Chain.session_id  sticky across turns (auto-prefixed with v4-<id>)
    Chain.notes       what this chain is testing
    Chain.turns[]
        .user_message
        .expect_card     (optional) expected primary card_type
        .expect_status   (optional) expected status (ready/blocked/refused)
        .expect_action   (optional) expected step.action
        .expect_blockers (optional) expected blocker_codes (any-of)
        .expect_selectors(optional) expected 4-byte selectors in tx.data
        .expect_fields   (optional) k→v in primary card to verify

Categories:
    A — Search → refine → execute (20)
    B — Strategy compose (15)
    C — Pool refinement (15)
    D — Lifecycle close-out (15)
    E — Cross-chain composed plan (15)
    F — Stuck-balance + recovery (10)
    G — Failure-continuation (10)
    H — §7 funding S1-S15 (15)
    I — §11 D.5/D.6 session-key flow (5)

Total: 120 chains.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Turn:
    user_message: str
    expect_card: str | None = None
    expect_status: str | None = None
    expect_action: str | None = None
    expect_blockers: list[str] = field(default_factory=list)
    expect_selectors: list[str] = field(default_factory=list)
    expect_fields: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass
class Chain:
    id: str
    category: str
    notes: str
    turns: list[Turn]

    @property
    def session_id(self) -> str:
        return f"v4-{self.id}"


# ---------------------------------------------------------------------------
# Category A — Search → refine → execute (20 chains × 4-5 turns)
# ---------------------------------------------------------------------------
CATEGORY_A: list[Chain] = [
    Chain(
        id="A01_aave_base_usdc",
        category="A",
        notes="USDC lending Base → filter Aave only → switch to $250 → switch to Optimism → execute",
        turns=[
            Turn("Find me USDC lending on Base", expect_card="pool_link"),
            Turn("Filter to Aave only", expect_card="pool_link"),
            Turn("Use $250 instead", expect_card="pool_link"),
            Turn("Actually on Optimism", expect_card="pool_link"),
            Turn(
                "Execute on Aave V3 with 250 USDC",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="supply",
                expect_selectors=["0x617ba037"],
            ),
        ],
    ),
    Chain(
        id="A02_steth_lido_filter",
        category="A",
        notes="ETH staking → Lido pin → 0.5 ETH → switch to LRT (Renzo) → execute",
        turns=[
            Turn("What's the best place to stake my ETH?", expect_card="pool_link"),
            Turn("Lido only", expect_card="pool_link"),
            Turn("Use 0.5 ETH", expect_card="pool_link"),
            Turn("Actually I want a liquid restaking token instead — Renzo", expect_card="pool_link"),
            Turn(
                "Stake 0.5 ETH on Renzo",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="stake",
                expect_selectors=["0xfdaf83a3"],
            ),
        ],
    ),
    Chain(
        id="A03_low_risk_only",
        category="A",
        notes="Low-risk USDC yield → only blue chip → drill into top pool → execute",
        turns=[
            Turn("Show me low risk USDC yield on Ethereum", expect_card="pool_link"),
            Turn("Only blue-chip protocols", expect_card="pool_link"),
            Turn("Show the top one", expect_card="pool_link"),
            Turn(
                "Deposit 500 USDC there",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="supply",
            ),
        ],
    ),
    Chain(
        id="A04_compound_base",
        category="A",
        notes="Compound V3 USDC Base → 100 USDC → switch to USDbC → execute",
        turns=[
            Turn("USDC lending on Base — Compound V3 only", expect_card="pool_link"),
            Turn("Use 100 USDC", expect_card="pool_link"),
            Turn("What's the deposit cap?", expect_card="text"),
            Turn(
                "Supply 100 USDC to Compound V3 Base",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="supply",
            ),
        ],
    ),
    Chain(
        id="A05_yearn_eth_vault",
        category="A",
        notes="Yearn V3 USDC vault on Ethereum",
        turns=[
            Turn("Yearn V3 USDC vaults", expect_card="pool_link"),
            Turn("Ethereum only", expect_card="pool_link"),
            Turn("Use 250 USDC", expect_card="pool_link"),
            Turn(
                "Execute deposit to top Yearn V3 USDC vault",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="supply",
            ),
        ],
    ),
    Chain(
        id="A06_morpho_blue",
        category="A",
        notes="Morpho Blue USDC → top market → 150 USDC → execute",
        turns=[
            Turn("Morpho Blue USDC markets", expect_card="pool_link"),
            Turn("Top market only", expect_card="pool_link"),
            Turn("Use 150 USDC", expect_card="pool_link"),
            Turn(
                "Execute the deposit",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="supply",
            ),
        ],
    ),
    Chain(
        id="A07_spark_dai",
        category="A",
        notes="Spark DAI sDAI savings",
        turns=[
            Turn("Where can I earn on DAI?", expect_card="pool_link"),
            Turn("Spark only", expect_card="pool_link"),
            Turn("100 DAI", expect_card="pool_link"),
            Turn(
                "Execute Spark DAI deposit",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="supply",
            ),
        ],
    ),
    Chain(
        id="A08_sky_savings_rate",
        category="A",
        notes="Sky Savings Rate (former Maker)",
        turns=[
            Turn("Sky DAI savings rate", expect_card="pool_link"),
            Turn("What's the APY?", expect_card="pool_link"),
            Turn("Use 250 USDS", expect_card="pool_link"),
            Turn(
                "Deposit 250 USDS to Sky savings",
                expect_card="execution_plan_v3",
                expect_status="ready",
            ),
        ],
    ),
    Chain(
        id="A09_aave_arb_usdt",
        category="A",
        notes="Aave V3 Arbitrum USDT",
        turns=[
            Turn("USDT yield on Arbitrum", expect_card="pool_link"),
            Turn("Aave V3 only", expect_card="pool_link"),
            Turn("Use $500 USDT", expect_card="pool_link"),
            Turn(
                "Execute Aave V3 USDT supply on Arbitrum",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="supply",
                expect_selectors=["0x617ba037"],
            ),
        ],
    ),
    Chain(
        id="A10_aave_polygon_dai",
        category="A",
        notes="Aave V3 Polygon DAI",
        turns=[
            Turn("DAI lending on Polygon", expect_card="pool_link"),
            Turn("Aave only", expect_card="pool_link"),
            Turn("100 DAI", expect_card="pool_link"),
            Turn(
                "Supply 100 DAI to Aave V3 Polygon",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="supply",
            ),
        ],
    ),
    Chain(
        id="A11_aave_opt_weth",
        category="A",
        notes="Aave V3 Optimism WETH",
        turns=[
            Turn("ETH yield on Optimism", expect_card="pool_link"),
            Turn("Aave V3 only", expect_card="pool_link"),
            Turn("0.1 ETH", expect_card="pool_link"),
            Turn(
                "Deposit 0.1 ETH to Aave V3 Optimism",
                expect_card="execution_plan_v3",
                expect_status="ready",
            ),
        ],
    ),
    Chain(
        id="A12_lido_ethereum",
        category="A",
        notes="Lido stETH on Ethereum",
        turns=[
            Turn("ETH staking on Ethereum", expect_card="pool_link"),
            Turn("Lido only", expect_card="pool_link"),
            Turn("0.05 ETH", expect_card="pool_link"),
            Turn(
                "Stake 0.05 ETH on Lido",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="stake",
                expect_selectors=["0xa1903eab"],
            ),
        ],
    ),
    Chain(
        id="A13_rocket_pool",
        category="A",
        notes="Rocket Pool rETH",
        turns=[
            Turn("ETH LSTs", expect_card="pool_link"),
            Turn("Rocket Pool only", expect_card="pool_link"),
            Turn("0.05 ETH", expect_card="pool_link"),
            Turn(
                "Stake 0.05 ETH on Rocket Pool",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="stake",
                expect_selectors=["0xa3e0464d"],
            ),
        ],
    ),
    Chain(
        id="A14_etherfi_eeth",
        category="A",
        notes="ether.fi eETH",
        turns=[
            Turn("ETH liquid staking", expect_card="pool_link"),
            Turn("ether.fi", expect_card="pool_link"),
            Turn("0.05 ETH", expect_card="pool_link"),
            Turn(
                "Stake 0.05 ETH on ether.fi",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="stake",
                expect_selectors=["0xd5c08a72"],
            ),
        ],
    ),
    Chain(
        id="A15_swell_rsweth",
        category="A",
        notes="Swell rswETH LRT",
        turns=[
            Turn("LRT options", expect_card="pool_link"),
            Turn("Swell only", expect_card="pool_link"),
            Turn("0.05 ETH", expect_card="pool_link"),
            Turn(
                "Stake 0.05 ETH on Swell",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="stake",
                expect_selectors=["0xf340fa01"],
            ),
        ],
    ),
    Chain(
        id="A16_frax_frxeth",
        category="A",
        notes="Frax frxETH",
        turns=[
            Turn("Frax ETH staking", expect_card="pool_link"),
            Turn("frxETH only", expect_card="pool_link"),
            Turn("0.05 ETH", expect_card="pool_link"),
            Turn(
                "Stake 0.05 ETH on Frax",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="stake",
                expect_selectors=["0x4dcd4547"],
            ),
        ],
    ),
    Chain(
        id="A17_mantle_meth",
        category="A",
        notes="Mantle mETH",
        turns=[
            Turn("Mantle ETH staking", expect_card="pool_link"),
            Turn("mETH only", expect_card="pool_link"),
            Turn("0.05 ETH", expect_card="pool_link"),
            Turn(
                "Stake 0.05 ETH on Mantle",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="stake",
                expect_selectors=["0xf6326fb3"],
            ),
        ],
    ),
    Chain(
        id="A18_kelp_rseth",
        category="A",
        notes="Kelp rsETH LRT",
        turns=[
            Turn("LRT options", expect_card="pool_link"),
            Turn("Kelp only", expect_card="pool_link"),
            Turn("0.05 ETH", expect_card="pool_link"),
            Turn(
                "Stake 0.05 ETH on Kelp",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="stake",
            ),
        ],
    ),
    Chain(
        id="A19_marinade_sol",
        category="A",
        notes="Marinade SOL native",
        turns=[
            Turn("SOL staking", expect_card="pool_link"),
            Turn("Marinade only", expect_card="pool_link"),
            Turn("1 SOL", expect_card="pool_link"),
            Turn(
                "Stake 1 SOL on Marinade",
                expect_card="execution_plan_v3",
                expect_status="ready",
                expect_action="stake",
            ),
        ],
    ),
    Chain(
        id="A20_jito_sol",
        category="A",
        notes="Jito SOL pool",
        turns=[
            Turn("Jito SOL staking", expect_card="pool_link"),
            Turn("Just Jito", expect_card="pool_link"),
            Turn("1 SOL", expect_card="pool_link"),
            Turn(
                "Stake 1 SOL on Jito",
                expect_card="execution_plan_v3",
                expect_action="stake",
            ),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Category B — Strategy compose (15 chains × 4-5 turns)
# ---------------------------------------------------------------------------
CATEGORY_B: list[Chain] = [
    Chain(
        id="B01_stable_strategy",
        category="B",
        notes="Stable yield $1000 strategy → drill #2 → swap for #3 → execute #1",
        turns=[
            Turn("Build me a stable yield strategy with $1000", expect_card="strategy_compose"),
            Turn("Tell me more about option 2", expect_card="pool_link"),
            Turn("Swap option 2 for an Optimism choice", expect_card="strategy_compose"),
            Turn(
                "Execute the top allocation",
                expect_card="execution_plan_v3",
                expect_status="ready",
            ),
        ],
    ),
    Chain(
        id="B02_bear_strategy",
        category="B",
        notes="Bear-market defensive strategy",
        turns=[
            Turn("Build a defensive bear-market strategy for $2000", expect_card="strategy_compose"),
            Turn("All stables only", expect_card="strategy_compose"),
            Turn("Drop Yearn and add Spark", expect_card="strategy_compose"),
            Turn("Execute the largest allocation"),
        ],
    ),
    Chain(
        id="B03_bull_eth_strategy",
        category="B",
        notes="Bullish ETH exposure with LSTs and LP",
        turns=[
            Turn("Build me a bull-ETH strategy with 0.5 ETH", expect_card="strategy_compose"),
            Turn("Tilt more to Renzo (LRT)", expect_card="strategy_compose"),
            Turn("What's the unlock for each?", expect_card="text"),
            Turn("Execute the Renzo leg"),
        ],
    ),
    Chain(
        id="B04_balanced_arb",
        category="B",
        notes="Balanced strategy on Arbitrum",
        turns=[
            Turn("Balanced yield strategy on Arbitrum with $1500", expect_card="strategy_compose"),
            Turn("Risk floor: medium", expect_card="strategy_compose"),
            Turn("Drop GMX, prefer Aave", expect_card="strategy_compose"),
            Turn("Execute the Aave leg"),
        ],
    ),
    Chain(
        id="B05_low_risk_only",
        category="B",
        notes="Low risk floor",
        turns=[
            Turn("Low-risk yield strategy with $500 stables", expect_card="strategy_compose"),
            Turn("Cap any single allocation at 30%", expect_card="strategy_compose"),
            Turn("Show me the allocations", expect_card="strategy_compose"),
            Turn("Execute the largest"),
        ],
    ),
    Chain(
        id="B06_eth_solana_split",
        category="B",
        notes="Cross-chain Eth + Solana strategy",
        turns=[
            Turn("Build me a split strategy: half Ethereum LST, half Solana LST. $1000", expect_card="strategy_compose"),
            Turn("Lido + Marinade", expect_card="strategy_compose"),
            Turn("0.2 ETH and 5 SOL", expect_card="strategy_compose"),
            Turn("Execute the Lido leg", expect_selectors=["0xa1903eab"]),
        ],
    ),
    Chain(
        id="B07_top3_apr",
        category="B",
        notes="Top 3 APR pools (≥1m TVL)",
        turns=[
            Turn("Top 3 APR strategy filtered to TVL >= $1m", expect_card="strategy_compose"),
            Turn("Only Aave V3 / Compound V3 / Yearn V3", expect_card="strategy_compose"),
            Turn("Make it $300 total", expect_card="strategy_compose"),
            Turn("Execute pool 2"),
        ],
    ),
    Chain(
        id="B08_curve_balancer",
        category="B",
        notes="Curve + Balancer stable strategy",
        turns=[
            Turn("Build me Curve + Balancer stable strategy $1000", expect_card="strategy_compose"),
            Turn("Single-sided only", expect_card="strategy_compose"),
            Turn("Drop Curve 3pool", expect_card="strategy_compose"),
            Turn("Execute Balancer leg"),
        ],
    ),
    Chain(
        id="B09_morpho_blueprint",
        category="B",
        notes="Morpho Blue blueprints",
        turns=[
            Turn("Morpho Blue blueprint USDC $500", expect_card="strategy_compose"),
            Turn("Show me the top 3 markets", expect_card="strategy_compose"),
            Turn("Pick the largest TVL one", expect_card="strategy_compose"),
            Turn("Execute it"),
        ],
    ),
    Chain(
        id="B10_pendle_pt",
        category="B",
        notes="Pendle PT strategy",
        turns=[
            Turn("Build a Pendle PT-USDC strategy $1000", expect_card="strategy_compose"),
            Turn("Show maturities", expect_card="text"),
            Turn("Pick the longest dated", expect_card="strategy_compose"),
            Turn("Execute the buy"),
        ],
    ),
    Chain(
        id="B11_velo_aero_dual",
        category="B",
        notes="Velodrome + Aerodrome strategy",
        turns=[
            Turn("Build a Velodrome + Aerodrome strategy $1000", expect_card="strategy_compose"),
            Turn("Concentrated liquidity only", expect_card="strategy_compose"),
            Turn("Stable pairs", expect_card="strategy_compose"),
            Turn("Execute the top allocation"),
        ],
    ),
    Chain(
        id="B12_lrt_only",
        category="B",
        notes="LRT-only strategy",
        turns=[
            Turn("Build me an LRT-only strategy with 0.5 ETH", expect_card="strategy_compose"),
            Turn("Renzo + Kelp + Swell", expect_card="strategy_compose"),
            Turn("Equal split", expect_card="strategy_compose"),
            Turn("Execute the Renzo leg", expect_selectors=["0xfdaf83a3"]),
        ],
    ),
    Chain(
        id="B13_jlp_inf_split",
        category="B",
        notes="JLP + INF Solana strategy",
        turns=[
            Turn("Build me a Solana JLP + Sanctum INF strategy with 10 USDC", expect_card="strategy_compose"),
            Turn("Equal split", expect_card="strategy_compose"),
            Turn("Show me the lockup terms", expect_card="text"),
            Turn("Execute the INF leg"),
        ],
    ),
    Chain(
        id="B14_kamino_jito",
        category="B",
        notes="Kamino + Jito Solana",
        turns=[
            Turn("Build me a Kamino + Jito Solana strategy with 5 SOL", expect_card="strategy_compose"),
            Turn("2 SOL Kamino lend + 3 SOL Jito stake", expect_card="strategy_compose"),
            Turn("What's the cost of unwinding?", expect_card="text"),
            Turn("Execute the Jito leg"),
        ],
    ),
    Chain(
        id="B15_pendle_yt_speculate",
        category="B",
        notes="Pendle YT speculation strategy",
        turns=[
            Turn("Build me a Pendle YT speculation strategy $500", expect_card="strategy_compose"),
            Turn("Show me the YT-USDe options", expect_card="strategy_compose"),
            Turn("Pick the longest maturity", expect_card="strategy_compose"),
            Turn("Execute the buy"),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Category C — Pool refinement (15 chains × 4-5 turns)
# ---------------------------------------------------------------------------
CATEGORY_C: list[Chain] = [
    Chain(
        id="C01_aave_base_refine_chain",
        category="C",
        notes="Aave Base → $250 → Optimism → use USDT → execute (exposure_disclosure)",
        turns=[
            Turn("Deposit 100 USDC in Aave V3 Base", expect_card="execution_plan_v3"),
            Turn("Make it $250 instead", expect_card="execution_plan_v3"),
            Turn("Actually on Optimism", expect_card="execution_plan_v3"),
            Turn(
                "Use my USDT instead of USDC",
                expect_card="execution_plan_v3",
                expect_fields={"exposure_disclosure": True},
            ),
            Turn("Execute now", expect_status="ready"),
        ],
    ),
    Chain(
        id="C02_aave_eth_native_refine",
        category="C",
        notes="Aave V3 ETH native refine",
        turns=[
            Turn("Supply 0.05 ETH to Aave V3", expect_card="execution_plan_v3"),
            Turn("Make it 0.1 ETH", expect_card="execution_plan_v3"),
            Turn("On Arbitrum instead", expect_card="execution_plan_v3"),
            Turn(
                "Execute",
                expect_status="ready",
                expect_selectors=["0x474cf53d"],
            ),
        ],
    ),
    Chain(
        id="C03_uniswap_v3_native",
        category="C",
        notes="Uniswap V3 native ETH-USDC refine",
        turns=[
            Turn("Deposit 0.05 ETH and 100 USDC into Uniswap V3 ETH-USDC 0.05%", expect_card="execution_plan_v3"),
            Turn("Change to 0.3% fee tier", expect_card="execution_plan_v3"),
            Turn("Make it wider range — full", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="C04_slipstream_base",
        category="C",
        notes="Aerodrome Slipstream WETH-USDC Base",
        turns=[
            Turn("Deposit 0.05 WETH and 100 USDC into Aerodrome Slipstream", expect_card="execution_plan_v3"),
            Turn("Switch to narrow range", expect_card="execution_plan_v3"),
            Turn("Use my native ETH", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="C05_velodrome_cl",
        category="C",
        notes="Velodrome CL Optimism",
        turns=[
            Turn("Velodrome CL WETH-USDC on Optimism", expect_card="pool_link"),
            Turn("Deposit 0.05 ETH + 100 USDC", expect_card="execution_plan_v3"),
            Turn("Wider range", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="C06_curve_3pool",
        category="C",
        notes="Curve 3pool USDC single-sided",
        turns=[
            Turn("Curve 3pool USDC deposit", expect_card="execution_plan_v3"),
            Turn("Use 100 USDC", expect_card="execution_plan_v3"),
            Turn("Single-sided only", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="C07_balancer_wsteth_weth",
        category="C",
        notes="Balancer wstETH-WETH",
        turns=[
            Turn("Balancer wstETH-WETH deposit", expect_card="execution_plan_v3"),
            Turn("Use 0.05 ETH", expect_card="execution_plan_v3"),
            Turn("Add tolerance 0.5%", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="C08_morpho_blue_market",
        category="C",
        notes="Morpho Blue market",
        turns=[
            Turn("Morpho Blue USDC market top TVL", expect_card="pool_link"),
            Turn("Use 250 USDC", expect_card="execution_plan_v3"),
            Turn("On Base instead", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="C09_yearn_v3_usdc",
        category="C",
        notes="Yearn V3 USDC vault",
        turns=[
            Turn("Yearn V3 USDC vault", expect_card="pool_link"),
            Turn("Ethereum", expect_card="pool_link"),
            Turn("Use 250 USDC", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="C10_aave_alt_token",
        category="C",
        notes="Aave V3 source-token reassignment",
        turns=[
            Turn("Aave V3 USDT supply 100 on Polygon", expect_card="execution_plan_v3"),
            Turn("Actually use my DAI", expect_card="execution_plan_v3"),
            Turn("Make it 100 DAI", expect_card="execution_plan_v3"),
            Turn(
                "Execute",
                expect_status="ready",
                expect_fields={"exposure_disclosure": True},
            ),
        ],
    ),
    Chain(
        id="C11_compound_base_refine",
        category="C",
        notes="Compound V3 Base USDC refine",
        turns=[
            Turn("Compound V3 Base USDC supply 50", expect_card="execution_plan_v3"),
            Turn("Make it 200 USDC", expect_card="execution_plan_v3"),
            Turn("On Arbitrum instead", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="C12_pancake_v3",
        category="C",
        notes="PancakeSwap V3 BNB-USDT",
        turns=[
            Turn("PancakeSwap V3 BNB-USDT 0.05% deposit 0.1 BNB and 30 USDT", expect_card="execution_plan_v3"),
            Turn("Narrow range", expect_card="execution_plan_v3"),
            Turn("Use my native BNB", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="C13_lido_amount_refine",
        category="C",
        notes="Lido amount refine",
        turns=[
            Turn("Stake 0.05 ETH on Lido", expect_card="execution_plan_v3"),
            Turn("Make it 0.2 ETH", expect_card="execution_plan_v3"),
            Turn("Use my native ETH", expect_card="execution_plan_v3"),
            Turn(
                "Execute",
                expect_status="ready",
                expect_selectors=["0xa1903eab"],
            ),
        ],
    ),
    Chain(
        id="C14_meteora_dlmm",
        category="C",
        notes="Meteora DLMM SOL-USDC",
        turns=[
            Turn("Meteora DLMM SOL-USDC deposit", expect_card="execution_plan_v3"),
            Turn("Use 1 SOL and 100 USDC", expect_card="execution_plan_v3"),
            Turn("Balanced range", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
    Chain(
        id="C15_raydium_clmm",
        category="C",
        notes="Raydium CLMM SOL-USDC",
        turns=[
            Turn("Raydium CLMM SOL-USDC deposit 1 SOL + 100 USDC", expect_card="execution_plan_v3"),
            Turn("Narrow range", expect_card="execution_plan_v3"),
            Turn("Make it 2 SOL", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Category D — Lifecycle close-out (15 chains × 4 turns)
# ---------------------------------------------------------------------------
CATEGORY_D: list[Chain] = [
    Chain(
        id="D01_v3_nft_close",
        category="D",
        notes="Uniswap V3 close position by tokenId",
        turns=[
            Turn("Open a Uniswap V3 ETH-USDC native position with 0.05 ETH and 100 USDC", expect_card="execution_plan_v3"),
            Turn("What positions do I have?", expect_card="text"),
            Turn("Close my Uniswap V3 position tokenId 12345", expect_card="execution_plan_v3", expect_action="close_position"),
            Turn("Show me the receipt", expect_card="text"),
        ],
    ),
    Chain(
        id="D02_aave_supply_withdraw_all",
        category="D",
        notes="Aave V3 supply → withdraw all",
        turns=[
            Turn("Supply 100 USDC to Aave V3 Base", expect_card="execution_plan_v3"),
            Turn("What's my position?", expect_card="text"),
            Turn(
                "Withdraw all USDC from Aave V3 Base",
                expect_card="execution_plan_v3",
                expect_action="withdraw",
                expect_selectors=["0x69328dec"],
            ),
            Turn("Confirm withdrawal", expect_status="ready"),
        ],
    ),
    Chain(
        id="D03_compound_claim_then_withdraw",
        category="D",
        notes="Compound V3 supply → claim COMP → withdraw",
        turns=[
            Turn("Supply 100 USDC to Compound V3 Ethereum", expect_card="execution_plan_v3"),
            Turn(
                "Claim COMP rewards",
                expect_card="execution_plan_v3",
                expect_action="claim",
                expect_selectors=["0xb7034f7e"],
            ),
            Turn(
                "Withdraw 50 USDC from Compound V3",
                expect_card="execution_plan_v3",
                expect_action="withdraw",
                expect_selectors=["0xf3fef3a3"],
            ),
            Turn("Confirm", expect_status="ready"),
        ],
    ),
    Chain(
        id="D04_v2_remove_pcs_bnb_usdt",
        category="D",
        notes="PCS V2 BNB-USDT remove liquidity",
        turns=[
            Turn("Deposit 1 BNB and 300 USDT into PCS V2 BNB-USDT", expect_card="execution_plan_v3"),
            Turn("Withdraw 10 LP from PancakeSwap V2 BNB-USDT", expect_card="execution_plan_v3"),
            Turn(
                "Confirm withdraw",
                expect_status="ready",
                expect_selectors=["0xbaa2abde"],
            ),
            Turn("Show me the receipt", expect_card="text"),
        ],
    ),
    Chain(
        id="D05_balancer_exit_pool",
        category="D",
        notes="Balancer wstETH-WETH exit pool",
        turns=[
            Turn("Deposit 0.05 ETH into Balancer wstETH-WETH", expect_card="execution_plan_v3"),
            Turn(
                "Exit Balancer wsteth-weth with 0.5 BPT",
                expect_card="execution_plan_v3",
                expect_action="exit_pool",
                expect_selectors=["0x8bdb3913"],
            ),
            Turn("Use WETH as exit token", expect_card="execution_plan_v3"),
            Turn("Confirm", expect_status="ready"),
        ],
    ),
    Chain(
        id="D06_curve_withdraw_3pool",
        category="D",
        notes="Curve 3pool withdraw single-sided",
        turns=[
            Turn("Curve 3pool USDC deposit 100", expect_card="execution_plan_v3"),
            Turn("Withdraw 100 USDC from Curve 3pool", expect_card="execution_plan_v3", expect_action="withdraw"),
            Turn("Use single-sided exit", expect_card="execution_plan_v3"),
            Turn("Confirm", expect_status="ready"),
        ],
    ),
    Chain(
        id="D07_yearn_redeem",
        category="D",
        notes="Yearn V3 USDC redeem",
        turns=[
            Turn("Yearn V3 USDC vault deposit 100", expect_card="execution_plan_v3"),
            Turn(
                "Redeem all from Yearn USDC vault",
                expect_card="execution_plan_v3",
                expect_action="redeem",
            ),
            Turn("Confirm", expect_status="ready"),
            Turn("Show me the receipt", expect_card="text"),
        ],
    ),
    Chain(
        id="D08_aave_borrow_repay",
        category="D",
        notes="Aave V3 borrow → repay loop",
        turns=[
            Turn("Supply 200 USDC as collateral on Aave V3 Base", expect_card="execution_plan_v3"),
            Turn(
                "Borrow 50 USDT from Aave V3 Base",
                expect_card="execution_plan_v3",
                expect_action="borrow",
                expect_selectors=["0xa415bcad"],
            ),
            Turn(
                "Repay 50 USDT to Aave V3 Base",
                expect_card="execution_plan_v3",
                expect_action="repay",
                expect_selectors=["0x573ade81"],
            ),
            Turn("Withdraw collateral 200 USDC", expect_card="execution_plan_v3"),
        ],
    ),
    Chain(
        id="D09_aave_native_full_cycle",
        category="D",
        notes="Aave V3 native ETH supply → withdraw → repay",
        turns=[
            Turn(
                "Supply 0.1 ETH to Aave V3 native",
                expect_card="execution_plan_v3",
                expect_selectors=["0x474cf53d"],
            ),
            Turn(
                "Withdraw all ETH from Aave V3",
                expect_card="execution_plan_v3",
                expect_selectors=["0x80500d20"],
            ),
            Turn(
                "Borrow 0.05 ETH from Aave V3 native",
                expect_card="execution_plan_v3",
                expect_selectors=["0x66514c97"],
            ),
            Turn(
                "Repay 0.05 ETH to Aave V3 native",
                expect_card="execution_plan_v3",
                expect_selectors=["0x02c5fcf8"],
            ),
        ],
    ),
    Chain(
        id="D10_marinade_liquid_unstake",
        category="D",
        notes="Marinade stake → liquid unstake",
        turns=[
            Turn("Marinade stake 1 SOL", expect_card="execution_plan_v3"),
            Turn("What's the receipt token?", expect_card="text"),
            Turn("Liquid unstake 0.5 mSOL", expect_card="execution_plan_v3", expect_action="unstake"),
            Turn("Confirm"),
        ],
    ),
    Chain(
        id="D11_jito_unstake",
        category="D",
        notes="Jito stake → secondary unstake",
        turns=[
            Turn("Jito stake 1 SOL", expect_card="execution_plan_v3"),
            Turn("Show me jitoSOL options to unwind", expect_card="text"),
            Turn("Unstake 0.5 jitoSOL via secondary market on Jupiter", expect_card="execution_plan_v3"),
            Turn("Confirm"),
        ],
    ),
    Chain(
        id="D12_orca_close_whirlpool",
        category="D",
        notes="Orca Whirlpool open → close",
        turns=[
            Turn("Orca Whirlpool USDC-SOL deposit 1 SOL + 100 USDC", expect_card="execution_plan_v3"),
            Turn("What positions on Orca do I have?", expect_card="text"),
            Turn("Withdraw from Orca USDC-SOL", expect_card="execution_plan_v3", expect_action="close_position"),
            Turn("Confirm"),
        ],
    ),
    Chain(
        id="D13_raydium_clmm_close",
        category="D",
        notes="Raydium CLMM close",
        turns=[
            Turn("Raydium CLMM SOL-USDC deposit 1 SOL + 100 USDC", expect_card="execution_plan_v3"),
            Turn("List my Raydium CLMM positions", expect_card="text"),
            Turn("Close my Raydium CLMM position 0", expect_card="execution_plan_v3", expect_action="close_position"),
            Turn("Confirm"),
        ],
    ),
    Chain(
        id="D14_meteora_dlmm_remove",
        category="D",
        notes="Meteora DLMM remove",
        turns=[
            Turn("Meteora DLMM SOL-USDC deposit 1 SOL + 100 USDC", expect_card="execution_plan_v3"),
            Turn("List my Meteora DLMM positions", expect_card="text"),
            Turn("Remove liquidity from Meteora DLMM SOL-USDC", expect_card="execution_plan_v3", expect_action="remove_liquidity"),
            Turn("Confirm"),
        ],
    ),
    Chain(
        id="D15_kamino_lend_withdraw",
        category="D",
        notes="Kamino Lend withdraw",
        turns=[
            Turn("Kamino Lend USDC deposit 100", expect_card="execution_plan_v3"),
            Turn("What's my Kamino position?", expect_card="text"),
            Turn("Withdraw 50 USDC from Kamino Lend", expect_card="execution_plan_v3", expect_action="withdraw"),
            Turn("Confirm"),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Category E — Cross-chain composed plan (15 chains × 4 turns)
# ---------------------------------------------------------------------------
CATEGORY_E: list[Chain] = [
    Chain(
        id="E01_eth_to_base_aave",
        category="E",
        notes="Bridge ETH→Base USDC + Aave V3 supply (deBridge)",
        turns=[
            Turn(
                "Bridge 100 USDC from Ethereum to Base then supply to Aave V3",
                expect_card="execution_plan_v3",
                expect_blockers=["PENDING_DST_FILL"],
            ),
            Turn("How long will the bridge take?", expect_card="text"),
            Turn("What's the slippage band?", expect_card="text"),
            Turn("Execute the bridge step now", expect_status="ready"),
        ],
    ),
    Chain(
        id="E02_eth_to_arb_compound",
        category="E",
        notes="Bridge ETH→Arb USDC + Compound V3",
        turns=[
            Turn(
                "Bridge 200 USDC from Ethereum to Arbitrum then supply to Compound V3",
                expect_card="execution_plan_v3",
                expect_blockers=["PENDING_DST_FILL"],
            ),
            Turn("Use deBridge", expect_card="execution_plan_v3"),
            Turn("Confirm slippage band", expect_card="text"),
            Turn("Execute bridge", expect_status="ready"),
        ],
    ),
    Chain(
        id="E03_eth_to_polygon_aave",
        category="E",
        notes="Bridge ETH→Polygon DAI + Aave",
        turns=[
            Turn("Bridge 100 DAI from Ethereum to Polygon then supply to Aave V3", expect_blockers=["PENDING_DST_FILL"]),
            Turn("Show me the steps", expect_card="execution_plan_v3"),
            Turn("Use LI.FI instead", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
    Chain(
        id="E04_eth_to_opt_aave_usdt",
        category="E",
        notes="Bridge ETH→Optimism USDT + Aave",
        turns=[
            Turn("Bridge 100 USDT from Ethereum to Optimism then supply to Aave V3", expect_blockers=["PENDING_DST_FILL"]),
            Turn("Show me the bridge name", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
    Chain(
        id="E05_arb_to_base_compound",
        category="E",
        notes="Bridge Arb→Base USDC + Compound",
        turns=[
            Turn("Bridge 200 USDC from Arbitrum to Base then supply to Compound V3", expect_blockers=["PENDING_DST_FILL"]),
            Turn("Show me the bridge fee", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
    Chain(
        id="E06_base_to_arb_yearn",
        category="E",
        notes="Bridge Base→Arb USDC + Yearn",
        turns=[
            Turn("Bridge 150 USDC from Base to Arbitrum then deposit to Yearn V3 USDC vault", expect_blockers=["PENDING_DST_FILL"]),
            Turn("Show me the vault APY", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
    Chain(
        id="E07_eth_to_base_curve",
        category="E",
        notes="Bridge ETH→Base + Curve 3pool",
        turns=[
            Turn("Bridge 100 USDC from Ethereum to Base then deposit to Curve 3pool single-sided", expect_blockers=["PENDING_DST_FILL"]),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Use Socket as fallback", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
    Chain(
        id="E08_eth_to_base_balancer",
        category="E",
        notes="Bridge ETH→Base + Balancer",
        turns=[
            Turn("Bridge 0.05 WETH from Ethereum to Base then deposit to Balancer", expect_blockers=["PENDING_DST_FILL"]),
            Turn("Use wstETH-WETH pool", expect_card="execution_plan_v3"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
    Chain(
        id="E09_eth_to_arb_morpho",
        category="E",
        notes="Bridge ETH→Arb + Morpho",
        turns=[
            Turn("Bridge 250 USDC from Ethereum to Arbitrum then supply to Morpho Blue", expect_blockers=["PENDING_DST_FILL"]),
            Turn("Show me the top market", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
    Chain(
        id="E10_eth_to_base_eth_native",
        category="E",
        notes="Native ETH bridge ETH→Base + Aave native",
        turns=[
            Turn("Bridge 0.1 ETH from Ethereum to Base then supply to Aave V3 native", expect_blockers=["PENDING_DST_FILL"]),
            Turn("Confirm bridge", expect_card="execution_plan_v3"),
            Turn("Show me the WTG3 address on Base", expect_card="text"),
            Turn("Execute"),
        ],
    ),
    Chain(
        id="E11_eth_to_arb_yearn_weth",
        category="E",
        notes="Bridge ETH→Arb WETH + Yearn",
        turns=[
            Turn("Bridge 0.1 WETH from Ethereum to Arbitrum then deposit to Yearn WETH vault", expect_blockers=["PENDING_DST_FILL"]),
            Turn("Show me the vault APY", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
    Chain(
        id="E12_eth_to_polygon_aave_usdt",
        category="E",
        notes="Bridge ETH→Polygon USDT + Aave",
        turns=[
            Turn("Bridge 200 USDT from Ethereum to Polygon then supply to Aave V3", expect_blockers=["PENDING_DST_FILL"]),
            Turn("Show me Polygon Aave V3 APY", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
    Chain(
        id="E13_eth_to_polygon_aave_dai",
        category="E",
        notes="Bridge ETH→Polygon DAI + Aave",
        turns=[
            Turn("Bridge 100 DAI from Ethereum to Polygon then supply to Aave V3", expect_blockers=["PENDING_DST_FILL"]),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Show me the bridge route", expect_card="text"),
            Turn("Execute"),
        ],
    ),
    Chain(
        id="E14_eth_to_avax_aave",
        category="E",
        notes="Bridge ETH→Avalanche + Aave",
        turns=[
            Turn("Bridge 200 USDC from Ethereum to Avalanche then supply to Aave V3", expect_blockers=["PENDING_DST_FILL"]),
            Turn("Show me Avax Aave V3 APY", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
    Chain(
        id="E15_eth_to_arb_balancer_weth",
        category="E",
        notes="Bridge ETH→Arb WETH + Balancer",
        turns=[
            Turn("Bridge 0.1 WETH from Ethereum to Arbitrum then deposit to Balancer", expect_blockers=["PENDING_DST_FILL"]),
            Turn("Use wstETH-WETH pool", expect_card="execution_plan_v3"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Category F — Stuck-balance + recovery (10 chains × 4 turns)
# ---------------------------------------------------------------------------
CATEGORY_F: list[Chain] = [
    Chain(
        id="F01_unsupported_adapter",
        category="F",
        notes="Unsupported adapter → recovery posture with three buttons",
        turns=[
            Turn("Deposit 100 USDC in NonExistentProtocol", expect_blockers=["UNSUPPORTED_ADAPTER"]),
            Turn("Show me my options", expect_card="execution_plan_v3"),
            Turn("Retry step", expect_card="execution_plan_v3"),
            Turn("Show recovery posture buttons", expect_card="execution_plan_v3"),
        ],
    ),
    Chain(
        id="F02_wallet_chain_mismatch",
        category="F",
        notes="Wallet chain mismatch → recovery",
        turns=[
            Turn("Deposit 100 USDC into Aave V3 on Solana", expect_blockers=["WALLET_CHAIN_MISMATCH"]),
            Turn("Why is it blocked?", expect_card="text"),
            Turn("Switch wallet to MetaMask EVM", expect_card="execution_plan_v3"),
            Turn("Retry", expect_card="execution_plan_v3"),
        ],
    ),
    Chain(
        id="F03_no_balance",
        category="F",
        notes="Balance shortfall",
        turns=[
            Turn("Deposit 100000 USDC to Aave V3 Base", expect_blockers=["INSUFFICIENT_BALANCE"]),
            Turn("Why is it blocked?", expect_card="text"),
            Turn("Show me a smaller amount option", expect_card="execution_plan_v3"),
            Turn("Use 10 USDC instead", expect_status="ready"),
        ],
    ),
    Chain(
        id="F04_pendle_pending_epoch",
        category="F",
        notes="Pendle pending epoch entry blocker",
        turns=[
            Turn("Pendle mint PT-USDe with 100 USDC", expect_blockers=["PENDING_EPOCH_ENTRY", "NEEDS_FRONTEND_SDK"]),
            Turn("When does the next epoch open?", expect_card="text"),
            Turn("Switch to swap PT instead", expect_card="execution_plan_v3"),
            Turn("Use 100 USDC", expect_status="ready"),
        ],
    ),
    Chain(
        id="F05_aerodrome_slipstream_recovery",
        category="F",
        notes="Slipstream blocked then recovered",
        turns=[
            Turn("Deposit 100 USDC in Aerodrome (vault not slipstream)", expect_card="pool_link"),
            Turn("Specifically Aerodrome Slipstream", expect_card="execution_plan_v3"),
            Turn("Use 0.05 WETH and 100 USDC", expect_status="ready"),
            Turn("Confirm"),
        ],
    ),
    Chain(
        id="F06_curve_volatile_blocker",
        category="F",
        notes="Curve volatile blocker recovery",
        turns=[
            Turn("Deposit 100 USDC into Curve volatile pool", expect_blockers=["ADAPTER_BUILD_FAILED"]),
            Turn("Why is it blocked?", expect_card="text"),
            Turn("Switch to stable pool", expect_card="execution_plan_v3"),
            Turn("Confirm", expect_status="ready"),
        ],
    ),
    Chain(
        id="F07_token_2022_hook",
        category="F",
        notes="Token-2022 hook blocker",
        turns=[
            Turn("Deposit 100 GLITCH-2022 to Meteora DAMM v2", expect_blockers=["TOKEN_2022_HOOK"]),
            Turn("Why?", expect_card="text"),
            Turn("Use USDC instead", expect_card="execution_plan_v3"),
            Turn("Confirm"),
        ],
    ),
    Chain(
        id="F08_gas_top_up",
        category="F",
        notes="Gas top-up blocker",
        turns=[
            Turn("Supply 100 USDC to Aave V3 on Avalanche (with empty AVAX wallet)", expect_blockers=["GAS_TOPUP_REQUIRED"]),
            Turn("Why?", expect_card="text"),
            Turn("Top up 0.1 AVAX from bridge", expect_card="execution_plan_v3"),
            Turn("Confirm"),
        ],
    ),
    Chain(
        id="F09_null_route",
        category="F",
        notes="Null route blocker",
        turns=[
            Turn("Swap 100 of XYZ123 to USDC on Base", expect_blockers=["NULL_ROUTE"]),
            Turn("Why?", expect_card="text"),
            Turn("Switch to USDT", expect_card="execution_plan_v3"),
            Turn("Confirm"),
        ],
    ),
    Chain(
        id="F10_aggregator_circuit_breaker",
        category="F",
        notes="Aggregator circuit breaker",
        turns=[
            Turn("Swap 1000000 USDC to ETH on Base", expect_blockers=["AGGREGATOR_CIRCUIT"]),
            Turn("Why?", expect_card="text"),
            Turn("Smaller — 100 USDC", expect_card="execution_plan_v3"),
            Turn("Confirm"),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Category G — Failure-continuation (10 chains × 4 turns)
# ---------------------------------------------------------------------------
CATEGORY_G: list[Chain] = [
    Chain(
        id="G01_partial_fail",
        category="G",
        notes="Partial-failure simulation",
        turns=[
            Turn("Supply 100 USDC to Aave V3 Base + 0.05 ETH to Lido", expect_card="execution_plan_v3"),
            Turn("What if step 2 fails?", expect_card="text"),
            Turn("Retry step 2", expect_card="execution_plan_v3"),
            Turn("Show me the recovery posture", expect_card="execution_plan_v3"),
        ],
    ),
    Chain(
        id="G02_resume_after_block",
        category="G",
        notes="Resume after blocker resolution",
        turns=[
            Turn("Deposit 100 USDC in Aave V3 Optimism", expect_card="execution_plan_v3"),
            Turn("Pause", expect_card="text"),
            Turn("Resume", expect_card="execution_plan_v3"),
            Turn("Confirm", expect_status="ready"),
        ],
    ),
    Chain(
        id="G03_session_resume",
        category="G",
        notes="Session resume across turns",
        turns=[
            Turn("Aave V3 Base USDC supply 100", expect_card="execution_plan_v3"),
            Turn("Add 50 more", expect_card="execution_plan_v3"),
            Turn("Add another 50", expect_card="execution_plan_v3"),
            Turn("Execute total", expect_status="ready"),
        ],
    ),
    Chain(
        id="G04_pick_alt_pool_after_blocker",
        category="G",
        notes="Pick alt pool after blocker",
        turns=[
            Turn("Deposit 100 USDC in NonExistentVault", expect_blockers=["UNSUPPORTED_ADAPTER", "ADAPTER_BUILD_FAILED"]),
            Turn("Suggest alternatives", expect_card="pool_link"),
            Turn("Pick the top Aave V3 alt", expect_card="execution_plan_v3"),
            Turn("Confirm", expect_status="ready"),
        ],
    ),
    Chain(
        id="G05_rebuild_after_amount_change",
        category="G",
        notes="Rebuild after amount change",
        turns=[
            Turn("Aave V3 USDC Base supply 100", expect_card="execution_plan_v3"),
            Turn("Actually 200", expect_card="execution_plan_v3"),
            Turn("Actually 50", expect_card="execution_plan_v3"),
            Turn("Confirm 50", expect_status="ready"),
        ],
    ),
    Chain(
        id="G06_post_block_continuation",
        category="G",
        notes="Post-block continuation",
        turns=[
            Turn("Deposit 100 USDC into Spark sUSDS", expect_card="execution_plan_v3"),
            Turn("If blocked use Aave V3 instead", expect_card="execution_plan_v3"),
            Turn("Confirm fallback", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="G07_retry_after_rpc",
        category="G",
        notes="Retry after RPC failure simulation",
        turns=[
            Turn("Bridge 100 USDC from Ethereum to Base then supply to Aave V3", expect_card="execution_plan_v3"),
            Turn("What if the destination RPC fails?", expect_card="text"),
            Turn("Retry destination step", expect_card="execution_plan_v3"),
            Turn("Confirm", expect_status="ready"),
        ],
    ),
    Chain(
        id="G08_slippage_breach",
        category="G",
        notes="Slippage breach with rebuild",
        turns=[
            Turn("Bridge 100 USDC from Ethereum to Optimism then supply to Aave V3", expect_card="execution_plan_v3"),
            Turn("If slippage > 50 bps, what happens?", expect_card="text"),
            Turn("Rebuild step 2 with actual fill", expect_card="execution_plan_v3"),
            Turn("Confirm rebuild", expect_status="ready"),
        ],
    ),
    Chain(
        id="G09_user_initiated_cancel",
        category="G",
        notes="User cancels mid-plan",
        turns=[
            Turn("Aave V3 supply 100 USDC Base", expect_card="execution_plan_v3"),
            Turn("Cancel that", expect_card="text"),
            Turn("Build me a Compound V3 supply instead", expect_card="execution_plan_v3"),
            Turn("Confirm", expect_status="ready"),
        ],
    ),
    Chain(
        id="G10_walletswap_continuation",
        category="G",
        notes="Wallet swap continuation",
        turns=[
            Turn("Deposit 100 USDC into Aave V3 Solana", expect_blockers=["WALLET_CHAIN_MISMATCH"]),
            Turn("Switch to MetaMask EVM Base", expect_card="execution_plan_v3"),
            Turn("Use 100 USDC", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Category H — §7 S1-S15 funding scenarios (15 chains × 4 turns)
# ---------------------------------------------------------------------------
CATEGORY_H: list[Chain] = [
    Chain(
        id="H01_S1_same_chain_dual",
        category="H",
        notes="S1: Same-chain dual-token Slipstream",
        turns=[
            Turn("Slipstream WETH-USDC Base deposit dual-token 0.05 WETH + 100 USDC", expect_card="execution_plan_v3"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Show me the pool address", expect_card="text"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H02_S2_split_swap",
        category="H",
        notes="S2: Same-chain split-swap Slipstream",
        turns=[
            Turn("Slipstream WETH-USDC Base deposit using 200 USDC (split half)", expect_card="execution_plan_v3"),
            Turn("Show me the swap leg", expect_card="text"),
            Turn("Confirm split", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H03_S3_native_eth_V3",
        category="H",
        notes="S3: Same-chain native ETH V3",
        turns=[
            Turn("Uniswap V3 ETH-USDC native 0.05 ETH + 100 USDC Ethereum", expect_card="execution_plan_v3"),
            Turn("Use my native ETH", expect_card="execution_plan_v3"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H04_S4_xchain_same_token",
        category="H",
        notes="S4: Cross-chain same-token (USDC ETH → Raydium CLMM)",
        turns=[
            Turn("Bridge 100 USDC from Ethereum to Solana then deposit to Raydium CLMM", expect_card="execution_plan_v3"),
            Turn("Show me the bridge leg", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H05_S5_xchain_diff_token",
        category="H",
        notes="S5: Cross-chain different-token (USDT ETH → JLP)",
        turns=[
            Turn("Bridge 100 USDT from Ethereum to Solana then deposit to Jupiter JLP", expect_card="execution_plan_v3"),
            Turn("Show me JLP composition", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H06_S6_xchain_native",
        category="H",
        notes="S6: Cross-chain native source (ETH ARB → ETH/USDC Base)",
        turns=[
            Turn("Bridge 0.1 ETH from Arbitrum to Base then deposit to Uniswap V3 ETH-USDC", expect_card="execution_plan_v3"),
            Turn("Show me the bridge fee", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H07_S7_dust_mixing",
        category="H",
        notes="S7: Dust mixing",
        turns=[
            Turn("Use 50 USDC + 50 USDT + 50 DAI to deposit to Curve 3pool", expect_card="execution_plan_v3"),
            Turn("Show me the swap pieces", expect_card="text"),
            Turn("Confirm dust mix", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H08_S8_partial_allowance",
        category="H",
        notes="S8: Partial allowance delta",
        turns=[
            Turn("Aave V3 USDC supply 100 Base", expect_card="execution_plan_v3"),
            Turn("I already approved 50 USDC last time", expect_card="execution_plan_v3"),
            Turn("Confirm partial approve top-up", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H09_S9_gas_missing_dst",
        category="H",
        notes="S9: Gas missing on dst",
        turns=[
            Turn("Bridge 100 USDC from Ethereum to Avalanche then supply to Aave V3 (no AVAX)", expect_card="execution_plan_v3"),
            Turn("Show me gas top-up plan", expect_card="text"),
            Turn("Confirm top-up", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H10_S10_pre_deposited_LST",
        category="H",
        notes="S10: Pre-deposited LST → unwrap chain",
        turns=[
            Turn("Convert my 0.05 stETH back to ETH then stake to Renzo", expect_card="execution_plan_v3"),
            Turn("Show me the unwrap leg", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H11_S11_NFT_LP_refinance",
        category="H",
        notes="S11: NFT-locked LP refinance",
        turns=[
            Turn("Refinance my Uniswap V3 ETH-USDC NFT tokenId 12345 to higher fee tier 0.3%", expect_card="execution_plan_v3"),
            Turn("Show me the close + reopen plan", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H12_S12_claim_compound",
        category="H",
        notes="S12: Claim-and-compound",
        turns=[
            Turn("Claim COMP and supply it back to Compound V3", expect_card="execution_plan_v3"),
            Turn("Show me the claim leg", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H13_S13_aave_supply",
        category="H",
        notes="S13: Aave V3 supply (baseline)",
        turns=[
            Turn("Aave V3 USDC supply 100 Base", expect_card="execution_plan_v3"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Show me the receipt token", expect_card="text"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H14_S14_v2_to_v3_migrate",
        category="H",
        notes="S14: V2→V3 migrate",
        turns=[
            Turn("Migrate my Uniswap V2 USDC-ETH LP to V3 0.05% native range narrow", expect_card="execution_plan_v3"),
            Turn("Show me the remove + mint plan", expect_card="text"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute", expect_status="ready"),
        ],
    ),
    Chain(
        id="H15_S15_wrong_wallet",
        category="H",
        notes="S15: Wrong wallet for chain",
        turns=[
            Turn("Aave V3 supply 100 USDC Solana (no Solana wallet present)", expect_blockers=["WALLET_CHAIN_MISMATCH"]),
            Turn("Switch to my Phantom Solana wallet", expect_card="execution_plan_v3"),
            Turn("Confirm", expect_card="execution_plan_v3"),
            Turn("Execute"),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Category I — §11 D.5/D.6 session-key flow (5 chains × 4 turns)
# ---------------------------------------------------------------------------
CATEGORY_I: list[Chain] = [
    Chain(
        id="I01_session_key_aave",
        category="I",
        notes="Autonomous rebalancing Aave V3 with $500/day cap",
        turns=[
            Turn("Set up autonomous rebalancing for my Aave V3 position with $500 daily cap", expect_card="text"),
            Turn("Open the settings page", expect_card="text"),
            Turn("Confirm Nexus EIP-7702 opt-in", expect_card="text"),
            Turn("Revoke autonomous", expect_card="text"),
            Turn("Try to rebalance autonomously (should refuse)", expect_card="text"),
        ],
    ),
    Chain(
        id="I02_session_key_compound",
        category="I",
        notes="Autonomous Compound V3 rebalancing",
        turns=[
            Turn("Set up autonomous rebalancing for my Compound V3 position $100 daily", expect_card="text"),
            Turn("Sign the policy", expect_card="text"),
            Turn("Confirm the spend cap", expect_card="text"),
            Turn("Revoke", expect_card="text"),
        ],
    ),
    Chain(
        id="I03_session_key_LST",
        category="I",
        notes="Autonomous Lido + LRT compounding",
        turns=[
            Turn("Autonomous Lido + Renzo compound 0.01 ETH weekly", expect_card="text"),
            Turn("Sign policy", expect_card="text"),
            Turn("Show me the spend cap + selector allowlist", expect_card="text"),
            Turn("Revoke", expect_card="text"),
        ],
    ),
    Chain(
        id="I04_session_key_marinade",
        category="I",
        notes="Autonomous Marinade Solana session-key",
        turns=[
            Turn("Set up autonomous Marinade compound 0.1 SOL weekly", expect_card="text"),
            Turn("Sign Phantom session keypair", expect_card="text"),
            Turn("Confirm cap", expect_card="text"),
            Turn("Revoke", expect_card="text"),
        ],
    ),
    Chain(
        id="I05_session_key_kernel",
        category="I",
        notes="Kernel v3 alternative path",
        turns=[
            Turn("Set up autonomous rebalancing using ZeroDev Kernel instead of Nexus, $200 daily", expect_card="text"),
            Turn("Sign Kernel policy", expect_card="text"),
            Turn("Confirm the impl address", expect_card="text"),
            Turn("Revoke", expect_card="text"),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Final assembly
# ---------------------------------------------------------------------------
ALL_CHAINS: list[Chain] = (
    CATEGORY_A + CATEGORY_B + CATEGORY_C + CATEGORY_D
    + CATEGORY_E + CATEGORY_F + CATEGORY_G + CATEGORY_H + CATEGORY_I
)

assert len(ALL_CHAINS) >= 100, f"Need ≥100 chains, got {len(ALL_CHAINS)}"


def get_chain(chain_id: str) -> Chain:
    for ch in ALL_CHAINS:
        if ch.id == chain_id:
            return ch
    raise KeyError(chain_id)


def chains_by_category(cat: str) -> list[Chain]:
    return [c for c in ALL_CHAINS if c.category == cat]
