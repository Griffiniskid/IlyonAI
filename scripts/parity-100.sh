#!/usr/bin/env bash
# Fire 100 varied prompts at BOTH local and prod (through the web path) and diff
# the behavioural signature (tool/card/route chosen) of each. Ignores exact
# numbers/scores/prices (those vary by live data + LLM); flags routing/outcome
# divergences (the AGENT_BACKEND class).
set -uo pipefail
LOCAL="${LOCAL_WEB:-http://localhost:3000}"
PROD="${PROD_WEB:-https://ilyonai.com}"
W="7Np41oeYqPefeNQEHSv1UDhYrehxin3NStpmzpaedWZ8"
# Keep concurrency LOW: prod serves live traffic + rate-limits; a burst makes its
# slow LLM calls time out and return empty -> false "differences". 2-3 is safe.
CONCURRENCY="${CONCURRENCY:-3}"
# structural markers only (tool names, card "type", fallbacks) — not LLM prose
SIG='analyze_token_full_sentinel|sentinel_token_report|solana_swap_proposal|swapTransaction|build_solana_swap|build_swap_tx|build_bridge_tx|bridge_proposal|build_yield_execution_plan|execution_plan_v3|get_token_price|get_wallet_balance|balance_report|search_defi_opportunities|defi_opportunities|get_staking_options|find_liquidity_pool|pool_link|compose_plan|get_defi_market_overview|"type": ?"[a-z_]+"|no deterministic|agent_v2_disabled|rate_limited|preferences|no_change|transfer'

prompts=(
"analyze this token 262o7xFCzVWxxVZmjPCBMCKtunieXARcZoyGmrkvpump"
"262o7xFCzVWxxVZmjPCBMCKtunieXARcZoyGmrkvpump"
"is this token safe DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
"check this token for rug DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
"analyze BONK"
"is BONK a scam"
"scan ACpzkGJV3DDU8HXy8yjab7RL9qNmDGym2GwLkzNppump"
"sentinel score for SOL"
"is USDC safe"
"review this contract 0x6982508145454ce325ddbe47a25d4ec3d2311933"
"swap 0.2 SOL to USDC"
"swap 5 USDC to SOL"
"swap 1 SOL to BONK"
"swap 10 USDC to this token ACpzkGJV3DDU8HXy8yjab7RL9qNmDGym2GwLkzNppump"
"swap 0.5 SOL to USDT"
"convert 100 USDC to SOL"
"swap all my SOL to USDC"
"swap 2 SOL to JUP"
"buy BONK with 5 USDC"
"sell 1000 BONK for SOL"
"swap 0.1 ETH to USDC"
"swap 50 USDT to USDC"
"bridge 10 USDC from solana to ethereum"
"bridge 0.5 SOL to BNB chain"
"move 100 USDC from ethereum to solana"
"cross chain swap SOL to ETH"
"bridge USDC to polygon"
"send 5 USDC from solana to arbitrum"
"my balance"
"what do I hold"
"show my portfolio"
"what is my SOL balance"
"my wallet value"
"do I have any USDC"
"SOL price"
"price of BONK"
"how much is ETH"
"BTC price"
"what is the price of JUP"
"trending solana tokens"
"top gainers today"
"is SOL up or down"
"ETH market cap"
"USDC price"
"best SOL pool"
"highest APY for USDC"
"where can I earn yield on SOL"
"find me a stablecoin farm"
"best yield on ethereum"
"top liquidity pools on solana"
"where to stake USDC for yield"
"safest high apy pool"
"find SOL USDC pool"
"best vaults for ETH"
"stake 1 SOL"
"stake SOL with lido"
"best liquid staking for SOL"
"stake ETH"
"how to stake SOL"
"what is impermanent loss"
"explain liquidity pools"
"what is an AMM"
"how does bridging work"
"what is slippage"
"what is yield farming"
"explain staking"
"what is a liquid staking token"
"what is TVL"
"difference between CEX and DEX"
"what is Solana"
"what is Ethereum"
"what is a memecoin"
"is crypto safe"
"what is a crypto wallet"
"what is DeFi"
"gas fees"
"solana gas fees"
"ethereum gas right now"
"is solana network congested"
"check my approvals"
"scan my wallet for risks"
"revoke risky approvals"
"am I exposed to any scams"
"hi"
"help"
"what can you do"
"swap"
"buy that token"
"swap 5 usdc to SOL then stake it"
"swap 100 USDC to SOL and bridge to ethereum"
"I want to make money in defi"
"allocate 1000 USDC across the best yields"
"find the safest 20 percent apy on solana under 50k tvl"
"what should I invest in"
"rebalance my portfolio"
"swap 0.2 sol to usdc on jupiter"
"deposit 100 usdc into aave"
"add liquidity to SOL USDC pool"
"claim my rewards"
"thanks"
)

mkdir -p /tmp/p100; rm -f /tmp/p100/* 2>/dev/null
one(){ # idx env url prompt — retry once on empty (transient rate-limit/timeout)
  local s=""
  for attempt in 1 2; do
    local body="{\"message\":\"$4\",\"query\":\"$4\",\"user_address\":\"$W\",\"solana_wallet\":\"$W\",\"wallet\":\"$W\",\"chain_id\":101,\"session_id\":\"p$1$2a${attempt}$RANDOM\"}"
    s=$(curl -sN --max-time 90 -X POST "$3/api/v1/agent" -H 'Content-Type: application/json' -d "$body" 2>/dev/null \
        | grep -aoiE "$SIG" | tr 'A-Z' 'a-z' | sed -E 's/ +//g' | sort -u | tr '\n' ',')
    [ -n "$s" ] && break
    sleep 3
  done
  printf '%s' "${s:-EMPTY}" > "/tmp/p100/$1.$2"
}
echo "firing ${#prompts[@]} prompts x2 envs (concurrency=$CONCURRENCY)..."
for i in "${!prompts[@]}"; do
  one "$i" L "$LOCAL" "${prompts[$i]}" &
  one "$i" M "$PROD"  "${prompts[$i]}" &
  while [ "$(jobs -rp | wc -l)" -ge "$CONCURRENCY" ]; do wait -n 2>/dev/null || sleep 0.5; done
done
wait
echo "=== DIFFERENCES ==="
match=0; differ=0
for i in "${!prompts[@]}"; do
  l=$(cat "/tmp/p100/$i.L" 2>/dev/null); m=$(cat "/tmp/p100/$i.M" 2>/dev/null)
  if [ "$l" = "$m" ]; then match=$((match+1)); else
    differ=$((differ+1))
    printf '#%-3s [%s]\n     local: %s\n     main : %s\n' "$i" "${prompts[$i]}" "${l:-EMPTY}" "${m:-EMPTY}"
  fi
done
echo "=== SUMMARY: matched=$match  differ=$differ  total=${#prompts[@]} ==="
