"""40 hard-strategy adversarial conversations.

Each conversation is a list of (turn_label, message, expected_signals) tuples.
expected_signals is a dict of soft-assertions evaluated against the SSE stream:

  card_types_any_of: list[str] — at least one card_type in {set} must appear
  must_emit_plan_v3: bool — execution_plan_v3 card required
  must_emit_alloc:   bool — allocation card required
  must_emit_opps:    bool — defi_opportunities card required
  text_must_contain: list[str] — final.content must include all
  text_must_not_contain: list[str] — final.content must NOT include any
  forbid_scratchpad: bool — final must not leak <plan>/<final>/Step:/scratchpad
  weights_sum_100: bool — allocation positions weight_pct sum to 100±0.5
  asset_chain_match: bool — every step.transaction.chain matches step.chain
  min_pools_in_card: int — defi_opportunities.items length >= n
"""
from __future__ import annotations


GUARDS_DEFAULT = {
    "forbid_scratchpad": True,
    "text_must_not_contain": [
        "<plan>", "</plan>", "<final>", "</final>",
        "Step 1:", "Step 2:", "Step 3:",
        "{{", "[TBD]", "TODO",
        "I am an AI", "I'm an AI",
        "ChatGPT", "GPT-4", "language model",
        "as an AI",
    ],
}


def _g(*overlay_dicts):
    out = dict(GUARDS_DEFAULT)
    out["text_must_not_contain"] = list(GUARDS_DEFAULT["text_must_not_contain"])
    for d in overlay_dicts:
        for k, v in d.items():
            if k == "text_must_not_contain":
                out["text_must_not_contain"].extend(v)
            else:
                out[k] = v
    return out


# (label, [(turn_id, message, expected_signals), ...])
CONVERSATIONS = [
    ("01_strategy_balanced_500_usdc", [
        ("t1", "I have 500 USDC on Solana. Build me a balanced 3-pool strategy targeting 8-15% APY.",
         _g({"must_emit_alloc": True, "must_emit_opps": True, "weights_sum_100": True})),
        ("t2", "Execute the plan",
         _g({"must_emit_plan_v3": True, "asset_chain_match": True})),
    ]),
    ("02_pivot_chain_mid_strategy", [
        ("t1", "Show me top 6 stablecoin yields on Ethereum.",
         _g({"must_emit_opps": True, "min_pools_in_card": 4})),
        ("t2", "Actually pivot to Base instead.",
         _g({"must_emit_opps": True, "text_must_contain": ["Base"]})),
        ("t3", "Pick the top 2 and allocate $1000 split 60/40.",
         _g({"must_emit_alloc": True, "weights_sum_100": True})),
    ]),
    ("03_lst_only_solana", [
        ("t1", "I want only liquid staking tokens on Solana with TVL above $100M. Pick 4.",
         _g({"must_emit_opps": True, "min_pools_in_card": 3,
             "text_must_contain": ["TVL"]})),
        ("t2", "Allocate 10 SOL across them weighted by TVL.",
         _g({"must_emit_alloc": True, "weights_sum_100": True})),
    ]),
    ("04_high_apy_experimental", [
        ("t1", "Show me the highest APY pools regardless of risk. Top 8.",
         _g({"must_emit_opps": True, "min_pools_in_card": 5})),
        ("t2", "Filter to pools with at least $500K TVL.",
         _g({"must_emit_opps": True})),
    ]),
    ("05_bridge_then_stake", [
        ("t1", "I have 0.5 ETH on Ethereum. Bridge it to Base then stake into the highest-yield blue-chip option.",
         _g({"must_emit_plan_v3": True, "asset_chain_match": True})),
    ]),
    ("06_reject_prior_show_pendle", [
        ("t1", "What are good blue-chip yield options across L2s?",
         _g({"must_emit_opps": True, "min_pools_in_card": 4})),
        ("t2", "Forget those. Show me Pendle PT positions only.",
         _g({"must_emit_opps": True, "text_must_contain": ["Pendle"]})),
    ]),
    ("07_refine_audited_only", [
        ("t1", "Top 8 ETH-correlated yield positions.",
         _g({"must_emit_opps": True})),
        ("t2", "Only protocols audited by Trail of Bits or Sigma Prime.",
         _g({"must_emit_opps": True})),
    ]),
    ("08_single_pool_pick_after_dump", [
        ("t1", "Show me the top 6 yield options on Arbitrum.",
         _g({"must_emit_opps": True, "min_pools_in_card": 4})),
        ("t2", "Pick the second one and allocate $250.",
         _g({"must_emit_alloc": True})),
        ("t3", "Execute deposit",
         _g({"must_emit_plan_v3": True})),
    ]),
    ("09_bootstrap_alloc", [
        ("t1", "I have $5000 in USDC sitting in my wallet. What should I do with it?",
         _g({"card_types_any_of": ["defi_opportunities", "allocation"]})),
        ("t2", "Go with the lowest risk option",
         _g({"card_types_any_of": ["allocation", "defi_opportunities"]})),
    ]),
    ("10_full_lifecycle_supply", [
        ("t1", "Supply 100 USDC into Aave V3 on Polygon",
         _g({"must_emit_plan_v3": True, "asset_chain_match": True})),
    ]),
    ("11_edge_tiny_amount", [
        ("t1", "I have $1 in USDC. What can I do with it?",
         _g({})),
    ]),
    ("12_edge_huge_amount", [
        ("t1", "I have $50 million USDC. Build a 6-pool diversified yield strategy.",
         _g({"must_emit_alloc": True, "must_emit_opps": True, "weights_sum_100": True})),
    ]),
    ("13_compound_vs_claim", [
        ("t1", "Build me a yield strategy. Auto-compound rewards weekly.",
         _g({"must_emit_opps": True})),
        ("t2", "Switch to claim weekly instead of compound.",
         _g({})),
    ]),
    ("14_exit_liquidity_stress", [
        ("t1", "Find me 5 pools where I could exit $1M without slippage > 1%.",
         _g({"must_emit_opps": True, "min_pools_in_card": 3})),
    ]),
    ("15_compare_aave_vs_compound", [
        ("t1", "Compare Aave V3 USDC supply on Ethereum vs Compound V3 USDC supply on Ethereum.",
         _g({"text_must_contain": ["Aave", "Compound"]})),
    ]),
    ("16_long_tail_msol", [
        ("t1", "Best yield options for mSOL holders on Solana.",
         _g({"must_emit_opps": True, "text_must_contain": ["mSOL"]})),
    ]),
    ("17_lrt_only_eth", [
        ("t1", "Liquid restaking tokens on Ethereum only. Top 5 by TVL.",
         _g({"must_emit_opps": True})),
    ]),
    ("18_misspelled_typos", [
        ("t1", "show me top yeild farming opurtunities on solanaa",
         _g({"must_emit_opps": True})),
    ]),
    ("19_emoji_query", [
        ("t1", "🚀 What's the best 🌾 farming play on Base right now? 💰",
         _g({})),
    ]),
    ("20_multi_constraint_hard", [
        ("t1", "I want stablecoin pools, audited, TVL > $50M, APY > 6%, on Ethereum or Arbitrum, max 4 results.",
         _g({"must_emit_opps": True})),
    ]),
    ("21_chain_aware_decimals_bsc", [
        ("t1", "Supply 250 USDC on Venus on BSC",
         _g({"must_emit_plan_v3": True, "asset_chain_match": True})),
    ]),
    ("22_protocol_spelled_oddly", [
        ("t1", "What yields can I get on uniswap v3 ETH/USDC on optimism",
         _g({"must_emit_opps": True})),
    ]),
    ("23_exec_strategy_no_amount", [
        ("t1", "Build me a balanced strategy across 4 stablecoin pools.",
         _g({"must_emit_opps": True, "must_emit_alloc": True})),
        ("t2", "Execute it",
         _g({"text_must_contain": ["amount"]})),
    ]),
    ("24_followup_proceed_after_strategy", [
        ("t1", "Build me a yield strategy with $1500 USDC, balanced risk, 4 pools.",
         _g({"must_emit_opps": True, "must_emit_alloc": True, "weights_sum_100": True})),
        ("t2", "Yes, proceed",
         _g({"must_emit_plan_v3": True})),
    ]),
    ("25_low_risk_only_strict", [
        ("t1", "I am extremely conservative. Only LOW risk pools, TVL > $50M, max APY 8%, on Ethereum.",
         _g({"must_emit_opps": True})),
    ]),
    ("26_curve_3pool_alts", [
        ("t1", "Alternatives to Curve 3pool with similar APY but higher TVL.",
         _g({"must_emit_opps": True})),
    ]),
    ("27_exec_specific_pendle", [
        ("t1", "What are top Pendle PT yields right now? Pick 3.",
         _g({"must_emit_opps": True})),
        ("t2", "Allocate $2000 evenly across them.",
         _g({"must_emit_alloc": True, "weights_sum_100": True})),
        ("t3", "Execute the deposits.",
         _g({"must_emit_plan_v3": True})),
    ]),
    ("28_multi_chain_diversification", [
        ("t1", "Build a strategy diversified across Solana, Ethereum, Arbitrum, Base. $4000 USDC.",
         _g({"must_emit_alloc": True, "weights_sum_100": True,
             "text_must_contain": ["Solana"]})),
    ]),
    ("29_negation_no_lp", [
        ("t1", "Best yield on Ethereum but not LP positions.",
         _g({"must_emit_opps": True})),
    ]),
    ("30_realistic_intent_followup", [
        ("t1", "I'm worried about depegs. Find me 5 stablecoin pools that have never depegged.",
         _g({"must_emit_opps": True})),
        ("t2", "Of those, which has the best 30-day APY trend?",
         _g({})),
    ]),
    ("31_solana_meme_caution", [
        ("t1", "Highest APY Solana memecoin LP pools.",
         _g({"must_emit_opps": True})),
        ("t2", "Why are these so risky?",
         _g({})),
    ]),
    ("32_word_number_apy", [
        ("t1", "Find me pools earning around twelve percent APY on stablecoins.",
         _g({"must_emit_opps": True})),
    ]),
    ("33_quick_action_chip_strategy", [
        ("t1", "Build me a balanced yield strategy",
         _g({"card_types_any_of": ["defi_opportunities", "allocation"]})),
    ]),
    ("34_quick_action_chip_explore", [
        ("t1", "Show me top yields right now",
         _g({"must_emit_opps": True})),
    ]),
    ("35_subsequent_refine_low_tvl_floor", [
        ("t1", "Best 4 yield pools on Mantle.",
         _g({})),
        ("t2", "Now show me only those with TVL above $5M.",
         _g({})),
    ]),
    ("36_chain_alias_eth", [
        ("t1", "Top 5 yields on eth",
         _g({"must_emit_opps": True})),
    ]),
    ("37_chain_alias_matic", [
        ("t1", "Top 5 yields on matic",
         _g({"must_emit_opps": True})),
    ]),
    ("38_pivot_then_execute", [
        ("t1", "Show me top yields on Optimism.",
         _g({"must_emit_opps": True})),
        ("t2", "Actually pivot to Base.",
         _g({"must_emit_opps": True, "text_must_contain": ["Base"]})),
        ("t3", "Pick the top one and supply $300.",
         _g({"must_emit_plan_v3": True})),
    ]),
    ("39_strategy_with_target_apy_band", [
        ("t1", "Build a strategy targeting 10-15% APY across 4 stablecoin pools, $2000 total.",
         _g({"must_emit_opps": True, "must_emit_alloc": True, "weights_sum_100": True})),
    ]),
    ("40_multi_turn_full_lifecycle", [
        ("t1", "I have 250 USDC on Polygon and want exposure to ETH-correlated yield. Suggest 3 options.",
         _g({"must_emit_opps": True, "min_pools_in_card": 2})),
        ("t2", "Allocate 60/30/10 across them.",
         _g({"must_emit_alloc": True, "weights_sum_100": True})),
        ("t3", "Execute deposits",
         _g({"must_emit_plan_v3": True, "asset_chain_match": True})),
    ]),
]


def total_turns() -> int:
    return sum(len(turns) for _, turns in CONVERSATIONS)
