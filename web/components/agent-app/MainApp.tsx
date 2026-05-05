"use client";
import React, { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence, type Variants } from "framer-motion";
import { CardRenderer } from "@/components/agent/cards/CardRenderer";
import type { CardFrame, ExecutionPlanPayload, ObservationFrame, PlanCompleteFrame, StepStatusFrame, ThoughtFrame, ToolFrame } from "@/types/agent";
import { connectMetaMask, resolveMetaMaskProvider } from "./wallets/metamask";
import { connectPhantomSolana, disconnectPhantomSolana, getStoredPhantomWalletContext, resolvePhantomEvmProvider, restorePhantomWalletContext } from "./wallets/phantom";
import { copyWithFeedback } from "./utils/copyWithFeedback";

// ── Types ───────────────────────────────────────────────────────────────────
type Role = "user" | "assistant";
type Tab  = "dashboard" | "chat" | "portfolio" | "swap";

interface ReasoningStep {
  id: number;
  type: "think" | "tool" | "result" | "conclude";
  label: string;
  detail?: string;
}

interface ExecutionNotice {
  title: string;
  body: string;
  steps?: ExecutionPlanPayload["steps"];
}

interface SwapPreview {
  fromToken: string;
  fromAmount: string;
  toToken: string;
  toAmount: string;
  route: string;
  priceImpact: string;
  fee: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  rawTx?: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  approvalTx?: any;
  isTransfer?: boolean;
  transferTo?: string;
  transferChainId?: number;
  actionType?: string;
  isBridge?: boolean;
  sourceChainLabel?: string;
  destinationChainLabel?: string;
  orderId?: string;
  estimatedTime?: string;
  bridgeRequestedAmount?: string;
  sourceExecutionSummary?: string;
  warnings?: string[];
  // Solana (Jupiter) swap fields
  swapTransaction?: string;  // base64 VersionedTransaction
  isSolanaSwap?: boolean;
}

interface TokenBalance {
  symbol: string;
  balance: number;
}

interface ChainBalance {
  chain: string;
  native_symbol: string;
  native_balance: number;
  tokens: TokenBalance[];
}

interface BalanceData {
  type: "balance_report";
  wallet_addresses: string[];
  balances: ChainBalance[];
  total_usd?: number;
  message?: string;
}

interface LiquidityPoolData {
  type: "liquidity_pool_report";
  dexId: string;
  pairAddress: string;
  poolSymbol?: string;
  baseToken: string;
  quoteToken: string;
  chainId: string;
  liquidity_usd: number;
  volume_24h_usd: number;
  apr: number;
  url: string;
  explorer_url: string;
  protocol_url?: string;
  defillama_url?: string;
}

interface UniversalCard {
  title: string;
  subtitle?: string;
  details?: Record<string, string>;
  url?: string;
  button_text?: string;
  defillama_url?: string;
  defillama_button_text?: string;
  explorer_url?: string;
}

interface UniversalCardsData {
  type: "universal_cards";
  message?: string;
  cards: UniversalCard[];
}

interface CompoundActionData {
  type: "compound_action";
  message: string;
  previews: SwapPreview[];
}

interface Message {
  id: number;
  role: Role;
  text: string;
  ts: Date;
  reasoning?: ReasoningStep[];
  agentCards?: CardFrame[];
  agentThoughts?: ThoughtFrame[];
  agentTools?: ToolFrame[];
  agentObservations?: ObservationFrame[];
  agentStepStatuses?: StepStatusFrame[];
  agentPlanCompletions?: PlanCompleteFrame[];
  elapsedMs?: number;
  swapPreview?: SwapPreview | null;
  compoundData?: CompoundActionData | null;
  balanceData?: BalanceData | null;
  poolData?: LiquidityPoolData | null;
  universalCards?: UniversalCardsData | null;
}

export interface ParsedAgentSseResponse {
  response: string;
  universalCards?: UniversalCardsData | null;
  agentCards: CardFrame[];
  agentThoughts: ThoughtFrame[];
  agentTools: ToolFrame[];
  agentObservations: ObservationFrame[];
  agentStepStatuses: StepStatusFrame[];
  agentPlanCompletions: PlanCompleteFrame[];
  elapsedMs?: number;
}

interface AuthUser {
  id: number;
  email?: string;
  wallet_address?: string;
  display_name: string;
  token: string;
}

interface ChatItem {
  id: string;
  title: string;
  updated_at: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────
// Returns true only if the query actually needs on-chain/API tool calls
function needsReasoning(query: string): boolean {
  const q = query.toLowerCase();
  const defiKeywords = [
    "swap", "exchange", "trade", "→", "->",
    "price", "курс", "стоимость",
    "balance", "баланс", "кошелек", "wallet",
    "gas", "fee", "fees", "газ",
    "bnb", "eth", "btc", "usdt", "busd", "cake", "sol", "usdc",
    "token", "токен", "coin",
    "buy", "sell", "купить", "продать",
    "send", "transfer", "отправить",
    "pool", "liquidity", "yield", "apy", "defi",
    "bridge", "cross-chain", "cross chain", "stake", "staking",
    "0x", "contract", "адрес",
    "block", "transaction", "txn",
    "portfolio", "портфолио",
  ];
  return defiKeywords.some(kw => q.includes(kw));
}

// Returns [] for simple messages — no reasoning animation shown
function generateReasoningSteps(query: string): ReasoningStep[] {
  if (!needsReasoning(query)) return [];

  const q = query.toLowerCase();

  if (q.includes("bridge") || q.includes("cross-chain") || q.includes("cross chain")) {
    return [
      { id: 1, type: "think",   label: "Parsing bridge request",          detail: "Source chain, destination chain, token, amount" },
      { id: 2, type: "tool",    label: "build_bridge_tx",                detail: "Querying deBridge DLN bridge route" },
      { id: 3, type: "result",  label: "Bridge route prepared",          detail: "Approval + bridge payload ready" },
      { id: 4, type: "conclude",label: "Preparing confirmation",         detail: "Ready for wallet signing" },
    ];
  }
  if (q.includes("stake") || q.includes("staking") || q.includes("liquidity") || q.includes("pool")) {
    return [
      { id: 1, type: "think",   label: "Identifying DeFi action",        detail: "Swap vs staking vs liquidity entry" },
      { id: 2, type: "tool",    label: "find_liquidity_pool",            detail: "Resolving pool target when needed" },
      { id: 3, type: "tool",    label: "build_swap_tx",                  detail: "Building Enso transaction bundle" },
      { id: 4, type: "conclude",label: "Transaction ready",              detail: "Approval and execution payload prepared" },
    ];
  }
  if (q.includes("swap") || q.includes("exchange") || q.includes("trade") || q.includes("→") || q.includes("->")) {
    return [
      { id: 1, type: "think",   label: "Identifying swap parameters",     detail: "Extracting token pair & amount" },
      { id: 2, type: "tool",    label: "build_swap_tx",                   detail: "Querying Enso or Jupiter route" },
      { id: 3, type: "result",  label: "Route found",                     detail: "Optimal same-chain transaction bundle" },
      { id: 4, type: "tool",    label: "approval check",                  detail: "Including approval transaction when needed" },
      { id: 5, type: "conclude",label: "Simulation complete",             detail: "Transaction ready to sign" },
    ];
  }
  if (q.includes("price") || q.includes("курс") || q.includes("стоимость") || q.includes("worth") || q.includes("cost")) {
    return [
      { id: 1, type: "tool",    label: "get_token_price",                 detail: "Binance REST API — spot price" },
      { id: 2, type: "result",  label: "Price data received",             detail: "CoinGecko fallback available" },
      { id: 3, type: "conclude",label: "Formatting market data",          detail: "Adding 24h context" },
    ];
  }
  if (q.includes("balance") || q.includes("баланс") || q.includes("wallet") || q.includes("кошелек") || q.includes("portfolio")) {
    return [
      { id: 1, type: "tool",    label: "get_balance",                     detail: "Connecting to chain RPC" },
      { id: 2, type: "result",  label: "On-chain query complete",         detail: "Latest block balance resolved" },
      { id: 3, type: "conclude",label: "Formatting wallet data",          detail: "Denominating in BNB" },
    ];
  }
  if (q.includes("gas") || q.includes("fee") || q.includes("газ")) {
    return [
      { id: 1, type: "tool",    label: "get_gas_price",                   detail: "Network — latest block" },
      { id: 2, type: "result",  label: "Gas data received",               detail: "Base fee + priority fee" },
      { id: 3, type: "conclude",label: "Estimating transaction cost",     detail: "Converting gwei → USD" },
    ];
  }
  // Generic DeFi query that needs tools but doesn't match above
  return [
    { id: 1, type: "think",   label: "Parsing DeFi intent",              detail: `"${query.slice(0, 40)}${query.length > 40 ? "…" : ""}"` },
    { id: 2, type: "tool",    label: "Calling on-chain tools",           detail: "Selecting best data source" },
    { id: 3, type: "conclude",label: "Composing response",               detail: "Formatting result" },
  ];
}

function extractJson(text: string): unknown | null {
  let current: unknown = text;
  for (let i = 0; i < 4; i += 1) {
    if (current && typeof current === "object") return current;
    if (typeof current !== "string") return null;

    const raw = current.trim();
    if (!raw) return null;

    try {
      current = JSON.parse(raw);
      continue;
    } catch {
      // continue to recovery paths
    }

    const start = raw.indexOf("{");
    const end = raw.lastIndexOf("}");
    if (start !== -1 && end > start) {
      const slice = raw.slice(start, end + 1);
      try {
        current = JSON.parse(slice);
        continue;
      } catch {
        // continue to unescape
      }
      current = slice;
      continue;
    }

    const unescaped = raw.replace(/\\"/g, '"').replace(/\\n/g, "\n");
    if (unescaped !== raw) {
      current = unescaped;
      continue;
    }
    return null;
  }
  return current && typeof current === "object" ? current : null;
}

async function fetchBridgeOrderStatus(orderId: string): Promise<string> {
  const res = await fetch(`/api/v1/bridge-status/${orderId}`);
  if (!res.ok) {
    throw new Error(`Bridge status check failed (${res.status})`);
  }
  const data = await res.json() as { status?: string; detail?: string };
  if (!data.status) {
    throw new Error(data.detail || "Missing bridge status");
  }
  return data.status;
}

export function parseSwapPreview(text: string): SwapPreview | null {
  // Try JSON format (build_swap_tx / build_transfer_tx output)
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let json = extractJson(text) as Record<string, any> | string | null;
    if (typeof json === "string") {
      const nested = extractJson(json);
      if (nested && typeof nested === "object") json = nested as Record<string, any>;
    }
    if (!json || typeof json !== "object") {
      const nested = extractJson(text.replace(/\\"/g, '"'));
      if (nested && typeof nested === "object") json = nested as Record<string, any>;
    }
    if (!json || typeof json !== "object") throw new Error("not an object");
    // Legacy/alternate Solana swap payloads that still contain a base64 tx
    if (json.swapTransaction) {
      const outSym: string = json.out_symbol ?? json.to_token_symbol ?? "Token";
      const outHuman: string = json.ui_out_amount != null
        ? String(json.ui_out_amount)
        : json.dst_amount_display != null
          ? String(json.dst_amount_display)
          : String(parseInt(json.out_amount ?? "0") / 10 ** (["USDC","USDT"].includes(outSym.toUpperCase()) ? 6 : 9));
      return {
        fromToken: json.in_symbol ?? json.from_token_symbol ?? "Token",
        fromAmount: json.ui_in_amount != null
          ? String(json.ui_in_amount)
          : json.amount_in_display != null
            ? String(json.amount_in_display)
            : "—",
        toToken: outSym,
        toAmount: outHuman,
        route: json.route_summary || "Jupiter route",
        priceImpact: json.price_impact_pct != null ? `${json.price_impact_pct}%` : "≤ 0.5%",
        fee: json.platform_fee_bps ? `${Number(json.platform_fee_bps) / 100}%` : "—",
        swapTransaction: json.swapTransaction,
        isSolanaSwap: true,
      };
    }
    if (json.type === "bridge_proposal" && json.tx) {
      const estimatedTime = json.estimated_fill_time_seconds != null
        ? `~${json.estimated_fill_time_seconds}s`
        : json.fees?.estimated_fill_time_seconds != null
          ? `~${json.fees.estimated_fill_time_seconds}s`
          : "—";
      const priceImpact = json.usd_price_impact != null
        ? `${Number(json.usd_price_impact).toFixed(2)}%`
        : json.fees?.recommended_slippage != null
          ? `~${json.fees.recommended_slippage}%`
          : "—";
      return {
        fromToken: json.from_token_symbol || "Token",
        fromAmount: json.amount_in_display != null ? String(json.amount_in_display) : "—",
        toToken: json.to_token_symbol || "Token",
        toAmount: json.dst_amount_display != null ? String(json.dst_amount_display) : "—",
        route: json.route_summary || "deBridge DLN",
        priceImpact,
        fee: json.estimated_fee_display || (Number(json.affiliate_fee_percent ?? 0) ? `${Number(json.affiliate_fee_percent)}% + bridge fees` : "Bridge fees only"),
        rawTx: json.chain_type === "evm" ? (json.tx ?? null) : null,
        approvalTx: json.approval_tx ?? null,
        actionType: "bridge",
        isBridge: true,
        swapTransaction: json.chain_type === "solana" ? (json.tx?.serialized ?? "") : undefined,
        isSolanaSwap: json.chain_type === "solana",
        sourceChainLabel: json.src_chain_name || (json.src_chain_id ? `Chain ${json.src_chain_id}` : undefined),
        destinationChainLabel: json.dst_chain_name || (json.dst_chain_id ? `Chain ${json.dst_chain_id}` : undefined),
        orderId: json.order_id ? String(json.order_id) : undefined,
        estimatedTime,
        bridgeRequestedAmount: json.requested_amount_display != null ? String(json.requested_amount_display) : undefined,
        sourceExecutionSummary: json.source_execution_summary ? String(json.source_execution_summary) : undefined,
        warnings: Array.isArray(json.warnings) ? json.warnings.map(String) : undefined,
      };
    }
    if (json.status === "ok" && json.chain_type === "solana" && json.tx?.serialized && json.type !== "bridge_proposal") {
      const outSym: string = json.out_symbol ?? "Token";
      const outHuman: string = json.ui_out_amount != null
        ? String(json.ui_out_amount)
        : String(parseInt(json.out_amount ?? "0") / 10 ** (["USDC","USDT"].includes(outSym.toUpperCase()) ? 6 : 9));
      return {
        fromToken: json.in_symbol ?? "Token",
        fromAmount: json.ui_in_amount != null ? String(json.ui_in_amount) : "—",
        toToken: outSym,
        toAmount: outHuman,
        route: json.route_summary || "Jupiter route",
        priceImpact: json.price_impact_pct != null ? `${json.price_impact_pct}%` : "≤ 0.5%",
        fee: json.platform_fee_bps ? `${Number(json.platform_fee_bps) / 100}%` : "—",
        swapTransaction: json.tx.serialized,
        isSolanaSwap: true,
      };
    }
    // Transfer transaction from build_transfer_tx
    if (json.status === "ok" && json.type === "transaction") {
      return {
        fromToken: json.token_symbol || "Token",
        fromAmount: json.amount != null ? String(json.amount) : "—",
        toToken: "—",
        toAmount: "—",
        route: "Direct Transfer",
        priceImpact: "—",
        fee: "—",
        rawTx: { to: json.to, data: json.data, value: json.value, chain_id: json.chain_id },
        isTransfer: true,
        transferTo: json.ui_to ?? json.to,
        transferChainId: json.chain_id,
      };
    }
    // Solana swap from build_solana_swap (Jupiter v6)
    if (
      json.type === "solana_swap_proposal" &&
      json.swapTransaction
    ) {
      const outSym: string = json.out_symbol ?? "Token";
      // Prefer backend-computed human-readable amount; fall back to raw division
      const outHuman: string = json.ui_out_amount != null
        ? String(json.ui_out_amount)
        : String(parseInt(json.out_amount ?? "0") / 10 ** (["USDC","USDT"].includes(outSym.toUpperCase()) ? 6 : 9));
      return {
        fromToken: json.in_symbol ?? "Token",
        fromAmount: "—",
        toToken: outSym,
        toAmount: outHuman,
        route: "Jupiter v6",
        priceImpact: "≤ 0.5%",
        fee: json.platform_fee_bps ? `${Number(json.platform_fee_bps) / 100}%` : "—",
        swapTransaction: json.swapTransaction,
        isSolanaSwap: true,
      };
    }
    if (json.type === "evm_action_proposal" && json.tx) {
      const feeBps = Number(json.platform_fee_bps ?? 0);
      const impact = json.price_impact_pct != null ? `${json.price_impact_pct}%` : "—";
      return {
        fromToken: json.from_token_symbol || "Token",
        fromAmount: json.amount_in_display != null ? String(json.amount_in_display) : "—",
        toToken: json.to_token_symbol || "Token",
        toAmount: json.dst_amount_display != null ? String(json.dst_amount_display) : "—",
        route: json.route_summary || "Enso route",
        priceImpact: impact,
        fee: feeBps ? `${feeBps / 100}% platform` : "—",
        rawTx: json.tx ?? null,
        approvalTx: json.approval_tx ?? null,
        actionType: json.action ?? "swap",
        warnings: Array.isArray(json.warnings) ? json.warnings.map(String) : undefined,
      };
    }
    // Swap transaction from build_swap_tx (EVM / old Solana path with dst_amount)
    if (json.status === "ok" && json.dst_amount) {
      const chain = json.chain_type === "solana" ? "Jupiter" : "Enso";
      return {
        fromToken: "Token",
        fromAmount: "—",
        toToken: "Token",
        toAmount: (parseInt(json.dst_amount) / 1e18).toFixed(6),
        route: `${chain} Aggregator`,
        priceImpact: "< 0.1%",
        fee: json.platform_fee_bps ? `${Number(json.platform_fee_bps) / 100}%` : "—",
        rawTx: json.tx ?? null,
        approvalTx: json.approval_tx ?? null,
      };
    }
  } catch { /* not JSON */ }

  // Try text format: "X/USDT → Y wei" or simulate_swap result
  const swapMatch = text.match(/([0-9,]+(?:\.[0-9]+)?)\s*(BNB|ETH|USDT|BUSD|CAKE|SOL)\s*→\s*([0-9,]+(?:\.[0-9]+)?)\s*(BNB|ETH|USDT|BUSD|CAKE|SOL)/i);
  if (swapMatch) {
      return {
        fromToken: swapMatch[2].toUpperCase(),
        fromAmount: swapMatch[1],
        toToken: swapMatch[4].toUpperCase(),
        toAmount: swapMatch[3],
        route: "Aggregator",
        priceImpact: "< 0.01%",
        fee: "0.05%",
      };
  }
  return null;
}

function parseBalanceData(text: string): BalanceData | null {
  try {
    const json = extractJson(text);
    if (json && typeof json === "object" && (json as Record<string, unknown>).type === "balance_report")
      return json as BalanceData;
  } catch { /* not JSON */ }
  return null;
}

function parseLiquidityPool(text: string): LiquidityPoolData | null {
  try {
    const json = extractJson(text);
    if (json && typeof json === "object" && (json as Record<string, unknown>).type === "liquidity_pool_report")
      return json as LiquidityPoolData;
  } catch { /* not JSON */ }
  return null;
}

function parseUniversalCards(text: string): UniversalCardsData | null {
  try {
    const json = extractJson(text);
    if (json && typeof json === "object") {
      const j = json as Record<string, unknown>;
      if (j.type === "universal_cards" && Array.isArray(j.cards))
        return json as UniversalCardsData;
    }
  } catch { /* not JSON */ }
  return null;
}

function parseCompoundAction(text: string): CompoundActionData | null {
  try {
    const json = extractJson(text);
    if (!json || typeof json !== "object") return null;
    const payload = json as Record<string, unknown>;
    if (payload.type !== "compound_action") return null;

    const previews = [payload.swap, payload.bridge]
      .map(item => item && typeof item === "object" ? parseSwapPreview(JSON.stringify(item)) : null)
      .filter((preview): preview is SwapPreview => Boolean(preview));

    return {
      type: "compound_action",
      message: typeof payload.message === "string" ? payload.message : "I've prepared a multi-step transaction plan. Review each step below.",
      previews,
    };
  } catch { /* not JSON */ }
  return null;
}

function resolveStructuredContent(text: string) {
  let swapPreview = null;
  let compoundData = null;
  let balanceData = null;
  let poolData = null;
  let universalCards = null;
  try { swapPreview = parseSwapPreview(text); } catch (e) { console.error("parseSwapPreview failed", e); }
  try { compoundData = parseCompoundAction(text); } catch (e) { console.error("parseCompoundAction failed", e); }
  try { balanceData = parseBalanceData(text); } catch (e) { console.error("parseBalanceData failed", e); }
  try { poolData = parseLiquidityPool(text); } catch (e) { console.error("parseLiquidityPool failed", e); }
  try { universalCards = parseUniversalCards(text); } catch (e) { console.error("parseUniversalCards failed", e); }
  return { swapPreview, compoundData, balanceData, poolData, universalCards };
}

function fmtCardValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try { return JSON.stringify(value); } catch { return String(value); }
}

function cardFromPosition(position: Record<string, unknown>, index: number): UniversalCard {
  return {
    title: `${fmtCardValue(position.protocol ?? position.project ?? `Position ${index + 1}`)} · ${fmtCardValue(position.asset ?? position.token ?? "Asset")}`,
    subtitle: `${fmtCardValue(position.chain ?? position.chain_id)} · APY ${fmtCardValue(position.apy)} · Sentinel ${fmtCardValue(position.sentinel)}`,
    details: {
      Weight: fmtCardValue(position.weight ? `${position.weight}%` : undefined),
      Amount: fmtCardValue(position.usd ?? position.amount_usd ?? position.amount),
      Risk: fmtCardValue(position.risk ?? position.risk_level),
      Fit: fmtCardValue(position.fit ?? position.strategy_fit),
      Safety: fmtCardValue(position.safety),
      Durability: fmtCardValue(position.durability),
      Exit: fmtCardValue(position.exit),
      Confidence: fmtCardValue(position.confidence),
    },
  };
}

function cardsFromAgentCard(cardType: string, payload: Record<string, unknown>): UniversalCard[] {
  if (cardType === "allocation") {
    const positions = Array.isArray(payload.positions) ? payload.positions : [];
    const cards = positions
      .filter((p): p is Record<string, unknown> => !!p && typeof p === "object")
      .map(cardFromPosition);
    if (cards.length) return cards;
  }

  if (cardType === "stake" && Array.isArray(payload.staking_options)) {
    return payload.staking_options
      .filter((p): p is Record<string, unknown> => !!p && typeof p === "object")
      .slice(0, 6)
      .map((p, i) => ({
        title: `${fmtCardValue(p.protocol ?? `Staking option ${i + 1}`)} · ${fmtCardValue(p.symbol ?? p.asset ?? "Asset")}`,
        subtitle: `${fmtCardValue(p.chain)} · APY ${fmtCardValue(p.apy)}% · Risk ${fmtCardValue(p.risk_level)}`,
        details: {
          TVL: fmtCardValue(p.tvl_usd ? `$${Number(p.tvl_usd).toLocaleString()}` : undefined),
          Pool: fmtCardValue(p.pool),
        },
      }));
  }

  if (cardType === "swap_quote") {
    const sentinel = payload.sentinel as Record<string, unknown> | undefined;
    const shield = payload.shield as Record<string, unknown> | undefined;
    return [{
      title: "Swap quote",
      subtitle: `${fmtCardValue(payload.rate)} · ${fmtCardValue(payload.router)}`,
      details: {
        Pay: fmtCardValue(payload.pay),
        Receive: fmtCardValue(payload.receive),
        Sentinel: fmtCardValue(sentinel?.sentinel),
        Risk: fmtCardValue(sentinel?.risk_level),
        Shield: fmtCardValue(shield?.verdict),
      },
    }];
  }

  if (cardType === "balance") {
    const tokens = Array.isArray(payload.tokens) ? (payload.tokens as Array<Record<string, unknown>>) : [];
    const byChain = (payload.by_chain && typeof payload.by_chain === "object") ? payload.by_chain as Record<string, Record<string, unknown>> : {};
    const positions = Array.isArray(payload.positions) ? payload.positions as unknown[] : [];

    const details: Record<string, string> = {
      "Total USD": fmtCardValue(payload.total_usd),
      Tokens: String(tokens.length),
      Positions: String(positions.length),
      Chains: String(Object.keys(byChain).length),
    };

    const topTokens = tokens
      .filter((t) => Number(t?.usd ?? 0) >= 0.01)
      .slice(0, 6);
    for (const t of topTokens) {
      const sym = String(t?.symbol ?? "?");
      const chain = String(t?.chain ?? "");
      const amt = Number(t?.amount ?? 0);
      const usd = Number(t?.usd ?? 0);
      const amtStr = amt >= 1 ? amt.toLocaleString(undefined, { maximumFractionDigits: 4 }) : amt.toPrecision(4);
      const usdStr = usd >= 1 ? `$${usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : `$${usd.toFixed(4)}`;
      const label = chain ? `${sym} · ${chain}` : sym;
      details[label] = `${amtStr} ${sym} (${usdStr})`;
    }

    for (const [chain, info] of Object.entries(byChain).slice(0, 8)) {
      const usd = Number(info?.usd ?? 0);
      if (usd <= 0) continue;
      details[`Chain · ${chain}`] = `$${usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
    }

    return [{
      title: "Wallet balance",
      subtitle: fmtCardValue(payload.address),
      details,
    }];
  }

  if (cardType === "execution_plan" || cardType === "execution_plan_v2") {
    const steps = Array.isArray(payload.steps) ? payload.steps : [];
    return [{
      title: cardType === "execution_plan_v2" ? "Execution plan v2" : "Execution plan",
      subtitle: `${steps.length || fmtCardValue(payload.total_steps)} steps · Risk gate ${fmtCardValue(payload.risk_gate ?? "clear")}`,
      details: {
        "Total gas": fmtCardValue(payload.total_gas ?? payload.total_gas_usd),
        "Blended Sentinel": fmtCardValue(payload.blended_sentinel ?? payload.weighted_sentinel),
        "Requires signatures": fmtCardValue(payload.requires_signature_count ?? payload.tx_count),
        "Double confirm": fmtCardValue(payload.requires_double_confirm),
      },
    }];
  }

  if (cardType === "plan_blocked") {
    return [{
      title: "Plan blocked",
      subtitle: "Sentinel Shield blocked signing",
      details: {
        Severity: fmtCardValue(payload.severity),
        Reasons: fmtCardValue(payload.reasons),
      },
    }];
  }

  return [];
}

export function parseAgentSseResponse(rawBody: string): ParsedAgentSseResponse | null {
  if (!rawBody.includes("event:") || !rawBody.includes("data:")) return null;

  let response = "";
  let elapsedMs: number | undefined;
  const cards: UniversalCard[] = [];
  const agentCards: CardFrame[] = [];
  const agentThoughts: ThoughtFrame[] = [];
  const agentTools: ToolFrame[] = [];
  const agentObservations: ObservationFrame[] = [];
  const agentStepStatuses: StepStatusFrame[] = [];
  const agentPlanCompletions: PlanCompleteFrame[] = [];
  for (const block of rawBody.split(/\n\n+/)) {
    const event = block.match(/^event:\s*(.+)$/m)?.[1]?.trim();
    const dataLine = block.match(/^data:\s*(.+)$/m)?.[1];
    if (!event || !dataLine) continue;
    let data: Record<string, unknown>;
    try { data = JSON.parse(dataLine); } catch { continue; }

    if (event === "final") {
      response = fmtCardValue(data.content);
      if (typeof data.elapsed_ms === "number") elapsedMs = data.elapsed_ms;
    } else if (event === "error") {
      response = `Agent error: ${fmtCardValue(data.error)}`;
    } else if (event === "thought") {
      agentThoughts.push({ ...(data as Omit<ThoughtFrame, "kind">), kind: "thought" });
    } else if (event === "tool") {
      agentTools.push({ ...(data as Omit<ToolFrame, "kind">), kind: "tool" });
    } else if (event === "observation") {
      agentObservations.push({ ...(data as Omit<ObservationFrame, "kind">), kind: "observation" });
    } else if (event === "card") {
      const cardType = fmtCardValue(data.card_type);
      const payload = data.payload && typeof data.payload === "object" ? data.payload as Record<string, unknown> : {};
      agentCards.push({ ...(data as Omit<CardFrame, "kind">), kind: "card" } as CardFrame);
      cards.push(...cardsFromAgentCard(cardType, payload));
    } else if (event === "step_status") {
      agentStepStatuses.push({ ...(data as Omit<StepStatusFrame, "kind">), kind: "step_status" });
    } else if (event === "plan_complete") {
      agentPlanCompletions.push({ ...(data as Omit<PlanCompleteFrame, "kind">), kind: "plan_complete" });
    }
  }

  return {
    response: response || "The agent completed without a final answer.",
    universalCards: cards.length ? { type: "universal_cards", cards } : null,
    agentCards,
    agentThoughts,
    agentTools,
    agentObservations,
    agentStepStatuses,
    agentPlanCompletions,
    elapsedMs,
  };
}

function reasoningFromAgentFrames(thoughts: ThoughtFrame[], tools: ToolFrame[], observations: ObservationFrame[] = []): ReasoningStep[] {
  const rows: Array<{ step: number; type: ReasoningStep["type"]; label: string; detail?: string }> = [
    ...thoughts.map((frame) => ({ step: frame.step_index, type: "think" as const, label: frame.content })),
    ...tools.map((frame) => ({
      step: frame.step_index,
      type: "tool" as const,
      label: `Called ${frame.name}`,
      detail: fmtCardValue(frame.args),
    })),
    ...observations.map((frame) => ({
      step: frame.step_index + 0.1,
      type: (frame.ok ? "result" : "conclude") as ReasoningStep["type"],
      label: frame.ok ? `${frame.name || "Tool"} completed` : `${frame.name || "Tool"} failed`,
      detail: frame.error ? fmtCardValue(frame.error) : undefined,
    })),
  ].sort((a, b) => a.step - b.step);

  return rows.map((row, index) => ({
    id: index + 1,
    type: row.type,
    label: row.label,
    detail: row.detail,
  }));
}

function orderAgentCards(cards: CardFrame[]): CardFrame[] {
  const priority = new Map<string, number>([
    ["allocation", 0],
    ["sentinel_matrix", 1],
    ["execution_plan", 2],
    ["execution_plan_v2", 3],
  ]);
  return [...cards].sort((a, b) => (priority.get(a.card_type) ?? 50) - (priority.get(b.card_type) ?? 50));
}

// ── Universal Card List component ───────────────────────────────────────────
function UniversalCardList({ data }: { data: UniversalCardsData }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 10 }}>
      {data.cards.map((card, i) => {
        const poolAddress = card.details?.["Pool Address"];
        const detailEntries = Object.entries(card.details ?? {}).filter(([key]) => key !== "Pool Address");

        return (
          <div key={i} style={{
            padding: "15px",
            background: "rgba(15,23,42,0.72)",
            borderRadius: 18,
            border: "1px solid rgba(255,255,255,0.08)",
            backdropFilter: "blur(18px)",
            boxShadow: "0 18px 50px rgba(0,0,0,0.28)",
          }}>
            <div style={{ fontWeight: 700, color: "#fff", marginBottom: 2, fontSize: 14 }}>{card.title}</div>
            {card.subtitle && (
              <div style={{ color: "rgba(148,163,184,0.85)", fontSize: 12, marginBottom: 10 }}>{card.subtitle}</div>
            )}

            {poolAddress && poolAddress !== "—" && (
              <div style={{
                marginBottom: 12,
                padding: "10px 12px",
                borderRadius: 10,
                border: "1px solid rgba(16,185,129,0.25)",
                background: "linear-gradient(135deg, rgba(16,185,129,0.10), rgba(15,23,42,0.55))",
              }}>
                <div style={{
                  color: "rgba(255,255,255,0.55)",
                  fontSize: 10,
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  marginBottom: 6,
                }}>
                  Pool Address
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "space-between" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                    <strong style={{ color: "#fff", fontFamily: "monospace", fontSize: 12 }}>
                      {poolAddress.length > 20 ? `${poolAddress.slice(0, 10)}...${poolAddress.slice(-8)}` : poolAddress}
                    </strong>
                    <button
                      type="button"
                      onClick={(e) => {
                        void copyWithFeedback(poolAddress, e.currentTarget);
                      }}
                      style={{
                        background: "none", border: "none", color: "rgba(255,255,255,0.6)",
                        cursor: "pointer", fontSize: 12, padding: "2px 4px", borderRadius: 4,
                        transition: "all 0.2s"
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = "rgba(255,255,255,0.1)";
                        e.currentTarget.style.color = "#34D399";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = "none";
                        e.currentTarget.style.color = "rgba(255,255,255,0.6)";
                      }}
                      title="Copy full pool address"
                    >
                      📋
                    </button>
                  </div>
                  {card.explorer_url && (
                    <a
                      href={card.explorer_url}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        color: "#34D399",
                        fontSize: 11,
                        fontWeight: 700,
                        textDecoration: "none",
                        whiteSpace: "nowrap",
                      }}
                    >
                      Explorer
                    </a>
                  )}
                </div>
              </div>
            )}

            {detailEntries.length > 0 && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 12 }}>
                {detailEntries.map(([key, val]) => (
                  <div key={key} style={{ fontSize: 13 }}>
                    <span style={{ color: "rgba(148,163,184,0.8)" }}>{key}: </span>
                    <strong style={{ color: "#fff" }}>{val}</strong>
                  </div>
                ))}
              </div>
            )}

            {(card.url || card.defillama_url) && (
              <div style={{ display: "flex", gap: 8 }}>
                {card.url && (
                  <a
                    href={card.url} target="_blank" rel="noreferrer"
                    style={{
                      flex: 1,
                      display: "block", textAlign: "center", background: "linear-gradient(135deg,#10b981,#34d399)",
                      color: "#03150f", padding: "8px 0", borderRadius: 10,
                      textDecoration: "none", fontWeight: 700, fontSize: 13,
                      boxShadow: "0 10px 24px rgba(16,185,129,0.18)",
                    }}
                  >
                    {card.button_text || "View Pool"}
                  </a>
                )}
                {card.defillama_url && (
                  <a
                    href={card.defillama_url} target="_blank" rel="noreferrer"
                    style={{
                      flex: card.url ? 1 : undefined,
                      display: "block", textAlign: "center",
                      background: "rgba(15,23,42,0.68)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      color: "#fff", padding: "8px 12px", borderRadius: 8,
                      textDecoration: "none", fontWeight: 700, fontSize: 13,
                    }}
                  >
                    {card.defillama_button_text || "View in DefiLlama"}
                  </a>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Data ────────────────────────────────────────────────────────────────────
const TOKENS_BASE = [
  { symbol: "SOL",  name: "Solana",      icon: "◎",  grad: "linear-gradient(135deg,#8B5CF6,#22D3EE)", vol: "$2.1B", pair: "SOLUSDT"  },
  { symbol: "ETH",  name: "Ethereum",    icon: "Ξ",  grad: "linear-gradient(135deg,#9578EA,#6D28D9)", vol: "$8.4B", pair: "ETHUSDT"  },
  { symbol: "BNB",  name: "BNB Chain",   icon: "⬡", grad: "linear-gradient(135deg,#F0B90B,#E8832A)", vol: "$1.2B", pair: "BNBUSDT"  },
  { symbol: "USDT", name: "Tether",      icon: "₮",  grad: "linear-gradient(135deg,#26A17B,#1A7A5E)", vol: "$45B",  pair: null       },
];

const TICKER_PAIRS = [
  { sym: "BNB",  pair: "BNBUSDT"  },
  { sym: "ETH",  pair: "ETHUSDT"  },
  { sym: "BTC",  pair: "BTCUSDT"  },
  { sym: "CAKE", pair: "CAKEUSDT" },
  { sym: "USDT", pair: null       },
  { sym: "SOL",  pair: "SOLUSDT"  },
  { sym: "ARB",  pair: "ARBUSDT"  },
  { sym: "OP",   pair: "OPUSDT"   },
];

const CG_IDS: Record<string, string> = {
  BTC: "bitcoin",
  ETH: "ethereum",
  BNB: "binancecoin",
  SOL: "solana",
  AVAX: "avalanche-2",
  CAKE: "pancakeswap-token",
  MATIC: "matic-network",
  ARB: "arbitrum",
  OP: "optimism",
  DOT: "polkadot",
  ADA: "cardano",
};

const QUICK_PROMPTS = [
  "📊 SOL price", "💰 My balance", "🔄 Swap 0.2 SOL → USDC", "🌊 Best SOL pool", "⛽ Gas fees",
];

const CAPABILITIES = [
  { icon: "💰", title: "Check Balance",  desc: "Live wallet balances across chains",       prompt: "What is my wallet balance?" },
  { icon: "💱", title: "Find Best Swap", desc: "Compare routes across Enso & Jupiter",    prompt: "Best route to swap 1 SOL to USDC" },
  { icon: "📈", title: "Price Analysis", desc: "Real-time prices from centralized and DEX venues",    prompt: "Show me SOL price and market data" },
  { icon: "⛽", title: "Gas Estimator",  desc: "Estimate gas for any transaction",         prompt: "What are current gas fees?" },
];

const PLATFORM_FEATURES = [
  { icon: "🤖", title: "AI Trading Assistant",   desc: "Ask anything in natural language — prices, balances, swap routes, yield strategies. No coding required." },
  { icon: "🔄", title: "Smart DEX Aggregation",  desc: "Best swap routes sourced from Jupiter for Solana, Enso for EVM, and cross-chain routing through deBridge." },
  { icon: "📊", title: "Portfolio Analytics",    desc: "Real-time balance tracking, 24h PnL, yield earned across Solana, Ethereum, Base, BNB Chain and more." },
  { icon: "🔗", title: "Multi-Chain Support",    desc: "Move between Solana and leading EVM ecosystems without leaving the same AI workspace." },
  { icon: "🛡️", title: "Non-Custodial Security", desc: "Your keys, your crypto. We never store private keys, seed phrases or sensitive data." },
];

const SIDEBAR_GROUPS = [
  {
    title: "Discover",
    items: [
      { key: "dashboard", label: "Home", icon: "⌂" },
    ],
  },
  {
    title: "Portfolio",
    items: [
      { key: "portfolio", label: "Portfolio", icon: "◔" },
    ],
  },
  {
    title: "AI Agent",
    items: [
      { key: "chat", label: "Chat", icon: "⌁" },
      { key: "swap", label: "Swap", icon: "⇄" },
    ],
  },
] as const;

const OVERVIEW_CHAINS = [
  { label: "ETH", color: "#8B9CF7" },
  { label: "BASE", color: "#3B82F6" },
  { label: "ARB", color: "#38BDF8" },
  { label: "BNB", color: "#FBBF24" },
  { label: "POL", color: "#A855F7" },
  { label: "OP", color: "#F43F5E" },
  { label: "AVAX", color: "#EF4444" },
  { label: "SOL", color: "#8B5CF6" },
];

const HOW_STEPS = [
  { num: "01", icon: "🔗", title: "Connect Wallet",   desc: "Link Phantom or MetaMask. We support Solana first, plus the major EVM networks in one app." },
  { num: "02", icon: "💬", title: "Ask the AI",       desc: 'Type naturally: "Swap 0.5 SOL to USDC at best rate" or "What\'s my portfolio worth today?"' },
  { num: "03", icon: "⚡", title: "Execute Instantly", desc: "Confirm the AI-generated transaction with one click. Fast, transparent, non-custodial." },
];

interface Partner {
  name: string;
  desc: string;
  category: string;
  logo?: string;
  icon?: string;
  logoSize: number;
}

const PARTNERS: Partner[] = [
  // DEX / Aggregators
  { name: "Jupiter", category: "DEX Aggregator", desc: "Solana", logo: "https://jup.ag/static/media/jupiter-logo.2d2d1a3f.svg", logoSize: 42 },
  { name: "Enso", category: "EVM Bundler", desc: "Multi-chain", logo: "https://www.enso.build/assets/images/enso-logo.png", logoSize: 36 },
  { name: "1inch", category: "DEX Aggregator", desc: "EVM", logo: "https://app.1inch.io/assets/images/1inch-logo.svg", logoSize: 40 },
  { name: "deBridge", category: "Cross-Chain", desc: "Bridge", logo: "https://debridge.finance/images/logo.svg", logoSize: 36 },
  // Data / Analytics
  { name: "DefiLlama", category: "Analytics", desc: "DeFi Data", logo: "https://defillama.com/logo.png", logoSize: 36 },
  { name: "CoinGecko", category: "Price Data", desc: "Market Data", logo: "https://static.coingecko.com/s/coingecko-logo-8901d2d8ebf2a4bdf88379cc404d7d0e.svg", logoSize: 34 },
  { name: "Binance", category: "Price Data", desc: "Exchange", logo: "https://public.bnbstatic.com/image/pgc/202302/f5f822d3-7e2f-4d53-8c0c-fd5b5f2e0e2c.png", logoSize: 34 },
  { name: "Moralis", category: "Web3 API", desc: "Multi-chain", logo: "https://moralis.io/wp-content/uploads/2022/12/Moralis-Logo-Light.svg", logoSize: 34 },
  { name: "Helius", category: "Solana RPC", desc: "Infrastructure", logo: "https://helius.xyz/_next/image?url=%2Fassets%2Fhelius-icon.png&w=64&q=75", logoSize: 34 },
  { name: "DexScreener", category: "Analytics", desc: "DEX Tracking", logo: "https://docs.dexscreener.com/img/logo.svg", logoSize: 32 },
  // AI
  { name: "OpenRouter", category: "AI Router", desc: "LLM Gateway", logo: "https://openrouter.ai/favicon.ico", logoSize: 32 },
  { name: "Gemini", category: "AI Model", desc: "Google", logo: "https://www.gstatic.com/lamda/images/gemini_sparkle_v002_d4735304ff6292a690345.svg", logoSize: 32 },
  { name: "Grok", category: "AI Model", desc: "xAI", logo: "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8e/Grok_logo.png/640px-Grok_logo.png", logoSize: 32 },
  // Wallets
  { name: "Phantom", category: "Wallet", desc: "Solana", logo: "https://phantom.app/img/phantom-logo.svg", logoSize: 34 },
  { name: "MetaMask", category: "Wallet", desc: "EVM", logo: "https://upload.wikimedia.org/wikipedia/commons/3/36/MetaMask_Fox.svg", logoSize: 34 },
];

const INTRO_STATS = [
  { value: "15+",  label: "Blockchains",    sub: "SOL · ETH · Base · more" },
  { value: "500+", label: "Tokens",         sub: "Across all chains"           },
  { value: "0.5%", label: "Platform Fee",   sub: "Transparent pricing"         },
  { value: "AI",   label: "Powered Engine", sub: "Natural language DeFi"       },
];

const WELCOME: Message = {
  id: 0, role: "assistant", ts: new Date(),
  text: "👋 Hello! I'm your AI crypto assistant.\n\nI can help you:\n• Check wallet balances across Solana, Ethereum, BNB Chain, Polygon and more\n• Get real-time token prices\n• Build same-chain swaps, staking, and liquidity transactions via Jupiter & Enso\n• Build cross-chain bridge transactions via deBridge\n\nJust type below or tap a quick action 🚀",
};

const APP_VERSION = "2026-03-21-wallet-swap-fix-4";

let nextId = 1;

const LOCAL_CHAT_PREFIX = "ap_local_chat:";
const LOCAL_CHAT_INDEX_PREFIX = "ap_local_chat_index:";

function localChatOwnerKey() {
  if (typeof window === "undefined") return "guest";
  return localStorage.getItem("ap_sol_wallet") || localStorage.getItem("ap_wallet") || "guest";
}

function localChatIndexKey() {
  return `${LOCAL_CHAT_INDEX_PREFIX}${localChatOwnerKey()}`;
}

function localChatStorageKey(sessionId?: string | null) {
  if (typeof window === "undefined") return null;
  const key = sessionId
    || localStorage.getItem("ap_chat_session")
    || localStorage.getItem("ap_sol_wallet")
    || localStorage.getItem("ap_wallet")
    || "guest";
  return `${LOCAL_CHAT_PREFIX}${key}`;
}

function loadLocalChatIndex(): ChatItem[] {
  if (typeof window === "undefined" || localStorage.getItem("ap_token")) return [];
  const raw = localStorage.getItem(localChatIndexKey());
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is ChatItem => !!item && typeof item.id === "string" && typeof item.title === "string" && typeof item.updated_at === "string")
      .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
  } catch {
    return [];
  }
}

function saveLocalChatIndex(chats: ChatItem[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(localChatIndexKey(), JSON.stringify(chats));
}

function upsertLocalChatIndex(chat: ChatItem): ChatItem[] {
  const next = [chat, ...loadLocalChatIndex().filter(item => item.id !== chat.id)]
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
  saveLocalChatIndex(next);
  return next;
}

function removeLocalChatIndex(chatId: string): ChatItem[] {
  const next = loadLocalChatIndex().filter(item => item.id !== chatId);
  saveLocalChatIndex(next);
  return next;
}

function titleFromMessages(messages: Message[]) {
  const firstUser = messages.find(message => message.role === "user" && message.text.trim());
  const title = firstUser?.text.trim() || "New Chat";
  return title.length > 40 ? `${title.slice(0, 40)}…` : title;
}

function loadLocalChatMessages(sessionId?: string | null): Message[] | null {
  const key = localChatStorageKey(sessionId);
  if (!key || localStorage.getItem("ap_token")) return null;
  const raw = localStorage.getItem(key);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    const restored = parsed
      .map((item): Message | null => {
        if (!item || (item.role !== "user" && item.role !== "assistant") || typeof item.text !== "string") return null;
        return {
          ...item,
          id: typeof item.id === "number" ? item.id : nextId++,
          ts: item.ts ? new Date(item.ts) : new Date(),
        } as Message;
      })
      .filter((item): item is Message => Boolean(item));
    if (!restored.length) return null;
    nextId = Math.max(nextId, ...restored.map(m => m.id + 1));
    return restored;
  } catch {
    return null;
  }
}

function shouldPersistLocalMessages(messages: Message[]) {
  return messages.some(m => m.id !== WELCOME.id || m.text !== WELCOME.text || m.role !== WELCOME.role);
}

function inlineMarkdown(text: string, prefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let index = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    const start = match.index ?? 0;
    if (start > last) nodes.push(text.slice(last, start));
    const value = match[0];
    if (value.startsWith("**")) {
      nodes.push(<strong key={`${prefix}-strong-${index++}`}>{value.slice(2, -2)}</strong>);
    } else {
      nodes.push(<code key={`${prefix}-code-${index++}`}>{value.slice(1, -1)}</code>);
    }
    last = start + value.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function MarkdownText({ text }: { text: string }) {
  const lines = text.split(/\r?\n/);
  const blocks: React.ReactNode[] = [];
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (!line.trim()) continue;
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = Math.min(heading[1].length, 3) as 1 | 2 | 3;
      const Tag = `h${level}` as keyof JSX.IntrinsicElements;
      blocks.push(<Tag key={`h-${i}`} className="agent-md-heading">{inlineMarkdown(heading[2], `h-${i}`)}</Tag>);
      continue;
    }
    if (/^[-*]\s+/.test(line.trim())) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*]\s+/, ""));
        i += 1;
      }
      i -= 1;
      blocks.push(
        <ul key={`ul-${i}`} className="agent-md-list">
          {items.map((item, idx) => <li key={idx}>{inlineMarkdown(item, `li-${i}-${idx}`)}</li>)}
        </ul>
      );
      continue;
    }
    const para = [line.trim()];
    while (i + 1 < lines.length && lines[i + 1].trim() && !/^(#{1,6})\s+/.test(lines[i + 1]) && !/^[-*]\s+/.test(lines[i + 1].trim())) {
      i += 1;
      para.push(lines[i].trim());
    }
    blocks.push(<p key={`p-${i}`}>{inlineMarkdown(para.join(" "), `p-${i}`)}</p>);
  }
  return <div className="agent-md">{blocks.length ? blocks : text}</div>;
}

// ── Framer Motion Variants ───────────────────────────────────────────────────
const fadeUp:  Variants = { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: "easeOut" as const } } };
const slideIn: Variants = { hidden: { opacity: 0, x: 18 }, show: { opacity: 1, x: 0, transition: { duration: 0.28, ease: "easeOut" as const } } };
const scaleIn: Variants = { hidden: { opacity: 0, scale: 0.96 }, show: { opacity: 1, scale: 1, transition: { duration: 0.25, ease: "easeOut" as const } } };
const MotionDiv = motion.div;

// ── CSS ─────────────────────────────────────────────────────────────────────
const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html, body, #root { height: 100%; }

  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #03150f; color: #E2E8F0; overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }

  ::-webkit-scrollbar { width: 3px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 99px; }

  /* ── Animated background ── */
  .bg-canvas { position: fixed; inset: 0; z-index: 0; overflow: hidden; pointer-events: none; }
  .blob { position: absolute; border-radius: 50%; filter: blur(90px); animation: drift 20s ease-in-out infinite; }
  .blob-1 { width: 700px; height: 700px; top: -250px; left: -200px; background: radial-gradient(circle, rgba(139,92,246,0.16) 0%, transparent 70%); }
  .blob-2 { width: 600px; height: 600px; bottom: -180px; right: -120px; background: radial-gradient(circle, rgba(240,185,11,0.11) 0%, transparent 70%); animation-delay: -7s; }
  .blob-3 { width: 500px; height: 500px; top: 35%; left: 38%; background: radial-gradient(circle, rgba(59,130,246,0.09) 0%, transparent 70%); animation-delay: -14s; }
  .blob-4 { width: 400px; height: 400px; top: 60%; left: 10%; background: radial-gradient(circle, rgba(16,185,129,0.07) 0%, transparent 70%); animation-delay: -4s; }
  @keyframes drift {
    0%,100% { transform: translate(0,0) scale(1); }
    33%  { transform: translate(50px,-35px) scale(1.06); }
    66%  { transform: translate(-25px,45px) scale(0.94); }
  }

  /* ══ INTRO SCREEN ══════════════════════════════════════════════════════════ */
  .intro-screen {
    position: fixed; inset: 0; z-index: 200;
    background: #03150f;
    overflow: hidden;
    transition: opacity 0.7s ease, transform 0.7s ease;
  }
  .intro-screen.fading { opacity: 0; transform: scale(1.015); pointer-events: none; }
  .intro-scroll { height: 100%; overflow-y: auto; scroll-behavior: smooth; }
  .intro-scroll::-webkit-scrollbar { width: 3px; }
  .intro-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 99px; }

  .intro-nav {
    position: sticky; top: 0; z-index: 10;
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 48px;
    backdrop-filter: blur(20px) saturate(1.4);
    background: rgba(6,11,20,0.85);
    border-bottom: 1px solid rgba(255,255,255,0.07);
  }
  .intro-nav-logo { display: flex; align-items: center; gap: 10px; }
  .intro-nav-mark {
    width: 32px; height: 32px; border-radius: 9px;
    display: flex; align-items: center; justify-content: center;
    overflow: hidden;
  }
  .intro-nav-name { font-size: 15px; font-weight: 700; letter-spacing: -0.3px; }
  .intro-nav-badge {
    font-size: 9px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase;
    padding: 3px 7px; border-radius: 99px;
    background: rgba(16,185,129,0.12); border: 1px solid rgba(16,185,129,0.3); color: #10B981;
  }
  .intro-nav-enter {
    padding: 9px 20px; border-radius: 10px; border: none; cursor: pointer;
    font-size: 13px; font-weight: 600; font-family: inherit;
    background: linear-gradient(135deg, #10b981, #34d399); color: #03150f;
    transition: all 0.2s; box-shadow: 0 2px 14px rgba(16,185,129,0.24);
  }
  .intro-nav-enter:hover { transform: translateY(-1px); box-shadow: 0 4px 20px rgba(16,185,129,0.3); }

  .intro-hero {
    min-height: calc(100vh - 65px);
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    text-align: center; padding: 70px 48px 80px;
  }
  .intro-hero-eyebrow {
    display: inline-flex; align-items: center; gap: 8px;
    background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.22);
    border-radius: 99px; padding: 6px 16px;
    font-size: 11px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;
    color: #34D399; margin-bottom: 28px;
    animation: fade-up 0.6s ease both;
  }
  .intro-hero-dot { width: 6px; height: 6px; border-radius: 50%; background: #34D399; animation: pulse-gold 2s infinite; }
  @keyframes pulse-gold {
    0%,100% { opacity: 1; box-shadow: 0 0 0 0 rgba(16,185,129,0.42); }
    50%     { opacity: 0.7; box-shadow: 0 0 0 5px rgba(240,185,11,0); }
  }
  .intro-hero-headline {
    font-size: 72px; font-weight: 900; letter-spacing: -3px; line-height: 1;
    margin-bottom: 22px; max-width: 800px;
    animation: fade-up 0.6s 0.1s ease both;
  }
  .intro-hero-headline .line1 { display: block; color: #fff; }
  .intro-hero-headline .line2 {
    display: block;
    background: linear-gradient(135deg, #6ee7b7 0%, #10b981 50%, #34d399 100%);
    background-size: 200% auto;
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    animation: fade-up 0.6s 0.1s ease both, shimmer 4s linear infinite;
  }
  @keyframes shimmer { to { background-position: 200% center; } }
  .intro-hero-sub {
    font-size: 18px; color: rgba(255,255,255,0.48); line-height: 1.7;
    margin-bottom: 38px; max-width: 520px;
    animation: fade-up 0.6s 0.2s ease both;
  }
  .intro-hero-btns {
    display: flex; align-items: center; gap: 14px; margin-bottom: 60px;
    animation: fade-up 0.6s 0.3s ease both;
  }
  .intro-btn-primary {
    padding: 15px 32px; border-radius: 14px; border: none; cursor: pointer;
    font-size: 15px; font-weight: 700; font-family: inherit;
    background: linear-gradient(135deg, #10b981, #34d399); color: #03150f;
    box-shadow: 0 4px 30px rgba(16,185,129,0.24);
    transition: all 0.2s; display: flex; align-items: center; gap: 8px;
  }
  .intro-btn-primary:hover { transform: translateY(-2px); box-shadow: 0 8px 40px rgba(240,185,11,0.55); }
  .intro-btn-secondary {
    padding: 15px 28px; border-radius: 14px; cursor: pointer;
    font-size: 15px; font-weight: 600; font-family: inherit;
    background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.12);
    color: rgba(255,255,255,0.7); transition: all 0.2s;
  }
  .intro-btn-secondary:hover { background: rgba(255,255,255,0.09); border-color: rgba(255,255,255,0.2); color: #fff; }
  .intro-stats-row {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 2px;
    width: 100%; max-width: 700px;
    background: rgba(255,255,255,0.06); border-radius: 18px; overflow: hidden;
    border: 1px solid rgba(255,255,255,0.08);
    animation: fade-up 0.6s 0.4s ease both;
  }
  .intro-stat-item { padding: 22px 18px; text-align: center; background: rgba(6,11,20,0.6); border-right: 1px solid rgba(255,255,255,0.06); }
  .intro-stat-item:last-child { border-right: none; }
  .intro-stat-val   { font-size: 26px; font-weight: 800; letter-spacing: -0.8px; color: #34D399; margin-bottom: 4px; }
  .intro-stat-label { font-size: 12px; font-weight: 600; color: #fff; margin-bottom: 3px; }
  .intro-stat-sub   { font-size: 10px; color: rgba(255,255,255,0.3); }
  @keyframes fade-up { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }

  .intro-section { padding: 80px; border-top: 1px solid rgba(255,255,255,0.05); }
  .intro-section-tag   { font-size: 10px; font-weight: 800; letter-spacing: 2px; text-transform: uppercase; color: #34D399; margin-bottom: 14px; }
  .intro-section-title { font-size: 40px; font-weight: 800; letter-spacing: -1.2px; line-height: 1.1; margin-bottom: 12px; }
  .intro-section-sub   { font-size: 16px; color: rgba(255,255,255,0.42); line-height: 1.7; max-width: 520px; margin-bottom: 48px; }

  .intro-feat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
  .intro-feat-card {
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 20px; padding: 28px 24px;
    backdrop-filter: blur(15px);
    transition: all 0.25s; position: relative; overflow: hidden;
  }
  .intro-feat-card::before {
    content: ''; position: absolute; inset: 0; border-radius: 20px;
    background: linear-gradient(135deg, rgba(16,185,129,0.08), transparent);
    opacity: 0; transition: opacity 0.25s;
  }
  .intro-feat-card:hover { border-color: rgba(16,185,129,0.22); transform: translateY(-3px); box-shadow: 0 8px 30px rgba(0,0,0,0.3); }
  .intro-feat-card:hover::before { opacity: 1; }
  .intro-feat-icon  { font-size: 32px; margin-bottom: 16px; }
  .intro-feat-title { font-size: 16px; font-weight: 700; margin-bottom: 8px; letter-spacing: -0.2px; }
  .intro-feat-desc  { font-size: 13px; color: rgba(255,255,255,0.4); line-height: 1.7; }

  .intro-how-bg { background: rgba(255,255,255,0.015); }
  .intro-steps { display: grid; grid-template-columns: 1fr auto 1fr auto 1fr; gap: 0; align-items: start; }
  .intro-step {
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 20px; padding: 28px 24px; text-align: center;
    backdrop-filter: blur(15px);
  }
  .intro-step-num   { font-size: 11px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase; color: rgba(240,185,11,0.6); margin-bottom: 14px; }
  .intro-step-icon  { font-size: 36px; margin-bottom: 14px; }
  .intro-step-title { font-size: 17px; font-weight: 700; letter-spacing: -0.3px; margin-bottom: 8px; }
  .intro-step-desc  { font-size: 13px; color: rgba(255,255,255,0.38); line-height: 1.7; }
  .intro-step-arrow { display: flex; align-items: center; justify-content: center; font-size: 22px; color: rgba(255,255,255,0.2); padding: 0 8px; margin-top: 60px; }

  .intro-partners-section { margin-bottom: 60px; }
  .intro-partners-category { font-size: 11px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: #34D399; margin-bottom: 20px; text-align: center; }
  .intro-partners-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 16px;
    margin-bottom: 40px;
  }
  .intro-partner {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 24px 16px;
    text-align: center;
    transition: all 0.25s ease;
    backdrop-filter: blur(15px);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 140px;
  }
  .intro-partner:hover {
    background: rgba(255,255,255,0.06);
    border-color: rgba(16,185,129,0.25);
    transform: translateY(-4px);
    box-shadow: 0 12px 40px rgba(0,0,0,0.25);
  }
  .intro-partner-logo {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    object-fit: contain;
    margin-bottom: 12px;
    filter: brightness(0.95);
    transition: filter 0.2s;
  }
  .intro-partner:hover .intro-partner-logo {
    filter: brightness(1.1);
  }
  .intro-partner-name { font-size: 14px; font-weight: 700; margin-bottom: 4px; color: rgba(255,255,255,0.9); }
  .intro-partner-desc { font-size: 11px; color: rgba(255,255,255,0.4); font-weight: 500; }
  .intro-partner-category-tag {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: rgba(16,185,129,0.7);
    background: rgba(16,185,129,0.1);
    border: 1px solid rgba(16,185,129,0.2);
    border-radius: 99px;
    padding: 3px 10px;
    margin-top: 10px;
  }

  .intro-bottom-cta { padding: 80px; border-top: 1px solid rgba(255,255,255,0.05); text-align: center; display: flex; flex-direction: column; align-items: center; }
  .intro-cta-glow { width: 200px; height: 200px; border-radius: 50%; filter: blur(80px); background: radial-gradient(circle, rgba(16,185,129,0.25) 0%, transparent 70%); margin-bottom: -80px; z-index: 0; position: relative; }
  .intro-cta-content { position: relative; z-index: 1; }
  .intro-cta-title { font-size: 48px; font-weight: 900; letter-spacing: -1.5px; line-height: 1.1; margin-bottom: 16px; }
  .intro-cta-sub   { font-size: 17px; color: rgba(255,255,255,0.4); line-height: 1.7; margin-bottom: 36px; max-width: 440px; }
  .intro-cta-terms { font-size: 11px; color: rgba(255,255,255,0.2); margin-top: 18px; }

  .intro-footer { padding: 24px 80px; border-top: 1px solid rgba(255,255,255,0.05); display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: rgba(255,255,255,0.22); }
  .intro-footer-links { display: flex; gap: 20px; }
  .intro-footer-link { color: rgba(255,255,255,0.22); cursor: pointer; transition: color 0.15s; }
  .intro-footer-link:hover { color: rgba(255,255,255,0.5); }

  /* ══ APP LAYOUT ═════════════════════════════════════════════════════════════ */
  .app { position: relative; z-index: 1; display: flex; flex: 1; min-height: 0; }

  /* ── Sidebar ── */
  .sidebar {
    width: 268px; flex-shrink: 0;
    backdrop-filter: blur(20px) saturate(1.6);
    background: rgba(8,13,22,0.7);
    border-right: 1px solid rgba(255,255,255,0.08);
    display: flex; flex-direction: column; overflow: hidden;
  }
  .sidebar-logo { padding: 20px 18px 16px; border-bottom: 1px solid rgba(255,255,255,0.06); display: flex; align-items: center; gap: 11px; transition: background 0.2s; border-radius: 0; }
  .sidebar-logo:hover { background: rgba(16,185,129,0.05); }
  .logo-mark { width: 36px; height: 36px; border-radius: 10px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 24px rgba(16,185,129,0.24); overflow: hidden; }
  .logo-text { font-size: 15px; font-weight: 700; letter-spacing: -0.3px; }
  .logo-sub  { font-size: 10px; color: rgba(255,255,255,0.3); margin-top: 1px; }

  .wallet-section { padding: 14px 14px 10px; }
  .wallet-card {
    background: linear-gradient(135deg, rgba(16,185,129,0.1), rgba(52,211,153,0.04));
    border: 1px solid rgba(16,185,129,0.18);
    border-radius: 14px; padding: 14px;
    backdrop-filter: blur(15px);
    box-shadow: inset 0 1px 0 rgba(16,185,129,0.08);
  }
  .wallet-label   { font-size: 10px; color: rgba(255,255,255,0.35); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
  .wallet-address { font-size: 12px; color: rgba(255,255,255,0.5); font-family: 'SF Mono','Fira Code',monospace; margin-bottom: 12px; }
  .connect-btn { width: 100%; padding: 11px 14px; border-radius: 12px; background: linear-gradient(135deg, rgba(16,185,129,0.16), rgba(52,211,153,0.08)); border: 1px solid rgba(16,185,129,0.25); color: #34D399; font-size: 13px; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 8px; cursor: pointer; transition: all 0.2s; font-family: inherit; }
  .connect-btn:hover { background: rgba(16,185,129,0.22); border-color: rgba(16,185,129,0.34); box-shadow: 0 0 20px rgba(16,185,129,0.16); }
  .wallet-btn-row { display: flex; gap: 7px; }
  .connect-btn.half { flex: 1; width: auto; font-size: 12px; padding: 9px 10px; }
  .disconnect-btn { flex: 0 0 auto; padding: 9px 11px; border-radius: 12px; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.22); color: #F87171; font-size: 12px; font-weight: 600; cursor: pointer; font-family: inherit; transition: all 0.2s; display: flex; align-items: center; gap: 5px; }
  .disconnect-btn:hover { background: rgba(239,68,68,0.16); border-color: rgba(239,68,68,0.4); }

  .net-section   { padding: 0 14px 10px; }
  .section-label { font-size: 10px; color: rgba(255,255,255,0.28); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
  .net-pill {
    display: flex; align-items: center; justify-content: space-between;
    background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px; padding: 9px 12px;
    backdrop-filter: blur(15px);
  }
  .net-left  { display: flex; align-items: center; gap: 9px; }
  .net-icon  { font-size: 18px; }
  .net-name  { font-size: 13px; font-weight: 600; }
  .net-id    { font-size: 10px; color: rgba(255,255,255,0.3); margin-top: 1px; }
  .net-badge { font-size: 10px; font-weight: 600; padding: 3px 9px; border-radius: 99px; background: rgba(16,185,129,0.12); color: #10B981; border: 1px solid rgba(16,185,129,0.25); }

  .status-dot { width: 8px; height: 8px; border-radius: 50%; animation: pulse-status 2.5s infinite; flex-shrink: 0; }
  .status-dot.online  { background: #10B981; }
  .status-dot.offline { background: #EF4444; animation: none; }
  .status-dot.pending { background: #34D399; animation: none; }
  .status-dot.purple  { background: #A78BFA; animation: pulse-purple 2.5s infinite; }
  @keyframes pulse-status { 0% { box-shadow: 0 0 0 0 rgba(16,185,129,0.5); } 70% { box-shadow: 0 0 0 7px rgba(16,185,129,0); } 100%{ box-shadow: 0 0 0 0 rgba(16,185,129,0); } }
  @keyframes pulse-purple  { 0% { box-shadow: 0 0 0 0 rgba(167,139,250,0.5); } 70% { box-shadow: 0 0 0 7px rgba(167,139,250,0); } 100%{ box-shadow: 0 0 0 0 rgba(167,139,250,0); } }

  .tokens-section { padding: 0 14px; flex: 1; overflow-y: auto; }
  .token-row { display: flex; align-items: center; justify-content: space-between; padding: 9px 10px; margin-bottom: 5px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07); border-radius: 11px; transition: all 0.2s; cursor: pointer; backdrop-filter: blur(12px); }
  .token-row:hover { background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.12); transform: translateX(2px); }
  .token-left  { display: flex; align-items: center; gap: 10px; }
  .token-icon  { width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 15px; font-weight: 700; flex-shrink: 0; }
  .token-sym   { font-size: 13px; font-weight: 600; }
  .token-net   { font-size: 10px; color: rgba(255,255,255,0.3); margin-top: 1px; }
  .token-right { text-align: right; }
  .token-amt   { font-size: 12px; font-weight: 600; }
  .token-change{ font-size: 10px; margin-top: 2px; }
  .change-pos  { color: #10B981; }
  .change-neg  { color: #EF4444; }
  .change-neu  { color: rgba(255,255,255,0.3); }

  /* ── Greenfield Memory indicator ── */
  .greenfield-row {
    padding: 8px 14px;
    border-top: 1px solid rgba(255,255,255,0.05);
    display: flex; align-items: center; gap: 8px;
    background: linear-gradient(135deg, rgba(139,92,246,0.06), transparent);
  }
  .greenfield-icon { font-size: 13px; }
  .greenfield-label { font-size: 10px; color: rgba(255,255,255,0.45); flex: 1; }
  .greenfield-badge {
    font-size: 9px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase;
    padding: 2px 7px; border-radius: 99px;
    background: rgba(139,92,246,0.15); border: 1px solid rgba(139,92,246,0.3); color: #A78BFA;
  }

  .sidebar-footer { padding: 10px 14px; border-top: 1px solid rgba(255,255,255,0.06); display: flex; align-items: center; justify-content: space-between; }
  .status-row  { display: flex; align-items: center; gap: 7px; font-size: 11px; color: rgba(255,255,255,0.35); }
  .footer-right { display: flex; align-items: center; gap: 10px; }
  .version     { font-size: 10px; color: rgba(255,255,255,0.2); }
  .about-btn   { font-size: 10px; color: rgba(255,255,255,0.22); background: none; border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; padding: 3px 8px; cursor: pointer; font-family: inherit; transition: all 0.15s; }
  .about-btn:hover { color: #34D399; border-color: rgba(16,185,129,0.24); background: rgba(16,185,129,0.08); }

  /* ══ MAIN ══════════════════════════════════════════════════════════════════ */
  .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

  /* ── Market Ticker ── */
  .ticker-bar { height: 32px; overflow: hidden; background: rgba(255,255,255,0.015); border-bottom: 1px solid rgba(255,255,255,0.06); display: flex; align-items: center; }
  .ticker-track { display: flex; align-items: center; animation: ticker-scroll 36s linear infinite; width: max-content; }
  .ticker-item  { display: inline-flex; align-items: center; gap: 7px; padding: 0 22px; font-size: 11px; font-weight: 500; border-right: 1px solid rgba(255,255,255,0.05); white-space: nowrap; }
  .ticker-sym   { color: rgba(255,255,255,0.6); font-weight: 700; }
  .ticker-price { color: rgba(255,255,255,0.75); }
  .ticker-chg.pos { color: #10B981; }
  .ticker-chg.neg { color: #EF4444; }
  .ticker-chg.neu { color: rgba(255,255,255,0.25); }
  @keyframes ticker-scroll { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }

  /* ── Tab bar ── */
  .tabbar { backdrop-filter: blur(20px) saturate(1.4); background: rgba(8,13,22,0.6); border-bottom: 1px solid rgba(255,255,255,0.07); padding: 0 24px; display: flex; align-items: center; height: 52px; flex-shrink: 0; }
  .tab-btn { height: 100%; padding: 0 18px; background: none; border: none; color: rgba(255,255,255,0.4); font-size: 13px; font-weight: 500; cursor: pointer; position: relative; transition: color 0.2s; font-family: inherit; display: flex; align-items: center; gap: 7px; }
  .tab-btn::after { content: ''; position: absolute; bottom: 0; left: 18px; right: 18px; height: 2px; border-radius: 99px; background: linear-gradient(90deg, #10b981, #34d399); opacity: 0; transition: opacity 0.2s; }
  .tab-btn.active { color: #34D399; font-weight: 600; }
  .tab-btn.active::after { opacity: 1; }
  .tab-btn:hover:not(.active) { color: rgba(255,255,255,0.7); }
  .tab-badge { width: 6px; height: 6px; border-radius: 50%; background: #34D399; box-shadow: 0 0 6px rgba(16,185,129,0.35); }

  /* ── Tab panel wrapper ── */
  .tab-panel { flex: 1; overflow: hidden; display: flex; flex-direction: column; }

  /* ══ DASHBOARD ═════════════════════════════════════════════════════════════ */
  .dash { flex: 1; overflow-y: auto; padding: 24px 28px 36px; }
  .dash-header { margin-bottom: 20px; }
  .dash-title  { font-size: 22px; font-weight: 800; letter-spacing: -0.5px; margin-bottom: 3px; }
  .dash-sub    { font-size: 13px; color: rgba(255,255,255,0.35); }

  .plat-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
  .plat-stat {
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 13px; padding: 14px; text-align: center;
    backdrop-filter: blur(15px);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    transition: border-color 0.2s;
  }
  .plat-stat:hover { border-color: rgba(255,255,255,0.13); }
  .plat-stat-val   { font-size: 18px; font-weight: 800; letter-spacing: -0.4px; margin-bottom: 3px; }
  .plat-stat-val.gold   { color: #34D399; }
  .plat-stat-val.green  { color: #10B981; }
  .plat-stat-val.purple { color: #A78BFA; }
  .plat-stat-val.blue   { color: #60A5FA; }
  .plat-stat-label { font-size: 10px; color: rgba(255,255,255,0.28); font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }

  .section-head  { display: flex; align-items: center; justify-content: space-between; margin-bottom: 11px; }
  .section-title { font-size: 13px; font-weight: 700; color: rgba(255,255,255,0.8); }
  .section-link  { font-size: 11px; color: rgba(255,255,255,0.28); cursor: pointer; transition: color 0.15s; }
  .section-link:hover { color: #34D399; }

  .market-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
  .market-card {
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px; padding: 15px; cursor: pointer;
    backdrop-filter: blur(15px);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    transition: all 0.2s;
  }
  .market-card:hover { background: rgba(255,255,255,0.055); border-color: rgba(255,255,255,0.14); transform: translateY(-2px); box-shadow: 0 8px 28px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.06); }
  .market-card-head  { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
  .market-card-icon  { width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 15px; font-weight: 700; }
  .market-card-chg   { font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 99px; }
  .market-card-chg.pos { background: rgba(16,185,129,0.12); color: #10B981; }
  .market-card-chg.neg { background: rgba(239,68,68,0.12);  color: #EF4444; }
  .market-card-chg.neu { background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.3); }
  .market-card-sym   { font-size: 14px; font-weight: 700; }
  .market-card-name  { font-size: 10px; color: rgba(255,255,255,0.28); margin-top: 1px; }
  .market-card-price { font-size: 18px; font-weight: 700; letter-spacing: -0.4px; margin-top: 10px; }
  .market-card-vol   { font-size: 10px; color: rgba(255,255,255,0.22); margin-top: 3px; }

  .action-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
  .action-card {
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px; padding: 18px 14px; cursor: pointer; text-align: center;
    backdrop-filter: blur(15px);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    transition: all 0.2s;
  }
  .action-card:hover { background: rgba(16,185,129,0.07); border-color: rgba(16,185,129,0.22); transform: translateY(-2px); box-shadow: 0 6px 20px rgba(16,185,129,0.08), inset 0 1px 0 rgba(16,185,129,0.1); }
  .action-card-icon  { font-size: 26px; margin-bottom: 9px; }
  .action-card-label { font-size: 13px; font-weight: 700; margin-bottom: 4px; }
  .action-card-desc  { font-size: 11px; color: rgba(255,255,255,0.3); }

  .feature-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 20px; }
  .feature-card {
    background: rgba(255,255,255,0.025); border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px; padding: 16px; display: flex; gap: 13px; align-items: flex-start;
    backdrop-filter: blur(15px);
    transition: all 0.2s;
  }
  .feature-card:hover { background: rgba(255,255,255,0.04); border-color: rgba(255,255,255,0.11); }
  .feature-card-icon  { font-size: 22px; flex-shrink: 0; margin-top: 1px; }
  .feature-card-title { font-size: 13px; font-weight: 700; margin-bottom: 4px; }
  .feature-card-desc  { font-size: 11px; color: rgba(255,255,255,0.32); line-height: 1.6; }

  .cta-hero {
    background: linear-gradient(135deg, rgba(16,185,129,0.08), rgba(139,92,246,0.07));
    border: 1px solid rgba(16,185,129,0.18); border-radius: 18px; padding: 24px 28px;
    display: flex; align-items: center; justify-content: space-between; gap: 24px;
    backdrop-filter: blur(15px);
    box-shadow: inset 0 1px 0 rgba(16,185,129,0.08);
  }
  .cta-hero-left  { flex: 1; }
  .cta-hero-title { font-size: 16px; font-weight: 800; letter-spacing: -0.3px; margin-bottom: 6px; }
  .cta-hero-sub   { font-size: 12px; color: rgba(255,255,255,0.38); line-height: 1.65; }
  .cta-hero-btn   { padding: 13px 24px; border-radius: 12px; border: none; cursor: pointer; font-size: 14px; font-weight: 700; font-family: inherit; background: linear-gradient(135deg, #10b981, #34d399); color: #03150f; white-space: nowrap; transition: all 0.2s; box-shadow: 0 4px 20px rgba(16,185,129,0.24); }
  .cta-hero-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 28px rgba(16,185,129,0.3); }

  /* ══ CHAT ══════════════════════════════════════════════════════════════════ */
  .chat-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  .messages  { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }

  .cap-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 4px; }
  .cap-card {
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.09);
    border-radius: 14px; padding: 14px 16px; cursor: pointer;
    backdrop-filter: blur(15px);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    transition: all 0.2s; display: flex; align-items: flex-start; gap: 12px;
  }
  .cap-card:hover { background: rgba(16,185,129,0.07); border-color: rgba(16,185,129,0.22); transform: translateY(-1px); }
  .cap-icon  { font-size: 22px; flex-shrink: 0; }
  .cap-title { font-size: 13px; font-weight: 600; margin-bottom: 2px; }
  .cap-desc  { font-size: 11px; color: rgba(255,255,255,0.3); line-height: 1.5; }

  .msg-row { display: flex; align-items: flex-end; gap: 10px; }
  .msg-row.user { flex-direction: row-reverse; }
  .msg-avatar { width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; }
  .msg-avatar.user      { background: linear-gradient(135deg, rgba(16,185,129,0.16), rgba(6,95,70,0.12)); border: 1px solid rgba(16,185,129,0.24); color: #34D399; }
  .msg-avatar.assistant { background: linear-gradient(135deg, rgba(139,92,246,0.2), rgba(59,130,246,0.15)); border: 1px solid rgba(139,92,246,0.3); color: #A78BFA; }

  .msg-body   { max-width: 72%; }
  .msg-bubble { padding: 12px 16px; font-size: 13.5px; line-height: 1.65; word-break: break-word; white-space: pre-wrap; }
  .msg-bubble.user {
    background: linear-gradient(135deg, rgba(16,185,129,0.12), rgba(6,95,70,0.08));
    border: 1px solid rgba(16,185,129,0.22);
    backdrop-filter: blur(15px);
    box-shadow: inset 0 1px 0 rgba(16,185,129,0.08);
    border-radius: 16px 16px 4px 16px;
  }
  .msg-bubble.assistant {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.09);
    backdrop-filter: blur(15px);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    border-radius: 16px 16px 16px 4px;
  }
  .agent-md { white-space: normal; display: flex; flex-direction: column; gap: 8px; }
  .agent-md-heading { font-size: 17px; line-height: 1.25; font-weight: 850; color: #fff; }
  .agent-md-list { margin-left: 18px; display: flex; flex-direction: column; gap: 4px; }
  .agent-md strong { color: #fff; font-weight: 850; }
  .agent-md code { border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; padding: 1px 5px; background: rgba(15,23,42,0.7); font-family: 'JetBrains Mono', monospace; font-size: 12px; }
  .execution-notice-card { padding: 14px 16px; border-radius: 18px; border: 1px solid rgba(251,191,36,0.22); background: rgba(30,18,4,0.86); box-shadow: inset 0 1px 0 rgba(255,255,255,0.05); }
  .execution-notice-title { font-size: 14px; font-weight: 850; color: #fff; }
  .execution-notice-sub { margin-top: 6px; font-size: 12px; color: rgba(254,243,199,0.72); line-height: 1.55; }
  .execution-notice-steps { margin-top: 10px; display: flex; flex-direction: column; gap: 7px; }
  .execution-notice-step { display: flex; align-items: center; gap: 8px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.08); background: rgba(15,23,42,0.45); padding: 8px 10px; font-size: 12px; color: #f8fafc; }
  .execution-notice-index { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 8px; background: rgba(251,191,36,0.18); color: #fde68a; font-weight: 850; }
  .execution-notice-meta { margin-left: auto; color: rgba(226,232,240,0.45); font-size: 11px; }
  .msg-ts { font-size: 10px; color: rgba(255,255,255,0.25); margin-top: 5px; padding: 0 4px; }
  .msg-row.user .msg-ts { text-align: right; }

  /* ── Reasoning accordion ── */
  .reasoning-wrap { margin-top: 8px; }
  .reasoning-toggle {
    display: flex; align-items: center; gap: 7px;
    background: rgba(139,92,246,0.07); border: 1px solid rgba(139,92,246,0.18);
    border-radius: 10px; padding: 7px 12px; cursor: pointer;
    font-size: 11px; font-weight: 600; color: rgba(167,139,250,0.85);
    transition: all 0.2s; font-family: inherit; width: 100%;
    backdrop-filter: blur(12px);
  }
  .reasoning-toggle:hover { background: rgba(139,92,246,0.12); border-color: rgba(139,92,246,0.28); }
  .reasoning-toggle-icon { font-size: 13px; }
  .reasoning-toggle-text { flex: 1; text-align: left; }
  .reasoning-toggle-caret { font-size: 9px; opacity: 0.6; transition: transform 0.2s; }
  .reasoning-toggle-caret.open { transform: rotate(180deg); }
  .reasoning-steps-inner { overflow: hidden; }
  .reasoning-steps-list { padding: 8px 4px 4px; display: flex; flex-direction: column; gap: 5px; }
  .reasoning-step {
    display: flex; align-items: flex-start; gap: 9px;
    padding: 8px 10px; border-radius: 9px;
    background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05);
    backdrop-filter: blur(10px);
  }
  .reasoning-step-icon { font-size: 13px; flex-shrink: 0; margin-top: 1px; }
  .reasoning-step-label { font-size: 11px; font-weight: 600; }
  .reasoning-step-detail { font-size: 10px; color: rgba(255,255,255,0.35); margin-top: 2px; }
  .step-think   .reasoning-step-label { color: #A78BFA; }
  .step-tool    .reasoning-step-label { color: #60A5FA; }
  .step-result  .reasoning-step-label { color: #10B981; }
  .step-conclude .reasoning-step-label { color: #34D399; }

  /* ── Live reasoning (while loading) ── */
  .reasoning-live {
    display: flex; flex-direction: column; gap: 5px; padding: 10px 12px;
    background: rgba(139,92,246,0.06); border: 1px solid rgba(139,92,246,0.15);
    border-radius: 14px 14px 14px 4px;
    backdrop-filter: blur(15px); max-width: 72%;
    box-shadow: inset 0 1px 0 rgba(139,92,246,0.08);
  }
  .reasoning-live-title { font-size: 10px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: rgba(167,139,250,0.6); margin-bottom: 4px; }
  .reasoning-live-step { display: flex; align-items: center; gap: 8px; font-size: 11.5px; padding: 3px 0; }
  .reasoning-live-step-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
  .reasoning-live-step.active .reasoning-live-step-dot  { background: #A78BFA; animation: pulse-purple 1.5s infinite; }
  .reasoning-live-step.done   .reasoning-live-step-dot  { background: #10B981; }
  .reasoning-live-step.active .reasoning-live-step-text { color: rgba(255,255,255,0.8); }
  .reasoning-live-step.done   .reasoning-live-step-text { color: rgba(255,255,255,0.4); }
  .reasoning-live-waiting {
    display: flex; align-items: center; gap: 7px;
    padding: 6px 0 2px;
    border-top: 1px solid rgba(255,255,255,0.05); margin-top: 4px;
    font-size: 10px; color: rgba(167,139,250,0.55);
  }
  .reasoning-live-waiting .typing-dot { width: 5px; height: 5px; background: rgba(167,139,250,0.5); }

  /* ── Simulation Preview ── */
  .sim-preview {
    margin-top: 10px;
    background: linear-gradient(135deg, rgba(16,185,129,0.08), rgba(139,92,246,0.06));
    border: 1px solid rgba(16,185,129,0.22);
    border-radius: 14px; padding: 14px 16px;
    backdrop-filter: blur(15px);
    box-shadow: 0 4px 20px rgba(16,185,129,0.08), inset 0 1px 0 rgba(16,185,129,0.08);
  }
  .sim-title {
    font-size: 10px; font-weight: 800; letter-spacing: 1.2px; text-transform: uppercase;
    color: #34D399; margin-bottom: 12px; display: flex; align-items: center; gap: 6px;
  }
  .sim-row { display: flex; align-items: center; gap: 10px; }
  .sim-token {
    flex: 1; display: flex; align-items: center; gap: 10px;
    background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px; padding: 10px 12px;
    backdrop-filter: blur(10px);
  }
  .sim-token-icon  { font-size: 20px; }
  .sim-token-label { font-size: 10px; color: rgba(255,255,255,0.4); margin-bottom: 2px; }
  .sim-token-value { font-size: 14px; font-weight: 700; }
  .sim-token.to .sim-token-value { color: #10B981; }
  .sim-arrow { font-size: 18px; color: rgba(255,255,255,0.3); flex-shrink: 0; }
  .sim-meta { display: flex; gap: 10px; margin-top: 10px; }
  .sim-meta-item {
    flex: 1; display: flex; flex-direction: column; gap: 2px;
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px; padding: 8px 10px;
  }
  .sim-meta-label { font-size: 9px; color: rgba(255,255,255,0.35); text-transform: uppercase; letter-spacing: 0.6px; }
  .sim-meta-value { font-size: 12px; font-weight: 600; color: #10B981; }

  /* ── Balance Card ── */
  .balance-card {
    margin-top: 10px;
    background: linear-gradient(135deg, rgba(99,102,241,0.08), rgba(16,185,129,0.05));
    border: 1px solid rgba(99,102,241,0.2);
    border-radius: 14px; padding: 14px 16px;
    backdrop-filter: blur(15px);
    box-shadow: 0 4px 20px rgba(99,102,241,0.06), inset 0 1px 0 rgba(255,255,255,0.05);
  }
  .balance-card-title {
    font-size: 10px; font-weight: 800; letter-spacing: 1.2px; text-transform: uppercase;
    color: #818CF8; margin-bottom: 12px; display: flex; align-items: center; gap: 6px;
  }
  .balance-chain-block { margin-bottom: 10px; }
  .balance-chain-block:last-child { margin-bottom: 0; }
  .balance-chain-header {
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; font-weight: 700; color: rgba(255,255,255,0.65);
    text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 5px;
  }
  .balance-chain-icon { font-size: 14px; }
  .balance-chain-name { }
  .balance-token-list {
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px; padding: 4px 0; overflow: hidden;
  }
  .balance-token-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 6px 12px; transition: background 0.15s;
  }
  .balance-token-row:hover { background: rgba(255,255,255,0.04); }
  .balance-token-symbol { font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.8); }
  .balance-token-amount { font-size: 12px; font-weight: 600; color: #34D399; font-variant-numeric: tabular-nums; }
  .balance-total-footer {
    margin-top: 12px;
    padding: 10px 14px;
    background: linear-gradient(135deg, rgba(52,211,153,0.1), rgba(99,102,241,0.08));
    border: 1px solid rgba(52,211,153,0.25);
    border-radius: 10px;
    display: flex; justify-content: space-between; align-items: center;
  }
  .balance-total-label { font-size: 11px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase; color: rgba(255,255,255,0.5); display: flex; flex-direction: column; gap: 2px; }
  .balance-total-estimate { font-size: 9px; font-weight: 500; letter-spacing: 0.3px; text-transform: uppercase; color: rgba(255,255,255,0.3); }
  .balance-total-value { font-size: 18px; font-weight: 800; color: #34D399; font-variant-numeric: tabular-nums; letter-spacing: -0.5px; }

  /* ── Typing bubble ── */
  .typing-bubble { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px 16px 16px 4px; padding: 14px 18px; display: flex; align-items: center; gap: 5px; backdrop-filter: blur(15px); }
  .typing-dot { width: 7px; height: 7px; border-radius: 50%; background: rgba(255,255,255,0.3); animation: typing 1.3s ease-in-out infinite; }
  .typing-dot:nth-child(2) { animation-delay: 0.18s; }
  .typing-dot:nth-child(3) { animation-delay: 0.36s; }
  @keyframes typing { 0%,60%,100% { transform: translateY(0); opacity: 0.3; } 30% { transform: translateY(-6px); opacity: 1; } }

  .quick-bar { padding: 10px 24px; border-top: 1px solid rgba(255,255,255,0.06); backdrop-filter: blur(20px); background: rgba(8,13,22,0.5); display: flex; gap: 7px; flex-wrap: wrap; }
  .quick-chip { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.09); border-radius: 99px; padding: 6px 14px; font-size: 12px; font-weight: 500; color: rgba(255,255,255,0.55); cursor: pointer; transition: all 0.2s; font-family: inherit; }
  .quick-chip:hover { background: rgba(16,185,129,0.1); border-color: rgba(16,185,129,0.24); color: #34D399; }

  .input-area  { padding: 14px 24px 18px; backdrop-filter: blur(20px) saturate(1.4); background: rgba(8,13,22,0.6); border-top: 1px solid rgba(255,255,255,0.07); }
  .input-row   { display: flex; gap: 10px; align-items: flex-end; }
  .msg-input   { flex: 1; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 14px; padding: 12px 16px; font-size: 13.5px; color: #E2E8F0; font-family: inherit; resize: none; line-height: 1.55; max-height: 140px; overflow-y: auto; transition: border-color 0.2s, box-shadow 0.2s; backdrop-filter: blur(15px); }
  .msg-input::placeholder { color: rgba(255,255,255,0.2); }
  .msg-input:focus { outline: none; border-color: rgba(16,185,129,0.34); box-shadow: 0 0 0 3px rgba(16,185,129,0.08); }
  .send-btn { width: 44px; height: 44px; border-radius: 13px; border: none; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: 700; cursor: pointer; transition: all 0.2s; }
  .send-btn.active   { background: linear-gradient(135deg, #10b981, #34d399); color: #03150f; box-shadow: 0 4px 15px rgba(16,185,129,0.24); }
  .send-btn.active:hover { transform: scale(1.05); }
  .send-btn.inactive { background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.2); cursor: not-allowed; }
  .input-hint { font-size: 10px; color: rgba(255,255,255,0.2); margin-top: 8px; text-align: center; }

  /* ══ PORTFOLIO ═════════════════════════════════════════════════════════════ */
  .page       { flex: 1; overflow-y: auto; padding: 28px; }
  .page-title { font-size: 22px; font-weight: 700; letter-spacing: -0.4px; margin-bottom: 4px; }
  .page-sub   { font-size: 13px; color: rgba(255,255,255,0.35); margin-bottom: 24px; }

  .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 22px; }
  .stat-card  {
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px; padding: 18px; position: relative; overflow: hidden;
    backdrop-filter: blur(15px);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    transition: border-color 0.2s;
  }
  .stat-card:hover { border-color: rgba(255,255,255,0.13); }
  .stat-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; border-radius: 16px 16px 0 0; }
  .stat-card.gold::before  { background: linear-gradient(90deg, #10b981, #34d399); }
  .stat-card.green::before { background: linear-gradient(90deg, #10B981, #059669); }
  .stat-card.blue::before  { background: linear-gradient(90deg, #3B82F6, #8B5CF6); }
  .stat-icon  { font-size: 22px; margin-bottom: 12px; }
  .stat-value { font-size: 26px; font-weight: 700; letter-spacing: -0.5px; margin-bottom: 4px; }
  .stat-label { font-size: 11px; color: rgba(255,255,255,0.35); font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }

  .portfolio-empty { text-align: center; padding: 48px 24px; background: rgba(255,255,255,0.02); border: 1px dashed rgba(255,255,255,0.1); border-radius: 20px; margin-bottom: 22px; backdrop-filter: blur(15px); }
  .portfolio-empty-icon  { font-size: 48px; margin-bottom: 16px; opacity: 0.45; }
  .portfolio-empty-title { font-size: 18px; font-weight: 700; margin-bottom: 8px; }
  .portfolio-empty-sub   { font-size: 13px; color: rgba(255,255,255,0.35); margin-bottom: 24px; max-width: 300px; margin-left: auto; margin-right: auto; line-height: 1.6; }
  .portfolio-empty-btn   { padding: 12px 28px; border-radius: 12px; border: none; cursor: pointer; font-size: 14px; font-weight: 700; font-family: inherit; background: linear-gradient(135deg, #10b981, #34d399); color: #03150f; box-shadow: 0 4px 20px rgba(16,185,129,0.24); transition: all 0.2s; }
  .portfolio-empty-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 25px rgba(16,185,129,0.3); }

  .portfolio-table {
    background: rgba(255,255,255,0.025); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px; overflow: hidden; margin-bottom: 20px;
    backdrop-filter: blur(15px);
  }
  .table-head { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; padding: 12px 18px; border-bottom: 1px solid rgba(255,255,255,0.06); font-size: 10px; color: rgba(255,255,255,0.28); text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }
  .table-row  { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; padding: 13px 18px; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.04); transition: background 0.15s; }
  .table-row:last-child { border-bottom: none; }
  .table-row:hover { background: rgba(255,255,255,0.03); }
  .table-token { display: flex; align-items: center; gap: 12px; }
  .table-icon  { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 700; }
  .table-sym   { font-size: 14px; font-weight: 600; }
  .table-name  { font-size: 11px; color: rgba(255,255,255,0.3); margin-top: 2px; }
  .table-cell  { font-size: 13px; font-weight: 500; }
  .cell-muted  { color: rgba(255,255,255,0.3); }
  .tip-card    {
    background: linear-gradient(135deg, rgba(16,185,129,0.08), rgba(240,185,11,0.03));
    border: 1px solid rgba(16,185,129,0.18); border-radius: 14px; padding: 16px;
    display: flex; gap: 12px; align-items: flex-start;
    backdrop-filter: blur(15px);
  }
  .tip-icon  { font-size: 20px; flex-shrink: 0; }
  .tip-title { font-size: 13px; font-weight: 600; color: #34D399; margin-bottom: 5px; }
  .tip-text  { font-size: 12px; color: rgba(255,255,255,0.45); line-height: 1.6; }

  /* ══ SWAP ══════════════════════════════════════════════════════════════════ */
  .swap-wrap { max-width: 460px; }
  .swap-card {
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.09);
    border-radius: 20px; overflow: hidden; margin-bottom: 14px;
    backdrop-filter: blur(15px);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
  }
  .swap-field { padding: 18px 20px; }
  .swap-field-label { font-size: 11px; color: rgba(255,255,255,0.3); margin-bottom: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.6px; }
  .swap-row   { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .swap-input { background: none; border: none; outline: none; font-size: 32px; font-weight: 700; color: #E2E8F0; font-family: inherit; width: 0; flex: 1; min-width: 0; }
  .swap-input::placeholder { color: rgba(255,255,255,0.15); }
  .token-select-btn { display: flex; align-items: center; gap: 8px; flex-shrink: 0; background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 9px 14px; font-size: 14px; font-weight: 700; color: #E2E8F0; cursor: pointer; transition: all 0.2s; font-family: inherit; backdrop-filter: blur(10px); }
  .token-select-btn:hover { background: rgba(255,255,255,0.11); border-color: rgba(255,255,255,0.18); }
  .t-icon     { width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; }
  .swap-balance { font-size: 11px; color: rgba(255,255,255,0.28); margin-top: 10px; }
  .swap-divider { position: relative; border-top: 1px solid rgba(255,255,255,0.06); display: flex; align-items: center; justify-content: center; }
  .swap-arrow-btn { position: absolute; width: 38px; height: 38px; border-radius: 50%; background: rgba(10,15,25,0.9); backdrop-filter: blur(15px); border: 1px solid rgba(255,255,255,0.12); display: flex; align-items: center; justify-content: center; font-size: 18px; color: rgba(255,255,255,0.5); cursor: pointer; transition: all 0.2s; font-family: inherit; }
  .swap-arrow-btn:hover { border-color: rgba(16,185,129,0.34); color: #34D399; transform: rotate(180deg); }
  .swap-output { font-size: 32px; font-weight: 700; color: rgba(255,255,255,0.2); }
  .swap-info { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; padding: 14px 16px; margin-bottom: 14px; backdrop-filter: blur(15px); }
  .swap-info-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
  .swap-info-row:last-child { border-bottom: none; }
  .info-key  { color: rgba(255,255,255,0.35); }
  .info-val  { font-weight: 500; }
  .info-val.gold  { color: #34D399; }
  .info-val.green { color: #10B981; }
  .cta-btn { width: 100%; padding: 15px; border: none; border-radius: 14px; cursor: pointer; font-size: 15px; font-weight: 700; font-family: inherit; transition: all 0.2s; background: linear-gradient(135deg, rgba(16,185,129,0.16), rgba(52,211,153,0.12)); border: 1px solid rgba(16,185,129,0.25); color: #34D399; }
  .cta-btn:hover { background: linear-gradient(135deg, rgba(16,185,129,0.22), rgba(52,211,153,0.16)); box-shadow: 0 0 30px rgba(16,185,129,0.16); }
  .swap-hint { font-size: 11px; color: rgba(255,255,255,0.25); text-align: center; margin-top: 10px; }

  /* ══ AUTH SCREEN ════════════════════════════════════════════════════════════ */
  .auth-overlay {
    position: fixed; inset: 0; z-index: 300;
    background: rgba(6,11,20,0.88);
    backdrop-filter: blur(18px) saturate(1.4);
    display: flex; align-items: center; justify-content: center;
  }
  .auth-card {
    position: relative;
    width: 420px; max-width: 94vw;
    background: rgba(14,20,34,0.95);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 24px; padding: 36px;
    box-shadow: 0 24px 80px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.06);
  }
  .auth-logo { display: flex; align-items: center; gap: 11px; margin-bottom: 28px; }
  .auth-logo-mark { width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 24px rgba(16,185,129,0.24); overflow: hidden; }
  .auth-logo-text { font-size: 18px; font-weight: 700; }
  .auth-logo-sub { font-size: 11px; color: rgba(255,255,255,0.35); margin-top: 2px; }
  .auth-title { font-size: 22px; font-weight: 800; letter-spacing: -0.5px; margin-bottom: 6px; }
  .auth-sub { font-size: 13px; color: rgba(255,255,255,0.38); margin-bottom: 28px; line-height: 1.5; }
  .auth-tabs { display: flex; gap: 6px; margin-bottom: 24px; background: rgba(255,255,255,0.04); border-radius: 12px; padding: 4px; }
  .auth-tab { flex: 1; padding: 9px; border-radius: 9px; border: none; background: none; color: rgba(255,255,255,0.45); font-size: 13px; font-weight: 600; font-family: inherit; cursor: pointer; transition: all 0.2s; }
  .auth-tab.active { background: rgba(16,185,129,0.12); color: #34D399; border: 1px solid rgba(16,185,129,0.25); }
  .auth-field { margin-bottom: 14px; }
  .auth-label { font-size: 11px; font-weight: 600; color: rgba(255,255,255,0.45); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 7px; }
  .auth-input {
    width: 100%; padding: 12px 14px; border-radius: 12px;
    background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
    color: #E2E8F0; font-size: 14px; font-family: inherit;
    outline: none; transition: border-color 0.2s;
  }
  .auth-input:focus { border-color: rgba(16,185,129,0.34); }
  .auth-input::placeholder { color: rgba(255,255,255,0.22); }
  .auth-btn {
    width: 100%; padding: 14px; border: none; border-radius: 13px; margin-top: 6px;
    font-size: 14px; font-weight: 700; font-family: inherit; cursor: pointer;
    background: linear-gradient(135deg, #10b981, #34d399); color: #03150f;
    transition: all 0.2s; box-shadow: 0 4px 20px rgba(16,185,129,0.24);
  }
  .auth-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 28px rgba(16,185,129,0.3); }
  .auth-btn:disabled { opacity: 0.55; cursor: default; }
  .auth-btn.secondary {
    background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
    color: rgba(255,255,255,0.8); box-shadow: none;
  }
  .auth-btn.secondary:hover { background: rgba(255,255,255,0.1); box-shadow: none; transform: none; }
  .auth-toggle { text-align: center; margin-top: 16px; font-size: 12px; color: rgba(255,255,255,0.35); }
  .auth-toggle-link { color: #34D399; cursor: pointer; font-weight: 600; margin-left: 4px; }
  .auth-toggle-link:hover { opacity: 0.8; }
  .auth-or { display: flex; align-items: center; gap: 12px; margin: 20px 0; }
  .auth-or-line { flex: 1; height: 1px; background: rgba(255,255,255,0.08); }
  .auth-or-text { font-size: 11px; color: rgba(255,255,255,0.28); }
  .auth-wallet-addr { font-family: 'SF Mono','Fira Code',monospace; font-size: 11px; color: rgba(255,255,255,0.5); margin-top: 10px; text-align: center; }
  .auth-error { font-size: 12px; color: #F87171; margin-top: 10px; text-align: center; padding: 8px 12px; background: rgba(248,113,113,0.1); border-radius: 8px; border: 1px solid rgba(248,113,113,0.2); }

  /* ══ CHAT LIST PANEL ════════════════════════════════════════════════════════ */
  .chat-list-overlay { position: fixed; inset: 0; z-index: 50; pointer-events: none; }
  .chat-list-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,0.4); pointer-events: all; }
  .chat-list-panel {
    position: absolute; left: 268px; top: 0; bottom: 0; width: 260px;
    background: rgba(10,16,28,0.97);
    border-right: 1px solid rgba(255,255,255,0.08);
    backdrop-filter: blur(20px);
    display: flex; flex-direction: column;
    pointer-events: all;
    box-shadow: 4px 0 30px rgba(0,0,0,0.4);
  }
  .chat-list-header { padding: 16px 14px 12px; border-bottom: 1px solid rgba(255,255,255,0.07); display: flex; align-items: center; justify-content: space-between; }
  .chat-list-title { font-size: 13px; font-weight: 700; color: rgba(255,255,255,0.75); }
  .chat-list-close { background: none; border: none; color: rgba(255,255,255,0.3); font-size: 18px; cursor: pointer; padding: 2px 6px; border-radius: 6px; transition: all 0.15s; line-height: 1; }
  .chat-list-close:hover { background: rgba(255,255,255,0.07); color: rgba(255,255,255,0.7); }
  .chat-list-new { margin: 10px 10px 8px; padding: 10px; border-radius: 11px; border: 1px dashed rgba(16,185,129,0.24); background: rgba(16,185,129,0.05); color: #34D399; font-size: 13px; font-weight: 600; font-family: inherit; cursor: pointer; width: calc(100% - 20px); transition: all 0.2s; }
  .chat-list-new:hover { background: rgba(16,185,129,0.1); border-color: rgba(16,185,129,0.42); }
  .chat-list-body { flex: 1; overflow-y: auto; padding: 6px 8px; }
  .chat-item { display: flex; align-items: center; padding: 9px 10px; border-radius: 10px; cursor: pointer; transition: all 0.15s; margin-bottom: 3px; gap: 8px; }
  .chat-item:hover { background: rgba(255,255,255,0.05); }
  .chat-item.active { background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.22); }
  .chat-item-icon { font-size: 15px; flex-shrink: 0; }
  .chat-item-body { flex: 1; min-width: 0; }
  .chat-item-title { font-size: 12px; font-weight: 500; color: rgba(255,255,255,0.75); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .chat-item-date { font-size: 10px; color: rgba(255,255,255,0.3); margin-top: 2px; }
  .chat-item-del { background: none; border: none; color: rgba(255,255,255,0.2); font-size: 14px; cursor: pointer; padding: 2px 5px; border-radius: 6px; opacity: 0; transition: all 0.15s; line-height: 1; }
  .chat-item:hover .chat-item-del { opacity: 1; }
  .chat-item-del:hover { color: #F87171; background: rgba(248,113,113,0.1); }
  .chat-list-empty { text-align: center; padding: 40px 16px; color: rgba(255,255,255,0.3); font-size: 12px; }
  .chat-list-empty-icon { font-size: 28px; margin-bottom: 10px; }

  /* User info row in sidebar */
  .user-row { padding: 8px 14px; border-top: 1px solid rgba(255,255,255,0.06); display: flex; align-items: center; gap: 9px; }
  .user-avatar { width: 28px; height: 28px; border-radius: 50%; background: linear-gradient(135deg, #A78BFA, #6D28D9); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; color: #fff; flex-shrink: 0; }
  .user-name { font-size: 11px; font-weight: 600; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .user-badge { font-size: 9px; color: rgba(255,255,255,0.3); margin-top: 1px; }
  .chat-controls { padding: 8px 10px; border-top: 1px solid rgba(255,255,255,0.06); display: flex; gap: 6px; }
  .chat-ctrl-btn { flex: 1; padding: 9px 6px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04); color: rgba(255,255,255,0.6); font-size: 11px; font-weight: 600; font-family: inherit; cursor: pointer; transition: all 0.18s; display: flex; align-items: center; justify-content: center; gap: 5px; }
  .chat-ctrl-btn:hover { background: rgba(255,255,255,0.09); border-color: rgba(255,255,255,0.18); color: #fff; }
  .chat-ctrl-btn.primary { background: rgba(16,185,129,0.1); border-color: rgba(16,185,129,0.25); color: #34D399; }
  .chat-ctrl-btn.primary:hover { background: rgba(16,185,129,0.18); border-color: rgba(16,185,129,0.34); }

  /* ══ ILYONAI DESIGN OVERRIDES ═════════════════════════════════════════════ */
  :root {
    --ily-bg: hsl(222 47% 4%);
    --ily-bg-soft: hsl(223 40% 7%);
    --ily-card: hsla(222, 47%, 7%, 0.78);
    --ily-card-strong: hsla(222, 47%, 7%, 0.92);
    --ily-muted-surface: hsla(217, 33%, 17%, 0.55);
    --ily-border: hsla(0, 0%, 100%, 0.08);
    --ily-border-strong: hsla(0, 0%, 100%, 0.14);
    --ily-text: hsl(210 40% 98%);
    --ily-muted: hsl(215 20% 65%);
    --ily-muted-soft: hsla(215, 20%, 65%, 0.72);
    --ily-accent: hsl(160 84% 39%);
    --ily-accent-strong: #10b981;
    --ily-accent-soft: #34d399;
    --ily-accent-deep: #065f46;
    --ily-ai: #a78bfa;
    --ily-ai-blue: #60a5fa;
    --ily-danger: #f87171;
    --ily-warn: #fbbf24;
    --ily-shadow: 0 18px 60px rgba(0, 0, 0, 0.35);
  }

  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background:
      radial-gradient(circle at top left, rgba(16,185,129,0.13), transparent 28%),
      radial-gradient(circle at 80% 18%, rgba(96,165,250,0.08), transparent 24%),
      radial-gradient(circle at 50% 100%, rgba(167,139,250,0.08), transparent 26%),
      var(--ily-bg);
    color: var(--ily-text);
  }

  .bg-canvas::after {
    content: '';
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(rgba(255,255,255,0.018) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,0.018) 1px, transparent 1px);
    background-size: 64px 64px;
    mask-image: radial-gradient(circle at center, rgba(0,0,0,0.4), transparent 78%);
  }

  .blob-1 { background: radial-gradient(circle, rgba(16,185,129,0.16) 0%, transparent 70%); }
  .blob-2 { background: radial-gradient(circle, rgba(96,165,250,0.08) 0%, transparent 70%); }
  .blob-3 { background: radial-gradient(circle, rgba(167,139,250,0.10) 0%, transparent 70%); }
  .blob-4 { background: radial-gradient(circle, rgba(52,211,153,0.08) 0%, transparent 70%); }

  .intro-screen { background: var(--ily-bg); }
  .intro-nav,
  .tabbar,
  .input-area,
  .quick-bar,
  .sidebar,
  .auth-card,
  .chat-list-panel,
  .reasoning-live,
  .typing-bubble,
  .wallet-card,
  .market-card,
  .action-card,
  .feature-card,
  .plat-stat,
  .portfolio-table,
  .stat-card,
  .balance-card,
  .sim-preview,
  .net-pill,
  .token-row,
  .cap-card,
  .intro-feat-card,
  .intro-step,
  .intro-partners-row,
  .intro-stat-item,
  .cta-hero,
  .portfolio-empty,
  .tip-card {
    backdrop-filter: blur(22px) saturate(1.1);
  }

  .intro-nav,
  .sidebar,
  .tabbar,
  .quick-bar,
  .input-area,
  .chat-list-panel { background: rgba(8, 15, 28, 0.72); }

  .intro-nav,
  .sidebar,
  .tabbar,
  .input-area,
  .quick-bar,
  .chat-list-panel,
  .portfolio-table,
  .market-card,
  .action-card,
  .feature-card,
  .plat-stat,
  .wallet-card,
  .net-pill,
  .token-row,
  .cap-card,
  .balance-card,
  .sim-preview,
  .stat-card,
  .portfolio-empty,
  .tip-card,
  .intro-feat-card,
  .intro-step,
  .intro-partners-row,
  .cta-hero,
  .intro-stats-row,
  .auth-card {
    border-color: var(--ily-border);
    box-shadow: var(--ily-shadow), inset 0 1px 0 rgba(255,255,255,0.03);
  }

  .logo-mark,
  .intro-nav-mark,
  .auth-logo-mark {
    box-shadow: 0 0 26px rgba(16,185,129,0.22);
  }

  .intro-nav-badge,
  .net-badge,
  .greenfield-badge,
  .intro-hero-eyebrow {
    background: rgba(16,185,129,0.10);
    border-color: rgba(16,185,129,0.28);
    color: var(--ily-accent-soft);
  }

  .intro-nav-enter,
  .intro-btn-primary,
  .cta-hero-btn,
  .portfolio-empty-btn,
  .auth-btn,
  .send-btn.active,
  .connect-btn,
  .cta-btn {
    background: linear-gradient(135deg, var(--ily-accent-strong), var(--ily-accent-soft));
    color: #02110c;
    box-shadow: 0 10px 30px rgba(16,185,129,0.24);
    border: none;
  }

  .connect-btn:hover,
  .intro-btn-primary:hover,
  .intro-nav-enter:hover,
  .cta-hero-btn:hover,
  .portfolio-empty-btn:hover,
  .auth-btn:hover:not(:disabled),
  .cta-btn:hover,
  .send-btn.active:hover {
    box-shadow: 0 14px 34px rgba(16,185,129,0.28);
  }

  .intro-btn-secondary,
  .chat-ctrl-btn,
  .chat-list-new,
  .quick-chip,
  .about-btn,
  .token-select-btn,
  .swap-arrow-btn {
    background: rgba(15, 23, 42, 0.72);
    border-color: var(--ily-border);
    color: var(--ily-muted-soft);
  }

  .chat-ctrl-btn.primary,
  .chat-list-new,
  .tab-btn.active,
  .section-link:hover,
  .about-btn:hover,
  .quick-chip:hover,
  .reasoning-step.step-conclude .reasoning-step-label,
  .tip-title,
  .sim-title {
    color: var(--ily-accent-soft);
  }

  .chat-ctrl-btn.primary,
  .chat-list-new:hover,
  .quick-chip:hover,
  .tab-btn::after,
  .msg-input:focus,
  .cap-card:hover,
  .action-card:hover,
  .intro-feat-card:hover,
  .cta-hero,
  .wallet-card,
  .portfolio-empty,
  .tip-card,
  .chat-item.active {
    border-color: rgba(16,185,129,0.24);
  }

  .sidebar-logo:hover,
  .cap-card:hover,
  .action-card:hover,
  .intro-feat-card:hover,
  .chat-item.active,
  .wallet-card,
  .cta-hero,
  .tip-card {
    background: linear-gradient(135deg, rgba(16,185,129,0.10), rgba(15,23,42,0.72));
  }

  .intro-hero-dot,
  .tab-badge,
  .status-dot.pending { background: var(--ily-accent-strong); }

  .intro-hero-headline .line2,
  .intro-stat-val,
  .intro-section-tag,
  .plat-stat-val.gold,
  .logo-sub strong {
    background: linear-gradient(135deg, var(--ily-accent-soft), var(--ily-accent-strong));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    color: transparent;
  }

  .plat-stat-val.green,
  .ticker-chg.pos,
  .change-pos,
  .market-card-chg.pos,
  .sim-token.to .sim-token-value,
  .sim-meta-value,
  .balance-token-amount,
  .balance-total-value { color: var(--ily-accent-soft); }

  .plat-stat-val.purple,
  .reasoning-toggle,
  .reasoning-live-title,
  .step-think .reasoning-step-label,
  .reasoning-live-step.active .reasoning-live-step-dot,
  .greenfield-badge { color: #c4b5fd; }

  .msg-avatar.user,
  .msg-bubble.user {
    background: linear-gradient(135deg, rgba(16,185,129,0.16), rgba(6,95,70,0.10));
    border-color: rgba(16,185,129,0.28);
    color: var(--ily-accent-soft);
  }

  .msg-avatar.assistant {
    background: linear-gradient(135deg, rgba(139,92,246,0.18), rgba(59,130,246,0.14));
    border-color: rgba(139,92,246,0.28);
  }

  .msg-bubble.assistant,
  .typing-bubble,
  .reasoning-step,
  .sim-token,
  .sim-meta-item,
  .balance-token-list,
  .balance-total-footer,
  .auth-btn.secondary,
  .chat-item:hover,
  .token-row:hover {
    background: rgba(15, 23, 42, 0.62);
    border-color: var(--ily-border);
  }

  .reasoning-toggle,
  .reasoning-live {
    background: rgba(139,92,246,0.08);
    border-color: rgba(139,92,246,0.22);
  }

  .sim-preview {
    background: linear-gradient(135deg, rgba(16,185,129,0.09), rgba(15,23,42,0.86));
    border-color: rgba(16,185,129,0.24);
  }

  .balance-card {
    background: linear-gradient(135deg, rgba(59,130,246,0.07), rgba(16,185,129,0.06));
    border-color: rgba(96,165,250,0.18);
  }

  .tip-card,
  .portfolio-empty,
  .cta-hero {
    background: linear-gradient(135deg, rgba(16,185,129,0.08), rgba(15,23,42,0.84));
  }

  .table-head,
  .wallet-label,
  .section-label,
  .balance-total-label,
  .balance-total-estimate,
  .sim-meta-label,
  .sim-token-label,
  .intro-step-num,
  .intro-footer,
  .token-net,
  .market-card-name,
  .page-sub,
  .dash-sub,
  .intro-section-sub,
  .intro-hero-sub,
  .input-hint,
  .chat-item-date,
  .logo-sub,
  .wallet-address,
  .msg-ts {
    color: var(--ily-muted);
  }

  .wallet-address,
  .token-amt,
  .market-card-price,
  .sim-meta-value,
  .balance-token-amount,
  .balance-total-value,
  .msg-ts,
  .user-badge,
  .table-cell {
    font-family: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
    font-variant-numeric: tabular-nums;
  }

  .msg-input,
  .auth-input {
    background: rgba(15, 23, 42, 0.62);
    border-color: var(--ily-border);
    color: var(--ily-text);
  }

  .msg-input::placeholder,
  .auth-input::placeholder { color: rgba(148, 163, 184, 0.42); }

  .auth-card {
    background: rgba(9, 15, 28, 0.92);
    border-color: rgba(16,185,129,0.16);
  }

  .auth-btn.secondary {
    color: var(--ily-text);
  }

  .chat-list-panel { box-shadow: 20px 0 60px rgba(0, 0, 0, 0.4); }

  /* ══ SENTINEL-STYLE APP SHELL ═══════════════════════════════════════════ */
  .app {
    position: relative;
    z-index: 1;
    display: flex;
    height: 100vh;
    background:
      radial-gradient(circle at 18% 12%, rgba(16,185,129,0.10), transparent 26%),
      radial-gradient(circle at 72% 18%, rgba(16,185,129,0.08), transparent 28%),
      linear-gradient(180deg, rgba(4,10,19,0.98), rgba(4,10,19,0.98));
  }

  .sidebar {
    width: 244px;
    background: rgba(4, 10, 19, 0.96);
    border-right: 1px solid rgba(255,255,255,0.07);
    padding: 14px 12px 12px;
    gap: 14px;
  }

  .sidebar-logo {
    padding: 10px 8px 18px;
    border-bottom: none;
    gap: 12px;
  }

  .logo-text {
    font-size: 14px;
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  .logo-sub {
    font-size: 11px;
    color: rgba(148,163,184,0.75);
    margin-top: 2px;
  }

  .sidebar-nav {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 2px 0 0;
    max-height: 280px;
    overflow-y: auto;
  }

  .sidebar-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .sidebar-group-title {
    padding: 0 8px 6px;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: rgba(148,163,184,0.56);
    font-weight: 700;
  }

  .sidebar-nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    background: transparent;
    border: 1px solid transparent;
    color: rgba(226,232,240,0.78);
    border-radius: 12px;
    padding: 10px 12px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.18s ease;
    font-family: inherit;
    text-align: left;
  }

  .sidebar-nav-item:hover {
    background: rgba(15,23,42,0.56);
    border-color: rgba(255,255,255,0.05);
  }

  .sidebar-nav-item.active {
    background: rgba(16,185,129,0.13);
    border-color: rgba(16,185,129,0.18);
    color: #34D399;
  }

  .sidebar-nav-item.disabled {
    opacity: 0.92;
  }

  .sidebar-nav-icon {
    width: 16px;
    text-align: center;
    color: rgba(148,163,184,0.84);
    font-size: 14px;
    flex-shrink: 0;
  }

  .sidebar-nav-item.active .sidebar-nav-icon {
    color: #34D399;
  }

  .wallet-section,
  .tokens-section,
  .greenfield-row,
  .user-row,
  .chat-controls {
    display: block;
  }

  .wallet-section {
    padding: 8px 8px 10px;
  }

  .tokens-section {
    padding: 0 8px;
    flex: 1;
    overflow-y: auto;
  }

  .token-row {
    border-radius: 14px;
    background: rgba(10,15,24,0.84);
  }

  .greenfield-row {
    margin: 6px 8px 0;
    border-top: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    background: rgba(10,15,24,0.76);
  }

  .user-row,
  .chat-controls {
    margin: 0 8px;
  }

  .chat-controls {
    display: flex;
    gap: 8px;
  }

  .sidebar-footer {
    border-top: 1px solid rgba(255,255,255,0.06);
    padding: 12px 8px 0;
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .status-row {
    justify-content: flex-start;
  }

  .footer-right {
    justify-content: space-between;
  }

  .main {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: linear-gradient(180deg, rgba(3,8,17,0.96), rgba(3,8,17,0.98));
  }

  .ticker-bar {
    display: flex;
    height: 42px;
    background: rgba(4,10,19,0.96);
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }

  .ticker-item {
    font-size: 12px;
    gap: 9px;
    color: rgba(226,232,240,0.7);
  }

  .tabbar {
    display: none;
  }

  .tab-btn {
    height: 54px;
    padding: 0 20px;
    font-size: 14px;
  }

  .tab-panel {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .content-canvas {
    flex: 1;
    width: 100%;
    padding: 14px 22px 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .top-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    border-radius: 14px;
    border: 1px solid rgba(16,185,129,0.18);
    background: rgba(7, 40, 35, 0.46);
    padding: 10px 16px;
    color: #d1fae5;
    margin-bottom: 14px;
  }
  .public-testing-banner {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    border-radius: 12px;
    border: 1px solid rgba(245, 158, 11, 0.35);
    background: rgba(120, 53, 15, 0.42);
    padding: 8px 14px;
    color: #fde68a;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.02em;
    margin-bottom: 10px;
  }
  .public-testing-banner a {
    color: #fbbf24;
    font-weight: 800;
    text-decoration: underline;
  }
  .public-testing-banner a:hover { color: #fde68a; }

  .top-banner-label {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 12px;
    font-weight: 600;
  }

  .top-banner-chip {
    padding: 5px 12px;
    border-radius: 999px;
    background: rgba(16,185,129,0.14);
    border: 1px solid rgba(16,185,129,0.16);
    color: #86efac;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .dash,
  .page {
    padding: 0;
    overflow: visible;
  }

  .overview-shell {
    display: flex;
    flex-direction: column;
    gap: 26px;
  }

  .overview-hero {
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
    gap: 42px;
    align-items: start;
    min-height: 520px;
    padding: 24px 8px 8px;
    position: relative;
  }

  .overview-hero::before {
    content: '';
    position: absolute;
    inset: -40px 18% 0 0;
    background: radial-gradient(circle, rgba(16,185,129,0.12), transparent 58%);
    pointer-events: none;
  }

  .hero-copy,
  .hero-preview {
    position: relative;
    z-index: 1;
  }

  .hero-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 14px;
    border-radius: 999px;
    border: 1px solid rgba(16,185,129,0.18);
    background: rgba(7,40,35,0.46);
    color: #86efac;
    font-size: 12px;
    font-weight: 600;
    margin-bottom: 22px;
  }

  .hero-heading {
    font-size: clamp(56px, 7vw, 78px);
    line-height: 0.92;
    font-weight: 800;
    letter-spacing: -0.06em;
    margin-bottom: 24px;
    color: #ffffff;
  }

  .hero-heading .accent {
    display: block;
    color: #25d59f;
  }

  .hero-sub {
    max-width: 560px;
    color: #8fa4c3;
    font-size: 18px;
    line-height: 1.55;
    margin-bottom: 34px;
  }

  .hero-search {
    display: flex;
    align-items: center;
    gap: 14px;
    border: 1px solid rgba(255,255,255,0.08);
    background: rgba(10,15,24,0.76);
    border-radius: 20px;
    padding: 10px 10px 10px 18px;
    max-width: 580px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
  }

  .hero-search input {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: #dbe7ff;
    font-size: 15px;
    font-family: 'JetBrains Mono', monospace;
  }

  .hero-search input::placeholder {
    color: rgba(148,163,184,0.78);
  }

  .hero-search-btn {
    padding: 14px 24px;
    border: none;
    border-radius: 14px;
    background: linear-gradient(135deg, #10b981, #25d59f);
    color: #04130d;
    font-size: 14px;
    font-weight: 800;
    cursor: pointer;
    transition: transform 0.16s ease, box-shadow 0.16s ease;
    box-shadow: 0 14px 28px rgba(16,185,129,0.16);
  }

  .hero-search-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 18px 36px rgba(16,185,129,0.2);
  }

  .hero-chain-row {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin: 20px 0 28px;
    align-items: center;
  }

  .hero-chain-label,
  .hero-footer-note {
    color: rgba(148,163,184,0.72);
    font-size: 12px;
  }

  .hero-chain-pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 6px 12px;
    border-radius: 999px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    color: #d1d9eb;
    font-size: 12px;
    font-weight: 600;
  }

  .hero-chain-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .hero-footer-row {
    display: flex;
    flex-wrap: wrap;
    gap: 28px;
    margin-top: 16px;
  }

  .hero-footer-item {
    display: flex;
    align-items: center;
    gap: 9px;
    color: #9cb4d8;
    font-size: 12px;
  }

  .hero-footer-item .check {
    color: #34D399;
    font-weight: 700;
  }

  .preview-card {
    border-radius: 22px;
    border: 1px solid rgba(255,255,255,0.08);
    background: rgba(10,15,24,0.88);
    padding: 22px 22px 20px;
    box-shadow: 0 24px 60px rgba(0,0,0,0.22);
  }

  .preview-card-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 18px;
  }

  .preview-card-title {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .preview-avatar {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: linear-gradient(135deg,#10b981,#34d399);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #04130d;
    font-size: 24px;
    font-weight: 800;
  }

  .preview-card-name {
    font-size: 18px;
    font-weight: 700;
    color: #f8fafc;
  }

  .preview-card-sub {
    font-size: 14px;
    color: #8fa4c3;
    margin-top: 2px;
  }

  .preview-score {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
  }

  .preview-score-badge {
    border-radius: 999px;
    border: 1px solid rgba(16,185,129,0.18);
    background: rgba(7,40,35,0.48);
    color: #6ee7b7;
    padding: 5px 10px;
    font-size: 11px;
  }

  .preview-score-value {
    color: #34D399;
    font-size: 18px;
    font-weight: 800;
  }

  .preview-ring-wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 12px 0 22px;
  }

  .preview-ring {
    width: 118px;
    height: 118px;
    border-radius: 50%;
    border: 7px solid rgba(16,185,129,0.18);
    border-top-color: #24d6a0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #34D399;
    font-weight: 800;
    box-shadow: inset 0 0 24px rgba(16,185,129,0.08);
  }

  .preview-ring small {
    color: rgba(226,232,240,0.72);
    font-size: 12px;
    margin-top: 4px;
  }

  .preview-checks {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .preview-check-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-radius: 14px;
    padding: 12px 14px;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.06);
    color: #f8fafc;
    font-size: 14px;
  }

  .preview-check-item.success {
    background: rgba(7,40,35,0.54);
    border-color: rgba(16,185,129,0.18);
  }

  .preview-check-item.warn {
    background: rgba(60,47,12,0.34);
    border-color: rgba(251,191,36,0.18);
  }

  .preview-check-state.success { color: #34D399; }
  .preview-check-state.warn { color: #FBBF24; }

  .dashboard-lower {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 18px;
  }

  .dashboard-lower .action-card,
  .dashboard-lower .feature-card,
  .dashboard-lower .market-card,
  .dashboard-lower .plat-stat {
    min-height: 170px;
    border-radius: 20px;
    background: rgba(7,13,24,0.68);
    border: 1px solid rgba(16,185,129,0.12);
  }

  .chat-wrap {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .chat-shell {
    display: contents;
  }

  .chat-shell-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 4px 0 14px;
    border-bottom: none;
  }

  .chat-shell-title {
    font-size: 14px;
    color: #f8fafc;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .chat-shell-actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .chat-shell-btn {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.08);
    background: rgba(255,255,255,0.03);
    color: #cbd5e1;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }

  .chat-shell-btn.primary {
    background: rgba(16,185,129,0.12);
    border-color: rgba(16,185,129,0.18);
    color: #6ee7b7;
  }

  .messages {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 12px 8px 8px;
    gap: 18px;
    background: linear-gradient(180deg, rgba(6,15,22,0.24), rgba(6,11,20,0.18));
  }

  .msg-body {
    max-width: 700px;
  }

  .msg-bubble.assistant {
    background: rgba(16,23,35,0.96);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px;
    padding: 14px 16px;
  }

  .msg-bubble.user {
    background: rgba(7,40,35,0.58);
    border: 1px solid rgba(16,185,129,0.22);
    border-radius: 18px;
  }

  .msg-row.user .msg-body {
    max-width: 560px;
  }

  .msg-avatar {
    width: 32px;
    height: 32px;
    background: rgba(91,33,182,0.2);
  }

  .msg-avatar.user {
    background: rgba(7,40,35,0.58);
    color: #d1fae5;
  }

  .reasoning-toggle {
    border-radius: 14px;
    padding: 10px 14px;
    background: rgba(30,24,53,0.72);
    border: 1px solid rgba(139,92,246,0.22);
  }

  .reasoning-steps-list {
    gap: 8px;
    padding: 10px 4px 0;
  }

  .reasoning-step {
    background: rgba(13,17,29,0.86);
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.05);
  }

  .sim-preview,
  .balance-card {
    border-radius: 18px;
    background: rgba(13,17,29,0.92);
    border: 1px solid rgba(139,92,246,0.2);
    box-shadow: none;
    padding: 16px;
  }

  .sim-title,
  .balance-card-title {
    color: #d8b4fe;
    margin-bottom: 14px;
  }

  .sim-token,
  .sim-meta-item,
  .balance-token-list,
  .balance-total-footer {
    background: rgba(7,13,24,0.72);
    border-color: rgba(255,255,255,0.06);
  }

  .quick-bar {
    padding: 12px 18px;
    background: rgba(8,13,22,0.86);
    border-top: 1px solid rgba(255,255,255,0.06);
    gap: 10px;
    justify-content: flex-start;
    flex-shrink: 0;
  }

  .quick-chip {
    padding: 10px 14px;
    font-size: 13px;
    border-radius: 999px;
    background: rgba(9,15,24,0.88);
    border-color: rgba(255,255,255,0.08);
  }

  .input-area {
    padding: 14px 18px 18px;
    background: rgba(8,13,22,0.94);
    flex-shrink: 0;
  }

  .msg-input {
    min-height: 60px;
    border-radius: 18px;
    padding: 16px 18px;
    font-size: 15px;
  }

  .send-btn {
    width: 52px;
    height: 52px;
    border-radius: 16px;
    align-self: center;
  }

  .page-shell {
    max-width: 1160px;
    margin: 0 auto;
    width: 100%;
    padding: 20px 22px 40px;
  }

  .swap-grid {
    display: grid !important;
    grid-template-columns: minmax(0, 1.15fr) minmax(280px, 0.85fr);
    gap: 18px;
    align-items: start;
    width: 100%;
  }

  @media (max-width: 900px) {
    .swap-grid {
      grid-template-columns: 1fr;
    }
  }

  .stats-grid,
  .portfolio-table,
  .tip-card,
  .swap-shell-card,
  .swap-side-card {
    border-radius: 20px;
  }

  @media (max-width: 1180px) {
    .overview-hero {
      grid-template-columns: 1fr;
    }
    .dashboard-lower {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 900px) {
    .sidebar {
      width: 210px;
    }
    .content-canvas,
    .page-shell {
      padding: 16px;
    }
    .dashboard-lower,
    .stats-grid,
    .market-grid,
    .action-grid,
    .feature-grid {
      grid-template-columns: 1fr;
    }
    .intro-partners-grid {
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 12px;
    }
    .intro-partner {
      padding: 16px 12px;
      min-height: 120px;
    }
    .intro-partner-logo {
      width: 36px;
      height: 36px;
    }
    .intro-partner-name {
      font-size: 12px;
    }
  }
`;


// ── Sub-components ────────────────────────────────────────────────────────────

const STEP_ICONS: Record<string, string> = {
  think: "🧠",
  tool: "⚙️",
  result: "✅",
  conclude: "💡",
};

interface ReasoningAccordionProps {
  steps: ReasoningStep[];
  isOpen: boolean;
  onToggle: () => void;
}

function ReasoningAccordion({ steps, isOpen, onToggle }: ReasoningAccordionProps) {
  return (
    <div className="reasoning-wrap rounded-3xl border border-cyan-300/20 bg-[#07111f]/85 p-3 shadow-[0_20px_80px_rgba(34,211,238,0.10)]" data-testid="reasoning-accordion">
      <button className="reasoning-toggle w-full" onClick={onToggle}>
        <span className="reasoning-toggle-icon">✦</span>
        <span className="reasoning-toggle-text">Sentinel Live Reasoning — {steps.length} steps</span>
        <span className="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.16em] text-emerald-200">streamed</span>
        <span className={`reasoning-toggle-caret${isOpen ? " open" : ""}`}>▲</span>
      </button>
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: "easeInOut" }}
            style={{ overflow: "hidden" }}
          >
            <div className="reasoning-steps-list">
              {steps.map((step, i) => (
                <motion.div
                  key={step.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04, duration: 0.18 }}
                  className={`reasoning-step step-${step.type}`}
                >
                  <span className="reasoning-step-icon font-mono text-cyan-200">{String(i + 1).padStart(2, "0")}</span>
                  <div>
                    <div className="reasoning-step-label">{STEP_ICONS[step.type]} {step.label}</div>
                    {step.detail && <div className="reasoning-step-detail">{step.detail}</div>}
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

interface SimulationPreviewProps {
  preview: SwapPreview;
  fromAddress?: string | null;
  solanaAddress?: string | null;
  walletType?: "metamask" | "phantom" | null;
}

async function waitForReceipt(
  eth: ReturnType<typeof resolveMetaMaskProvider>,
  txHash: string,
  timeoutMs = 120000,
) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const receipt = await eth.request({ method: "eth_getTransactionReceipt", params: [txHash] });
    if (receipt) return receipt;
    await new Promise(resolve => window.setTimeout(resolve, 2000));
  }
  throw new Error("Timed out waiting for transaction confirmation. Please check your wallet activity.");
}

function SimulationPreview({ preview, fromAddress, solanaAddress, walletType }: SimulationPreviewProps) {
  const [isPending, setIsPending] = useState(false);
  const [txHash, setTxHash] = useState<string | null>(null);
  const [txError, setTxError] = useState<string | null>(null);
  const [bridgeStatus, setBridgeStatus] = useState<string | null>(null);

  useEffect(() => {
    if (!preview.isBridge || !preview.orderId || !txHash) return;
    let cancelled = false;
    const terminal = new Set(["Fulfilled", "OrderCancelled", "ClaimedUnlock", "ClaimedOrderCancel"]);

    const poll = async () => {
      for (let attempt = 0; attempt < 20; attempt += 1) {
        try {
          const status = await fetchBridgeOrderStatus(preview.orderId!);
          if (cancelled) return;
          setBridgeStatus(status);
          if (terminal.has(status)) return;
        } catch (err) {
          if (!cancelled) {
            console.warn("[bridge-status]", err);
          }
        }
        await new Promise(resolve => window.setTimeout(resolve, 4000));
      }
    };

    setBridgeStatus("Submitted");
    void poll();
    return () => {
      cancelled = true;
    };
  }, [preview.isBridge, preview.orderId, txHash]);

  // ── Solana swap via Phantom ────────────────────────────────────────────────
  const executeSolanaSwap = async () => {
    if (!preview.swapTransaction) return;
    setTxError(null);
    setIsPending(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const sol = (window as any)?.phantom?.solana ?? (window as any).solana;
      if (!sol?.isPhantom) throw new Error("Phantom wallet not found");

      const { VersionedTransaction } = await import("@solana/web3.js");
      const txBytes = Uint8Array.from(atob(preview.swapTransaction), c => c.charCodeAt(0));
      const tx = VersionedTransaction.deserialize(txBytes);

      const { signature } = await sol.signAndSendTransaction(tx);
      setTxHash(signature);
    } catch (e: unknown) {
      const err = e as { message?: string };
      setTxError(err?.message ?? "Transaction rejected");
      console.error("[executeSolanaSwap] Phantom error:", e);
    } finally {
      setIsPending(false);
    }
  };

  const executeSwap = async () => {
    if (!preview.rawTx) return;
    setTxError(null);
    setIsPending(true);
    try {
      let eth: ReturnType<typeof resolveMetaMaskProvider> | ReturnType<typeof resolvePhantomEvmProvider> | null = null;
      try {
        eth = walletType === "phantom" ? resolvePhantomEvmProvider() : resolveMetaMaskProvider();
      } catch {
        eth = null;
      }
      if (!eth) throw new Error(walletType === "phantom" ? "Phantom EVM wallet not found" : "MetaMask not found");

      const requiredChainId: number | undefined = preview.rawTx.chain_id ?? preview.approvalTx?.chain_id;
      if (requiredChainId) {
        const currentChainHex = await eth.request({ method: "eth_chainId" }) as string;
        const currentChainId = parseInt(currentChainHex, 16);
        if (currentChainId !== requiredChainId) {
          const requiredHex = "0x" + requiredChainId.toString(16);
          try {
            await eth.request({ method: "wallet_switchEthereumChain", params: [{ chainId: requiredHex }] });
          } catch (switchErr: unknown) {
            const msg = (switchErr as { message?: string }).message ?? "Network switch rejected";
            setTxError(`Please switch to the correct network first. ${msg}`);
            setIsPending(false);
            return;
          }
        }
      }

      if (preview.approvalTx) {
        const { chain_id: _approvalChain, ...approvalFields } = preview.approvalTx;
        const approvalTx = fromAddress ? { ...approvalFields, from: fromAddress } : approvalFields;
        const approvalHash = await eth.request({ method: "eth_sendTransaction", params: [approvalTx] }) as string;
        await waitForReceipt(eth, approvalHash);
      }

      const { chain_id: _cid, ...txFields } = preview.rawTx;
      const tx = fromAddress ? { ...txFields, from: fromAddress } : txFields;
      const hash = await eth.request({ method: "eth_sendTransaction", params: [tx] }) as string;
      setTxHash(hash);
    } catch (e: unknown) {
      const err = e as { message?: string; reason?: string; data?: { message?: string } };
      const msg = err?.data?.message ?? err?.reason ?? err?.message ?? "Transaction rejected";
      console.error("[executeSwap] EVM wallet error:", e);
      setTxError(msg);
    } finally {
      setIsPending(false);
    }
  };

  const actionLabel = preview.actionType === "stake"
    ? "Stake"
    : preview.actionType === "add_liquidity"
      ? "Add Liquidity"
      : preview.isBridge
        ? "Bridge"
        : "Swap";

  const buttonLabel = preview.isTransfer
    ? `📤 Send in ${walletType === "phantom" ? "Phantom" : "MetaMask"}`
    : preview.isBridge
      ? (preview.approvalTx ? `🌉 Approve & Bridge in ${walletType === "phantom" ? "Phantom" : "MetaMask"}` : `🌉 Bridge in ${walletType === "phantom" ? "Phantom" : "MetaMask"}`)
      : preview.approvalTx
        ? `✅ Approve & ${actionLabel} in ${walletType === "phantom" ? "Phantom" : "MetaMask"}`
        : `🚀 ${actionLabel} in ${walletType === "phantom" ? "Phantom" : "MetaMask"}`;

  return (
    <motion.div
      className="sim-preview"
      variants={scaleIn}
      initial="hidden"
      animate="show"
    >
      {preview.isTransfer ? (
        <>
          <div className="sim-title"><span>📤</span> Transfer Preview</div>
          <div className="sim-meta">
            <div className="sim-meta-item">
                <span className="sim-meta-label">Token</span>
                <span className="sim-meta-value" style={{ color: "#34D399" }}>{preview.fromToken}</span>
              </div>
            {preview.fromAmount && preview.fromAmount !== "—" && (
              <div className="sim-meta-item">
                <span className="sim-meta-label">Amount</span>
                <span className="sim-meta-value" style={{ color: "#34D399", fontWeight: 600 }}>
                  {preview.fromAmount} {preview.fromToken}
                </span>
              </div>
            )}
            {preview.transferChainId && (
              <div className="sim-meta-item">
                <span className="sim-meta-label">Network</span>
                <span className="sim-meta-value" style={{ color: "#A78BFA" }}>
                  {CHAIN_CONFIG[preview.transferChainId]?.name ?? `Chain ${preview.transferChainId}`}
                </span>
              </div>
            )}
            <div className="sim-meta-item">
              <span className="sim-meta-label">To</span>
                <span className="sim-meta-value" style={{ color: "#60A5FA", fontSize: 11, wordBreak: "break-all" }}>
                  {preview.transferTo}
                </span>
            </div>
          </div>
        </>
      ) : preview.isBridge ? (
        <>
          <div className="sim-title"><span>🌉</span> Bridge Preview</div>
          <div className="sim-row">
            <div className="sim-token from">
              <span className="sim-token-icon">⬡</span>
              <div>
                <div className="sim-token-label">From</div>
                <div className="sim-token-value">{preview.fromAmount} {preview.fromToken}</div>
                {preview.sourceChainLabel && <div className="sim-token-label">{preview.sourceChainLabel}</div>}
              </div>
            </div>
            <div className="sim-arrow">→</div>
            <div className="sim-token to">
              <span className="sim-token-icon">◎</span>
              <div>
                <div className="sim-token-label">To</div>
                <div className="sim-token-value">~{preview.toAmount} {preview.toToken}</div>
                {preview.destinationChainLabel && <div className="sim-token-label">{preview.destinationChainLabel}</div>}
              </div>
            </div>
          </div>
          <div className="sim-meta">
            {preview.bridgeRequestedAmount && (
              <div className="sim-meta-item">
                <span className="sim-meta-label">Requested</span>
                <span className="sim-meta-value">{preview.bridgeRequestedAmount} {preview.fromToken}</span>
              </div>
            )}
            <div className="sim-meta-item">
              <span className="sim-meta-label">Route</span>
              <span className="sim-meta-value" style={{ color: "#C4B5FD" }}>{preview.route}</span>
            </div>
            {preview.sourceExecutionSummary && (
              <div className="sim-meta-item">
                <span className="sim-meta-label">Source Execution</span>
                <span className="sim-meta-value" style={{ fontSize: 11, lineHeight: 1.4 }}>{preview.sourceExecutionSummary}</span>
              </div>
            )}
            <div className="sim-meta-item">
              <span className="sim-meta-label">Est. Time</span>
              <span className="sim-meta-value">{preview.estimatedTime ?? "—"}</span>
            </div>
            <div className="sim-meta-item">
              <span className="sim-meta-label">Fee</span>
              <span className="sim-meta-value" style={{ color: "#FBBF24" }}>{preview.fee}</span>
            </div>
            {bridgeStatus && (
              <div className="sim-meta-item">
                <span className="sim-meta-label">Bridge Status</span>
                <span className="sim-meta-value" style={{ color: bridgeStatus === "Fulfilled" ? "#34D399" : "#A78BFA" }}>{bridgeStatus}</span>
              </div>
            )}
            {preview.orderId && (
              <div className="sim-meta-item">
                <span className="sim-meta-label">Order ID</span>
                <span className="sim-meta-value" style={{ fontSize: 11, wordBreak: "break-all" }}>{preview.orderId}</span>
              </div>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="sim-title"><span>⚡</span> {actionLabel} Preview</div>
          <div className="sim-row">
            <div className="sim-token from">
              <span className="sim-token-icon">⬡</span>
              <div>
                <div className="sim-token-label">You Pay</div>
                <div className="sim-token-value">{preview.fromAmount} {preview.fromToken}</div>
              </div>
            </div>
            <div className="sim-arrow">→</div>
            <div className="sim-token to">
              <span className="sim-token-icon">₮</span>
              <div>
                <div className="sim-token-label">You Receive</div>
                <div className="sim-token-value">~{preview.toAmount} {preview.toToken}</div>
              </div>
            </div>
          </div>
          <div className="sim-meta">
            <div className="sim-meta-item">
              <span className="sim-meta-label">Route</span>
              <span className="sim-meta-value" style={{ color: "#C4B5FD" }}>{preview.route}</span>
            </div>
            <div className="sim-meta-item">
              <span className="sim-meta-label">Price Impact</span>
              <span className="sim-meta-value">{preview.priceImpact}</span>
            </div>
            <div className="sim-meta-item">
              <span className="sim-meta-label">Fee</span>
              <span className="sim-meta-value" style={{ color: "#FBBF24" }}>{preview.fee}</span>
            </div>
          </div>
        </>
      )}

      {preview.warnings && preview.warnings.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 12 }}>
          {preview.warnings.map((warning, index) => (
            <div
              key={index}
              style={{ padding: "8px 12px", background: "rgba(251,191,36,0.10)", border: "1px solid rgba(251,191,36,0.24)", borderRadius: 10, color: "#FCD34D", fontSize: 12 }}
            >
              ⚠️ {warning}
            </div>
          ))}
        </div>
      )}

      {preview.isSolanaSwap && preview.swapTransaction && !txHash && (
        <button
          className="cta-btn"
          onClick={executeSolanaSwap}
          disabled={isPending || !solanaAddress}
          style={{ marginTop: 14, width: "100%", opacity: isPending ? 0.7 : 1, background: "linear-gradient(135deg,#10b981,#34d399)", color: "#03150f" }}
        >
          {isPending ? "⏳ Confirm in Phantom..." : (preview.isBridge ? "👻 Bridge in Phantom" : "👻 Swap in Phantom")}
        </button>
      )}

      {preview.rawTx && !txHash && (
        <button
          className="cta-btn"
          onClick={executeSwap}
          disabled={isPending}
          style={{ marginTop: 14, width: "100%", opacity: isPending ? 0.7 : 1 }}
        >
          {isPending ? "⏳ Confirm in wallet..." : buttonLabel}
        </button>
      )}

      {txHash && (
          <div style={{ marginTop: 12, padding: "10px 14px", background: "rgba(16,185,129,0.12)", border: "1px solid rgba(16,185,129,0.25)", borderRadius: 10 }}>
            <div style={{ color: "#34D399", fontWeight: 700, fontSize: 13, marginBottom: 4 }}>{preview.isBridge ? "✅ Bridge transaction sent" : "✅ Transaction sent"}</div>
            <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 11, wordBreak: "break-all", fontFamily: "monospace" }}>{txHash}</div>
          </div>
      )}

      {txError && (
        <div style={{ marginTop: 10, padding: "8px 12px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)", borderRadius: 8, color: "#F87171", fontSize: 12 }}>
          ❌ {txError}
        </div>
      )}
    </motion.div>
  );
}

// ── BalanceCard ───────────────────────────────────────────────────────────────
const CHAIN_ICONS: Record<string, string> = {
  "BNB Smart Chain": "⬡", Ethereum: "Ξ", Polygon: "⬟",
  Arbitrum: "🔵", Optimism: "🔴", Base: "🔷", Avalanche: "🔺",
  Solana: "◎", zkSync: "⚡", Linea: "🟣", Scroll: "📜",
};

function BalanceCard({ data }: { data: BalanceData }) {
  if (data.message && !data.balances.length) {
    return (
      <motion.div className="balance-card" variants={scaleIn} initial="hidden" animate="show">
        <div className="balance-card-title"><span>💼</span> Wallet Balances</div>
        <div style={{ color: "rgba(255,255,255,0.45)", fontSize: 13, padding: "8px 0" }}>{data.message}</div>
      </motion.div>
    );
  }

  return (
    <motion.div className="balance-card" variants={scaleIn} initial="hidden" animate="show">
      <div className="balance-card-title"><span>💼</span> Wallet Balances</div>
      {data.balances.map((chain, i) => (
        <div key={i} className="balance-chain-block">
          <div className="balance-chain-header">
            <span className="balance-chain-icon">{CHAIN_ICONS[chain.chain] ?? "🌐"}</span>
            <span className="balance-chain-name">{chain.chain}</span>
          </div>
          <div className="balance-token-list">
            {chain.native_balance > 0 && (
              <div className="balance-token-row">
                <span className="balance-token-symbol">{chain.native_symbol}</span>
                <span className="balance-token-amount">{chain.native_balance.toFixed(6).replace(/\.?0+$/, "")}</span>
              </div>
            )}
            {Object.values(
                chain.tokens.reduce((acc: Record<string, typeof chain.tokens[0]>, tok) => {
                  const k = tok.symbol.toUpperCase();
                  if (!acc[k]) acc[k] = tok;
                  return acc;
                }, {})
              ).map((tok, j) => (
                <div key={j} className="balance-token-row">
                  <span className="balance-token-symbol">{tok.symbol}</span>
                  <span className="balance-token-amount">{tok.balance.toFixed(6).replace(/\.?0+$/, "")}</span>
                </div>
              ))}
          </div>
        </div>
      ))}
      {(data.total_usd ?? 0) > 0 && (
        <div className="balance-total-footer">
          <span className="balance-total-label">
            Total Balance
            <span className="balance-total-estimate">estimate</span>
          </span>
          <span className="balance-total-value">≈ ${data.total_usd!.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        </div>
      )}
    </motion.div>
  );
}

// ── LiquidityPoolCard ─────────────────────────────────────────────────────────
const DEX_ICONS: Record<string, string> = {
  pancakeswap: "🥞", uniswap: "🦄", raydium: "🔷", orca: "🐋",
  sushiswap: "🍣", curve: "🌀", balancer: "⚖️", traderjoe: "🎰",
};

const CHAIN_NAMES: Record<string, string> = {
  bsc: "BNB Smart Chain", ethereum: "Ethereum", polygon: "Polygon",
  arbitrum: "Arbitrum One", optimism: "Optimism", base: "Base",
  avalanche: "Avalanche", solana: "Solana", fantom: "Fantom",
};

const CHAIN_EXPLORERS: Record<string, string> = {
  bsc:       "https://bscscan.com/address/",
  ethereum:  "https://etherscan.io/address/",
  polygon:   "https://polygonscan.com/address/",
  arbitrum:  "https://arbiscan.io/address/",
  optimism:  "https://optimistic.etherscan.io/address/",
  base:      "https://basescan.org/address/",
  avalanche: "https://snowtrace.io/address/",
  solana:    "https://solscan.io/account/",
  fantom:    "https://ftmscan.com/address/",
  cronos:    "https://cronoscan.com/address/",
  celo:      "https://celoscan.io/address/",
};

function poolExplorerUrl(chainId: string, pairAddress: string): string {
  if (!pairAddress || pairAddress === "—" || pairAddress.includes("-")) return "";
  const base = CHAIN_EXPLORERS[chainId?.toLowerCase()];
  return base ? base + pairAddress : "";
}

// DEX slug → main protocol liquidity/pool page
const DEX_PROTOCOL_URLS: Record<string, string> = {
  uniswap:      "https://app.uniswap.org/explore/pools",
  pancakeswap:  "https://pancakeswap.finance/liquidity",
  raydium:      "https://raydium.io/swap/",
  orca:         "https://www.orca.so/pools",
  meteora:      "https://app.meteora.ag/",
  sushiswap:    "https://www.sushi.com/pools",
  curve:        "https://curve.fi",
  balancer:     "https://app.balancer.fi",
  aerodrome:    "https://aerodrome.finance/pools",
  velodrome:    "https://velodrome.finance/pools",
  camelot:      "https://app.camelot.exchange/pools",
  quickswap:    "https://quickswap.exchange/#/pools",
  traderjoe:    "https://lfj.gg/pools",
  lfj:          "https://lfj.gg/pools",
  kyberswap:    "https://kyberswap.com/pools",
  thena:        "https://www.thena.fi/pools",
  gmx:          "https://app.gmx.io/#/pools",
  pendle:       "https://app.pendle.finance/trade/pools",
  aave:         "https://app.aave.com/",
  compound:     "https://app.compound.finance/",
  morpho:       "https://app.morpho.org/",
  beefy:        "https://app.beefy.com/",
  yearn:        "https://yearn.fi/vaults",
};

function poolProtocolUrl(dexId: string, chain: string, fallback: string): string {
  // Priority 1: Use backend-provided protocol_url (most accurate, includes specific pool pages)
  if (fallback && !fallback.includes("defillama")) return fallback;
  
  // Priority 2: Frontend DEX mapping (general pool hub pages)
  const d = dexId?.toLowerCase() ?? "";
  const match = Object.keys(DEX_PROTOCOL_URLS).find(k => d.includes(k));
  if (match) return DEX_PROTOCOL_URLS[match];
  
  // Priority 3: DexScreener chain page
  return `https://dexscreener.com/${chain?.toLowerCase() || ""}`;
}

function poolDefiLlamaUrl(pairAddress: string, chainId: string, defillama_url: string, url: string): string {
  // Prefer backend-provided URLs that point directly to defillama.com
  if (defillama_url && defillama_url.includes("defillama.com")) return defillama_url;
  if (url && url.includes("defillama.com")) return url;
  // Fallback: construct from pairAddress
  if (!pairAddress || pairAddress === "—") return "https://defillama.com/yields";
  // UUID pool: pairAddress IS the full pool ID
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(pairAddress))
    return `https://defillama.com/yields/pool/${pairAddress}`;
  // Native address: reconstruct as "address-chain" (DefiLlama pool ID format)
  const ch = chainId?.toLowerCase() || "";
  return ch
    ? `https://defillama.com/yields/pool/${pairAddress}-${ch}`
    : `https://defillama.com/yields/pool/${pairAddress}`;
}

function fmt$(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000)     return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
}

function LiquidityPoolCard({ data }: { data: LiquidityPoolData }) {
  const dexIcon    = DEX_ICONS[data.dexId?.toLowerCase()] ?? "💧";
  const network    = CHAIN_NAMES[data.chainId?.toLowerCase()] ?? data.chainId;
  const shortAddr  = data.pairAddress.length > 12
    ? `${data.pairAddress.slice(0, 6)}…${data.pairAddress.slice(-4)}`
    : data.pairAddress;
  const explorerUrl  = poolExplorerUrl(data.chainId, data.pairAddress);
  const defiLlamaUrl = poolDefiLlamaUrl(data.pairAddress, data.chainId, data.defillama_url ?? "", data.url ?? "");
  const protocolUrl  = poolProtocolUrl(data.dexId, data.chainId, data.protocol_url ?? "");

  return (
    <motion.div
      className="balance-card"
      variants={scaleIn} initial="hidden" animate="show"
      style={{ marginTop: 8 }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <span style={{ fontSize: 22 }}>{dexIcon}</span>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: "#fff", lineHeight: 1.2 }}>
            🌊 {data.poolSymbol ?? `${data.baseToken} / ${data.quoteToken}`}
          </div>
          <div style={{ fontSize: 11, color: "rgba(148,163,184,0.82)", marginTop: 2 }}>
            {data.dexId?.toUpperCase()} · {network}
          </div>
        </div>
      </div>

      {/* Metrics */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 14 }}>
        {[
          { label: "Liquidity",  value: fmt$(data.liquidity_usd),  color: "#34D399" },
          { label: "24h Volume", value: fmt$(data.volume_24h_usd), color: "#60A5FA" },
          { label: "APR",        value: data.apr > 0 ? `${data.apr.toFixed(2)}%` : "—", color: "#FBBF24" },
        ].map(({ label, value, color }) => (
          <div key={label} style={{
            background: "rgba(15,23,42,0.72)", borderRadius: 12,
            padding: "10px 12px", border: "1px solid rgba(255,255,255,0.07)",
          }}>
            <div style={{ fontSize: 10, color: "rgba(148,163,184,0.8)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</div>
            <div style={{ fontSize: 16, fontWeight: 700, color, fontFamily: "'JetBrains Mono', monospace" }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Pair address */}
      <div style={{
        background: "rgba(15,23,42,0.72)", borderRadius: 12, padding: "10px 12px",
        border: "1px solid rgba(255,255,255,0.06)", marginBottom: 12,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <span style={{ fontSize: 10, color: "rgba(148,163,184,0.78)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Pool Address</span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 11, color: "rgba(226,232,240,0.78)", fontFamily: "'JetBrains Mono', monospace" }}>{shortAddr}</span>
          <button
            type="button"
            onClick={(e) => {
              void copyWithFeedback(data.pairAddress, e.currentTarget);
            }}
            style={{
              background: "none", border: "none", color: "rgba(255,255,255,0.5)",
              cursor: "pointer", fontSize: 12, padding: "2px 4px", borderRadius: 4,
              transition: "all 0.2s"
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "rgba(255,255,255,0.1)";
              e.currentTarget.style.color = "#34D399";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "none";
              e.currentTarget.style.color = "rgba(255,255,255,0.5)";
            }}
            title="Copy full address"
          >
            📋
          </button>
        </div>
      </div>

      {/* Links */}
      <div style={{ display: "flex", gap: 8 }}>
          <a href={defiLlamaUrl} target="_blank" rel="noopener noreferrer" style={{
            flex: 1, textAlign: "center", padding: "8px 0",
            background: "rgba(15,23,42,0.72)",
            border: "1px solid rgba(96,165,250,0.24)", borderRadius: 10,
            color: "#00A3FF", fontSize: 12, fontWeight: 600, textDecoration: "none",
          }}>
          🦙 DefiLlama
        </a>
        {explorerUrl && (
          <a href={explorerUrl} target="_blank" rel="noopener noreferrer" style={{
            flex: 1, textAlign: "center", padding: "8px 0",
            background: "rgba(96,165,250,0.1)", border: "1px solid rgba(96,165,250,0.25)",
            borderRadius: 8, color: "#60A5FA", fontSize: 12, fontWeight: 600, textDecoration: "none",
          }}>
            🔍 Explorer
          </a>
        )}
          <a href={protocolUrl} target="_blank" rel="noopener noreferrer" style={{
            flex: 1, textAlign: "center", padding: "8px 0",
            background: "linear-gradient(135deg,#10b981,#34d399)", border: "1px solid rgba(16,185,129,0.24)",
            borderRadius: 10, color: "#03150f", fontSize: 12, fontWeight: 700, textDecoration: "none",
            boxShadow: "0 10px 24px rgba(16,185,129,0.18)",
          }}>
            🌐 View Pool
          </a>
      </div>
    </motion.div>
  );
}

// ── AuthScreen ───────────────────────────────────────────────────────────────
const API = "/api/v1";

interface AuthScreenProps {
  onAuth: (user: AuthUser, walletType: "metamask" | "phantom") => void;
  onClose?: () => void;
}

function AuthScreen({ onAuth, onClose }: AuthScreenProps) {
  const [loading, setLoading] = useState<"" | "metamask" | "phantom">("");
  const [error, setError] = useState("");

  const handleMetaMask = async () => {
    setError(""); setLoading("metamask");
    try {
      const { user, address, chainId } = await connectMetaMask();
      const authUser: AuthUser = { id: user.id, display_name: user.display_name, wallet_address: address, email: user.email, token: user.token };
      // chainId stored for later use — MetaMask defaults to BNB (56)
      void chainId;
      onAuth(authUser, "metamask");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading("");
    }
  };

  const handlePhantom = async () => {
    setError(""); setLoading("phantom");
    try {
      const { solanaAddress, evmAddress, evmChainId, displayName, signedMessage, signature } = await connectPhantomSolana();
      localStorage.setItem("ap_sol_wallet", solanaAddress);
      if (evmAddress) {
        localStorage.setItem("ap_wallet", evmAddress);
      }
      localStorage.setItem("ap_phantom_wallet_context", JSON.stringify({ solanaAddress, evmAddress, evmChainId }));

      // Attempt backend authentication to get a real JWT
      let authUser: AuthUser;
      if (signature) {
        try {
          const res = await fetch(`${API}/auth/phantom`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              public_key: solanaAddress,
              message: signedMessage,
              signature,
              display_name: displayName,
            }),
          });
          if (res.ok) {
            const data = await res.json();
            authUser = {
              id: data.user.id,
              display_name: data.user.display_name,
              wallet_address: solanaAddress,
              email: data.user.email,
              token: data.token,
            };
            localStorage.setItem("ap_token", data.token);
          } else {
            // Auth failed — fall back to guest mode (no chat persistence)
            authUser = { id: 0, wallet_address: solanaAddress, display_name: displayName, token: "" };
          }
        } catch {
          authUser = { id: 0, wallet_address: solanaAddress, display_name: displayName, token: "" };
        }
      } else {
        // signMessage failed — guest mode
        authUser = { id: 0, wallet_address: solanaAddress, display_name: displayName, token: "" };
      }

      onAuth(authUser, "phantom");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading("");
    }
  };

  return (
    <div className="auth-overlay">
      <div className="auth-card">
        {onClose && (
          <button onClick={onClose} style={{
            position: "absolute", top: 16, right: 16,
            background: "rgba(15,23,42,0.72)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "50%",
            width: 32, height: 32, cursor: "pointer", fontSize: 18, color: "#aaa",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>×</button>
        )}

        <div className="auth-logo">
          <div className="auth-logo-mark">
            <img src="/ilyon-logo.svg" alt="Ilyon AI" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
          </div>
          <div>
            <div className="auth-logo-text">Ilyon AI Beta</div>
            <div className="auth-logo-sub">Multi-Chain DeFi AI</div>
          </div>
        </div>

        <div className="auth-title">Connect your wallet</div>
        <div className="auth-sub">
          Choose your wallet to sign in. Your address is your identity —
          no password needed.
        </div>

        <button className="auth-btn" onClick={handleMetaMask} disabled={!!loading} style={{ marginBottom: 10 }}>
          {loading === "metamask" ? "Waiting for signature…" : "🦊 Connect with MetaMask"}
        </button>

        <button className="auth-btn" onClick={handlePhantom} disabled={!!loading} style={{
          background: "rgba(15,23,42,0.78)",
          boxShadow: "none",
          border: "1px solid rgba(139,92,246,0.28)",
          color: "#C4B5FD",
        }}>
          {loading === "phantom" ? "Connecting…" : "👻 Connect with Phantom"}
        </button>

        {error && <div className="auth-error" style={{ marginTop: 14 }}>{error}</div>}

        <div style={{ marginTop: 20, fontSize: 11, color: "rgba(255,255,255,0.2)", textAlign: "center", lineHeight: 1.6 }}>
          Non-custodial · Your keys, your crypto · No email required
        </div>
      </div>
    </div>
  );
}

// ── ChatListPanel ─────────────────────────────────────────────────────────────
interface ChatListPanelProps {
  chats: ChatItem[];
  currentChatId: string | null;
  onSelect: (chatId: string) => void;
  onCreate: () => void;
  onDelete: (chatId: string) => void;
  onClose: () => void;
}

function ChatListPanel({ chats, currentChatId, onSelect, onCreate, onDelete, onClose }: ChatListPanelProps) {
  const fmtDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  };
  return (
    <div className="chat-list-overlay">
      <div className="chat-list-backdrop" onClick={onClose} />
      <motion.div
        className="chat-list-panel"
        initial={{ x: -260 }}
        animate={{ x: 0 }}
        exit={{ x: -260 }}
        transition={{ duration: 0.22, ease: "easeOut" }}
      >
        <div className="chat-list-header">
          <span className="chat-list-title">💬 Chats</span>
          <button className="chat-list-close" onClick={onClose}>×</button>
        </div>
        <button className="chat-list-new" onClick={onCreate}>＋ New Chat</button>
        <div className="chat-list-body">
          {chats.length === 0 ? (
            <div className="chat-list-empty">
              <div className="chat-list-empty-icon">💬</div>
              No chats yet. Start a conversation!
            </div>
          ) : (
            chats.map(chat => (
              <div
                key={chat.id}
                className={`chat-item ${chat.id === currentChatId ? "active" : ""}`}
                onClick={() => onSelect(chat.id)}
              >
                <span className="chat-item-icon">💬</span>
                <div className="chat-item-body">
                  <div className="chat-item-title">{chat.title}</div>
                  <div className="chat-item-date">{fmtDate(chat.updated_at)}</div>
                </div>
                <button
                  className="chat-item-del"
                  onClick={e => { e.stopPropagation(); onDelete(chat.id); }}
                  title="Delete chat"
                >🗑</button>
              </div>
            ))
          )}
        </div>
      </motion.div>
    </div>
  );
}

// ── Portfolio helpers ─────────────────────────────────────────────────────────
interface PortfolioToken {
  symbol: string;
  name: string;
  icon: string;
  grad: string;
  balance: string;
  balanceRaw: number;
  price: number;
  valueUsd: number;
  chainName?: string;
}

interface ChainTokenConfig {
  symbol: string; name: string; address: string; decimals: number;
  icon: string; grad: string; stablecoin: boolean; pricePair?: string;
}
interface ChainConfig {
  id?: number; explorer?: string;
  name: string; rpc: string;
  nativeSymbol: string; nativeIcon: string; nativeGrad: string; nativePricePair: string;
  tokens: ChainTokenConfig[];
}

const CHAIN_CONFIG: Record<number, ChainConfig> = {
  56: {
    name: "BNB Smart Chain", rpc: "https://bsc-dataseed.binance.org",
    nativeSymbol: "BNB", nativeIcon: "⬡", nativeGrad: "linear-gradient(135deg,#F0B90B,#E8832A)", nativePricePair: "BNBUSDT",
    tokens: [
      // Stablecoins
      { symbol: "USDT",  name: "Tether USD",         address: "0x55d398326f99059fF775485246999027B3197955", decimals: 18, icon: "₮", grad: "linear-gradient(135deg,#26A17B,#1A7A5E)", stablecoin: true },
      { symbol: "USDC",  name: "USD Coin",            address: "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", decimals: 18, icon: "$", grad: "linear-gradient(135deg,#2775CA,#1a5a9e)", stablecoin: true },
      { symbol: "BUSD",  name: "Binance USD",         address: "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56", decimals: 18, icon: "B$", grad: "linear-gradient(135deg,#F0B90B,#b38608)", stablecoin: true },
      { symbol: "DAI",   name: "Dai",                 address: "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3", decimals: 18, icon: "◈", grad: "linear-gradient(135deg,#F5AC37,#b07d1e)", stablecoin: true },
      { symbol: "FDUSD", name: "First Digital USD",   address: "0xc5f0f7b66764F6ec8C8Dff7BA683102295E16409", decimals: 18, icon: "$", grad: "linear-gradient(135deg,#1a6faf,#0d4a78)", stablecoin: true },
      // Major crypto (pegged BEP-20)
      { symbol: "WBNB",  name: "Wrapped BNB",         address: "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", decimals: 18, icon: "⬡", grad: "linear-gradient(135deg,#F0B90B,#E8832A)", stablecoin: false, pricePair: "BNBUSDT" },
      { symbol: "ETH",   name: "Ethereum (BEP-20)",   address: "0x2170Ed0880ac9A755fd29B2688956BD959F933F8", decimals: 18, icon: "Ξ", grad: "linear-gradient(135deg,#627EEA,#3c5aa8)", stablecoin: false, pricePair: "ETHUSDT" },
      { symbol: "BTCB",  name: "Bitcoin (BEP-20)",    address: "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", decimals: 18, icon: "₿", grad: "linear-gradient(135deg,#F7931A,#c47213)", stablecoin: false, pricePair: "BTCUSDT" },
      { symbol: "CAKE",  name: "PancakeSwap",         address: "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82", decimals: 18, icon: "🥞", grad: "linear-gradient(135deg,#1FC7D4,#118fa0)", stablecoin: false, pricePair: "CAKEUSDT" },
      { symbol: "XRP",   name: "XRP (BEP-20)",        address: "0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE", decimals: 18, icon: "✕", grad: "linear-gradient(135deg,#346AA9,#1e4578)", stablecoin: false, pricePair: "XRPUSDT" },
      { symbol: "ADA",   name: "Cardano (BEP-20)",    address: "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47", decimals: 18, icon: "₳", grad: "linear-gradient(135deg,#0D1E6E,#09144a)", stablecoin: false, pricePair: "ADAUSDT" },
      { symbol: "SOL",   name: "Solana (BEP-20)",     address: "0x570A5D26f7765Ecb712C0924E4De545B89fD43dF", decimals: 18, icon: "◎", grad: "linear-gradient(135deg,#9945FF,#6b30b8)", stablecoin: false, pricePair: "SOLUSDT" },
      { symbol: "DOT",   name: "Polkadot (BEP-20)",   address: "0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402", decimals: 18, icon: "●", grad: "linear-gradient(135deg,#E6007A,#a0005a)", stablecoin: false, pricePair: "DOTUSDT" },
      { symbol: "DOGE",  name: "Dogecoin (BEP-20)",   address: "0xbA2aE424d960c26247Dd6c32edC70B295c744C43", decimals: 8,  icon: "Ð", grad: "linear-gradient(135deg,#C2A633,#8a7422)", stablecoin: false, pricePair: "DOGEUSDT" },
      { symbol: "LTC",   name: "Litecoin (BEP-20)",   address: "0x4338665CBB7B2485A8855A139b75D5e34AB0DB94", decimals: 18, icon: "Ł", grad: "linear-gradient(135deg,#BFBBBB,#8a8888)", stablecoin: false, pricePair: "LTCUSDT" },
      { symbol: "LINK",  name: "Chainlink (BEP-20)",  address: "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD", decimals: 18, icon: "⬡", grad: "linear-gradient(135deg,#2A5ADA,#1a3ea0)", stablecoin: false, pricePair: "LINKUSDT" },
      { symbol: "AVAX",  name: "Avalanche (BEP-20)",  address: "0x1CE0c2827e2eF14D5C4f29a091d735A204794041", decimals: 18, icon: "△", grad: "linear-gradient(135deg,#E84142,#a82e2f)", stablecoin: false, pricePair: "AVAXUSDT" },
      { symbol: "UNI",   name: "Uniswap (BEP-20)",    address: "0xBf5140A22578168FD562DCcF235E5D43A02ce9B1", decimals: 18, icon: "🦄", grad: "linear-gradient(135deg,#FF007A,#b30056)", stablecoin: false, pricePair: "UNIUSDT" },
      { symbol: "MATIC", name: "Polygon (BEP-20)",    address: "0xCC42724C6683B7E57334c4E856f4c9965ED682bD", decimals: 18, icon: "⬡", grad: "linear-gradient(135deg,#8247E5,#5a2fa0)", stablecoin: false, pricePair: "MATICUSDT" },
      { symbol: "TRX",   name: "TRON (BEP-20)",       address: "0xCE7de646e7208a4Ef112cb6ed5038FA6cC6b12e3", decimals: 6,  icon: "◆", grad: "linear-gradient(135deg,#EB0029,#a00020)", stablecoin: false, pricePair: "TRXUSDT" },
      { symbol: "SHIB",  name: "Shiba Inu (BEP-20)",  address: "0x2859e4544C4bB03966803b044A93563Bd2D0DD4D", decimals: 18, icon: "🐕", grad: "linear-gradient(135deg,#FFA409,#b37306)", stablecoin: false, pricePair: "SHIBUSDT" },
    ],
  },
  1: {
    name: "Ethereum", rpc: "https://rpc.ankr.com/eth",
    nativeSymbol: "ETH", nativeIcon: "Ξ", nativeGrad: "linear-gradient(135deg,#627EEA,#3c5aa8)", nativePricePair: "ETHUSDT",
    tokens: [
      { symbol: "USDT",  name: "Tether USD",  address: "0xdAC17F958D2ee523a2206206994597C13D831ec7", decimals: 6,  icon: "₮", grad: "linear-gradient(135deg,#26A17B,#1A7A5E)", stablecoin: true },
      { symbol: "USDC",  name: "USD Coin",    address: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", decimals: 6,  icon: "$", grad: "linear-gradient(135deg,#2775CA,#1a5a9e)", stablecoin: true },
      { symbol: "WBTC",  name: "Wrapped BTC", address: "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", decimals: 8,  icon: "₿", grad: "linear-gradient(135deg,#F7931A,#c47213)", stablecoin: false, pricePair: "BTCUSDT" },
      { symbol: "LINK",  name: "Chainlink",   address: "0x514910771AF9Ca656af840dff83E8264EcF986CA", decimals: 18, icon: "⬡", grad: "linear-gradient(135deg,#2A5ADA,#1a3ea0)", stablecoin: false, pricePair: "LINKUSDT" },
      { symbol: "UNI",   name: "Uniswap",     address: "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984", decimals: 18, icon: "🦄", grad: "linear-gradient(135deg,#FF007A,#b30056)", stablecoin: false, pricePair: "UNIUSDT" },
    ],
  },
  137: {
    name: "Polygon", rpc: "https://rpc.ankr.com/polygon",
    nativeSymbol: "MATIC", nativeIcon: "⬡", nativeGrad: "linear-gradient(135deg,#8247E5,#5a2fa0)", nativePricePair: "MATICUSDT",
    tokens: [
      { symbol: "USDT", name: "Tether USD", address: "0xc2132D05D31c914a87C6611C10748AEb04B58e8F", decimals: 6, icon: "₮", grad: "linear-gradient(135deg,#26A17B,#1A7A5E)", stablecoin: true },
      { symbol: "USDC", name: "USD Coin",   address: "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174", decimals: 6, icon: "$", grad: "linear-gradient(135deg,#2775CA,#1a5a9e)", stablecoin: true },
    ],
  },
  8453: {
    id: 8453,
    name: "Base",
    rpc: "https://mainnet.base.org",
    explorer: "https://basescan.org",
    nativeSymbol: "ETH",
    nativeIcon: "https://cryptologos.cc/logos/ethereum-eth-logo.png",
    nativeGrad: "linear-gradient(135deg, #0052FF 0%, #002299 100%)",
    nativePricePair: "ETHUSDT",
    tokens: [
      { address: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", symbol: "USDC", name: "USD Coin", decimals: 6, icon: "https://cryptologos.cc/logos/usd-coin-usdc-logo.png", grad: "linear-gradient(135deg, #2775ca 0%, #1a4f8b 100%)", stablecoin: true },
    ],
  },
  10: {
    id: 10,
    name: "Optimism",
    rpc: "https://mainnet.optimism.io",
    explorer: "https://optimistic.etherscan.io",
    nativeSymbol: "ETH",
    nativeIcon: "https://cryptologos.cc/logos/ethereum-eth-logo.png",
    nativeGrad: "linear-gradient(135deg, #FF0420 0%, #990213 100%)",
    nativePricePair: "ETHUSDT",
    tokens: [
      { address: "0x4200000000000000000000000000000000000042", symbol: "OP", name: "Optimism", decimals: 18, icon: "https://cryptologos.cc/logos/optimism-ethereum-op-logo.png", grad: "linear-gradient(135deg, #FF0420 0%, #990213 100%)", stablecoin: false, pricePair: "OPUSDT" },
    ],
  },
  43114: {
    id: 43114,
    name: "Avalanche",
    rpc: "https://api.avax.network/ext/bc/C/rpc",
    explorer: "https://snowtrace.io",
    nativeSymbol: "AVAX",
    nativeIcon: "https://cryptologos.cc/logos/avalanche-avax-logo.png",
    nativeGrad: "linear-gradient(135deg, #E84142 0%, #992b2c 100%)",
    nativePricePair: "AVAXUSDT",
    tokens: [
      { address: "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7", symbol: "USDT", name: "Tether USD", decimals: 6, icon: "https://cryptologos.cc/logos/tether-usdt-logo.png", grad: "linear-gradient(135deg, #26A17B 0%, #105c44 100%)", stablecoin: true },
    ],
  },
  42161: {
    id: 42161,
    name: "Arbitrum",
    rpc: "https://arb1.arbitrum.io/rpc",
    explorer: "https://arbiscan.io",
    nativeSymbol: "ETH",
    nativeIcon: "Ξ",
    nativeGrad: "linear-gradient(135deg,#28A0F0,#1a6faa)",
    nativePricePair: "ETHUSDT",
    tokens: [
      { address: "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", symbol: "USDT", name: "Tether USD",  decimals: 6,  icon: "₮", grad: "linear-gradient(135deg,#26A17B,#1A7A5E)", stablecoin: true },
      { address: "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", symbol: "USDC", name: "USD Coin",    decimals: 6,  icon: "$", grad: "linear-gradient(135deg,#2775CA,#1a5a9e)", stablecoin: true },
      { address: "0x912CE59144191C1204E64559FE8253a0e49E6548", symbol: "ARB",  name: "Arbitrum",    decimals: 18, icon: "△", grad: "linear-gradient(135deg,#28A0F0,#1a6faa)", stablecoin: false, pricePair: "ARBUSDT" },
    ],
  },
  324: {
    id: 324,
    name: "zkSync Era",
    rpc: "https://mainnet.era.zksync.io",
    explorer: "https://explorer.zksync.io",
    nativeSymbol: "ETH",
    nativeIcon: "Ξ",
    nativeGrad: "linear-gradient(135deg,#8C8DFC,#5253a8)",
    nativePricePair: "ETHUSDT",
    tokens: [
      { address: "0x493257fD37EDB34451f62EDf8D2a0C418852bA4C", symbol: "USDT", name: "Tether USD", decimals: 6,  icon: "₮", grad: "linear-gradient(135deg,#26A17B,#1A7A5E)", stablecoin: true },
      { address: "0x3355df6D4c9C3035724Fd0e3914dE96A5a83aaf4", symbol: "USDC", name: "USD Coin",   decimals: 6,  icon: "$", grad: "linear-gradient(135deg,#2775CA,#1a5a9e)", stablecoin: true },
    ],
  },
  250: {
    id: 250,
    name: "Fantom",
    rpc: "https://rpc.ftm.tools",
    explorer: "https://ftmscan.com",
    nativeSymbol: "FTM",
    nativeIcon: "👻",
    nativeGrad: "linear-gradient(135deg,#1969FF,#1048b3)",
    nativePricePair: "FTMUSDT",
    tokens: [
      { address: "0x049d68029688eAbF473097a2fC38ef61633A3C7A", symbol: "USDT", name: "Tether USD", decimals: 6,  icon: "₮", grad: "linear-gradient(135deg,#26A17B,#1A7A5E)", stablecoin: true },
      { address: "0x04068DA6C83AFCFA0e13ba15A6696662335D5B75", symbol: "USDC", name: "USD Coin",   decimals: 6,  icon: "$", grad: "linear-gradient(135deg,#2775CA,#1a5a9e)", stablecoin: true },
    ],
  },
};

// CoinGecko IDs for fallback pricing when Binance is unavailable


async function fetchPortfolio(
  address: string,
): Promise<{ tokens: PortfolioToken[]; totalUsd: number; nativePrice: number; solPrice: number; chainName: string }> {
  try {
    const response = await fetch(`/api/portfolio/${address}`);
    if (!response.ok) throw new Error(`Backend returned ${response.status}`);
    const data = await response.json();
    return {
      tokens:      data.tokens   ?? [],
      totalUsd:    data.totalUsd ?? 0,
      nativePrice: data.bnbPrice ?? 0,
      solPrice:    data.solPrice ?? 0,
      chainName:   "All Networks",
    };
  } catch (error) {
    console.error("Backend portfolio error:", error);
    return { tokens: [], totalUsd: 0, nativePrice: 0, solPrice: 0, chainName: "Error" };
  }
}

function buildPhantomPortfolioAddress(solanaAddress: string | null, evmAddress: string | null): string {
  if (solanaAddress && evmAddress) return `${solanaAddress},${evmAddress}`;
  return solanaAddress || evmAddress || "";
}

// ── Component ────────────────────────────────────────────────────────────────
export default function MainApp() {
  const makeWelcome = (): Message => ({ ...WELCOME, ts: new Date() });
  const createClientSessionId = () => globalThis.crypto?.randomUUID?.() ?? `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const [messages, setMessages]         = useState<Message[]>(() => loadLocalChatMessages() ?? [makeWelcome()]);
  const [input, setInput]               = useState("");
  const [loading, setLoading]           = useState(false);
  const [backendOk, setBackendOk]       = useState<null | boolean>(null);
  const [activeTab, setActiveTab]       = useState<Tab>(() => {
    if (typeof window === "undefined") return "chat";
    const t = new URLSearchParams(window.location.search).get("tab");
    return t === "chat" || t === "swap" || t === "portfolio" || t === "dashboard" ? t : "chat";
  });
  useEffect(() => {
    if (typeof window === "undefined") return;
    const sync = () => {
      const t = new URLSearchParams(window.location.search).get("tab");
      if (t === "chat" || t === "swap" || t === "portfolio" || t === "dashboard") setActiveTab(t);
    };
    window.addEventListener("popstate", sync);
    window.addEventListener("ilyon-tab-change", sync as EventListener);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener("ilyon-tab-change", sync as EventListener);
    };
  }, []);
  const [showIntro, setShowIntro]       = useState(() => {
    if (typeof window === "undefined") return true;
    return !new URLSearchParams(window.location.search).get("tab");
  });
  const [introFading, setIntroFading]   = useState(false);
  const [openReasoning, setOpenReasoning] = useState<number | null>(null);
  const [liveSteps, setLiveSteps]       = useState<ReasoningStep[]>([]);
  const [totalSteps, setTotalSteps]     = useState(0);

  // Auth + chat persistence
  const [authUser, setAuthUser]         = useState<AuthUser | null>(null);
  const [walletType, setWalletType]     = useState<"metamask" | "phantom" | null>(
    () => (localStorage.getItem("ap_wallet_type") as "metamask" | "phantom" | null) || null
  );
  // Show login modal on load if not authenticated and no Phantom wallet saved
  const [showAuth, setShowAuth]         = useState(
    () => !localStorage.getItem("ap_token") && !localStorage.getItem("ap_sol_wallet")
  );
  const [chatList, setChatList]         = useState<ChatItem[]>(() => loadLocalChatIndex());
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [clientSessionId, setClientSessionId] = useState<string>(() => localStorage.getItem("ap_chat_session") || createClientSessionId());
  const [showChatList, setShowChatList] = useState(false);
  const [executionNotice, setExecutionNotice] = useState<ExecutionNotice | null>(null);

  // Wallet connections — EVM (MetaMask/Phantom EVM) and Solana (Phantom)
  const [connectedWallet, setConnectedWallet] = useState<string | null>(() => {
    return localStorage.getItem("ap_wallet") || null;
  });
  const [solanaWallet, setSolanaWallet] = useState<string | null>(() => {
    const stored = getStoredPhantomWalletContext();
    return stored?.solanaAddress ?? localStorage.getItem("ap_sol_wallet") ?? null;
  });
  const solDisplayAddr = solanaWallet ?? null;
  const [_nativeBalance, setNativeBalance]       = useState<string>("0.00");
  const [portfolioTokens, setPortfolioTokens]   = useState<PortfolioToken[]>([]);
  const [portfolioTotalUsd, setPortfolioTotalUsd] = useState<number>(0);
  const [bnbPriceUsd, setBnbPriceUsd]           = useState<number>(0);
  const [solPriceUsd, setSolPriceUsd]           = useState<number>(0);
  const [portfolioLoading, setPortfolioLoading] = useState(false);
  const [balanceUnit, setBalanceUnit]           = useState<"USD" | "native">("USD");
  const [connectedChainId, setConnectedChainId] = useState<number>(() => {
    const stored = getStoredPhantomWalletContext();
    if ((localStorage.getItem("ap_wallet_type") as "metamask" | "phantom" | null) === "phantom") {
      return stored?.evmChainId ?? 101;
    }
    return 56;
  });

  const [portfolioError, setPortfolioError]     = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem("ap_chat_session", clientSessionId);
  }, [clientSessionId]);

  useEffect(() => {
    if (typeof window === "undefined" || authUser?.token || localStorage.getItem("ap_token")) return;
    let cancelled = false;
    restorePhantomWalletContext()
      .then(context => {
        if (cancelled || !context?.solanaAddress) return;
        setWalletType("phantom");
        setSolanaWallet(context.solanaAddress);
        setConnectedWallet(context.evmAddress || null);
        setConnectedChainId(context.evmChainId || 101);
        setShowAuth(false);
        setChatList(loadLocalChatIndex());
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [authUser?.token]);

  useEffect(() => {
    if (typeof window === "undefined" || authUser?.token || localStorage.getItem("ap_token")) return;
    const key = localChatStorageKey(clientSessionId);
    if (!key) return;
    if (!shouldPersistLocalMessages(messages)) {
      localStorage.removeItem(key);
      return;
    }
    localStorage.setItem(key, JSON.stringify(messages));
    const updated = upsertLocalChatIndex({
      id: clientSessionId,
      title: titleFromMessages(messages),
      updated_at: new Date().toISOString(),
    });
    setChatList(updated);
  }, [authUser?.token, clientSessionId, messages]);

  useEffect(() => {
    const prevVersion = localStorage.getItem("ap_app_version");
    if (prevVersion !== APP_VERSION) {
      localStorage.setItem("ap_app_version", APP_VERSION);
      localStorage.removeItem("ap_chat_session");
      setCurrentChatId(null);
      setClientSessionId(createClientSessionId());
      setMessages([makeWelcome()]);
      setLiveSteps([]);
      setTotalSteps(0);
      setLoading(false);
    }
  }, [APP_VERSION]);

  // Toast notifications
  const [toasts, setToasts] = useState<Array<{id: number; msg: string; type: "success"|"error"|"info"}>>([]);
  const toastId = useRef(0);
  const showToast = (msg: string, type: "success"|"error"|"info" = "info") => {
    const id = ++toastId.current;
    setToasts(prev => [...prev, { id, msg, type }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3500);
  };

  // Swap tab state
  const [swapFromToken, setSwapFromToken] = useState("BNB");
  const [swapToToken, setSwapToToken]     = useState("USDT");
  const [swapFromAmount, setSwapFromAmount] = useState("");
  const [swapQuote, setSwapQuote]         = useState<{toAmount: string; rate: string; route: string} | null>(null);
  const [swapQuoteLoading, setSwapQuoteLoading] = useState(false);
  const [overviewSearch, setOverviewSearch] = useState("");

  // ── Live ticker prices ───────────────────────────────────────────────────
  const [livePrices, setLivePrices] = useState<Record<string, { price: string; change: string; pos: boolean }>>({
    USDT: { price: "$1.00", change: "0.0%", pos: false },
  });
  useEffect(() => {
    const fetchPrices = async () => {
      try {
        const ids = Object.values(CG_IDS).join(",");
        const res = await fetch(
          `https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd&include_24hr_change=true`,
          { signal: AbortSignal.timeout(8000) }
        );
        if (!res.ok) return;
        const data = await res.json();
        const updated: Record<string, { price: string; change: string; pos: boolean }> = {
          USDT: { price: "$1.00", change: "0.0%", pos: false },
        };
        for (const [sym, cgId] of Object.entries(CG_IDS)) {
          const info = data[cgId];
          if (!info || typeof info.usd !== "number") continue;
          const price = Number(info.usd);
          const change = Number(info.usd_24h_change || 0);
          updated[sym] = {
            price: price >= 1000 ? `$${price.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : `$${price.toFixed(price < 1 ? 4 : 2)}`,
            change: `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`,
            pos: change >= 0,
          };
        }
        setLivePrices(updated);
      } catch { /* keep stale prices */ }
    };
    fetchPrices();
    const id = setInterval(fetchPrices, 30_000);
    return () => clearInterval(id);
  }, []);

  // Listen for active wallet EVM chain changes
  useEffect(() => {
    let eth: { request: (a: { method: string; params?: unknown[] }) => Promise<unknown>; on?: (e: string, h: (v: string) => void) => void; removeListener?: (e: string, h: (v: string) => void) => void } | null = null;
    try {
      if (walletType === "phantom") {
        eth = resolvePhantomEvmProvider();
      } else if (walletType === "metamask") {
        eth = resolveMetaMaskProvider();
      }
    } catch {
      eth = null;
    }
    if (!eth) {
      if (walletType === "phantom") {
        setConnectedChainId(101);
      }
      return;
    }
    const handleChainChange = (chainHex: string) => setConnectedChainId(parseInt(chainHex, 16));
    eth.on?.("chainChanged", handleChainChange);
    if (connectedWallet) {
      eth.request({ method: "eth_chainId" }).then(h => setConnectedChainId(parseInt(h as string, 16))).catch(() => {});
    }
    return () => { eth.removeListener?.("chainChanged", handleChainChange); };
  }, [connectedWallet, walletType]);

  useEffect(() => {
    const wallet = walletType === "phantom"
      ? buildPhantomPortfolioAddress(solanaWallet, connectedWallet)
      : connectedWallet;
    if (!wallet) {
      setNativeBalance("0.00");
      setPortfolioTokens([]);
      setPortfolioTotalUsd(0);
      setPortfolioError(null);
      return;
    }
    setPortfolioLoading(true);
    setPortfolioError(null);
      fetchPortfolio(wallet)
      .then(({ tokens, totalUsd, nativePrice, solPrice }) => {
        setPortfolioTokens(tokens);
        setPortfolioTotalUsd(totalUsd);
        setBnbPriceUsd(nativePrice);
        setSolPriceUsd(solPrice);
        const preferredNative = walletType === "phantom" ? "SOL" : "BNB";
        const mainToken = tokens.find(t => t.symbol === preferredNative || t.symbol === "ETH" || t.symbol === "SOL");
        setNativeBalance(mainToken ? mainToken.balance : "0.00");
      })
      .catch(console.error)
      .finally(() => setPortfolioLoading(false));
  }, [connectedWallet, solanaWallet, walletType]);

  // Live swap quote fetching via CoinGecko-backed live prices
  useEffect(() => {
    const amount = parseFloat(swapFromAmount);
    if (!amount || amount <= 0 || swapFromToken === swapToToken) {
      setSwapQuote(null);
      return;
    }
    setSwapQuoteLoading(true);
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const parseUsd = (symbol: string) => {
          if (symbol === "USDT" || symbol === "USDC") return 1;
          const priceText = livePrices[symbol]?.price;
          if (!priceText) return null;
          const parsed = Number(priceText.replace(/[$,]/g, ""));
          return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
        };
        const fromUsd = parseUsd(swapFromToken);
        const toUsd = parseUsd(swapToToken);
        if (!fromUsd || !toUsd) {
          setSwapQuote(null);
          return;
        }
        const toAmount = (amount * fromUsd / toUsd).toFixed(toUsd > 100 ? 4 : 2);
        const rate = (fromUsd / toUsd).toFixed(toUsd > 100 ? 6 : 4);
        const route = swapFromToken === "SOL" || swapToToken === "SOL" ? "Jupiter" : "1inch";
        setSwapQuote({ toAmount, rate, route });
      } catch {
        setSwapQuote(null);
      } finally {
        setSwapQuoteLoading(false);
      }
    }, 500);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [livePrices, swapFromAmount, swapFromToken, swapToToken]);

  const messagesRef    = useRef<HTMLDivElement>(null);
  const textareaRef    = useRef<HTMLTextAreaElement>(null);
  const introScrollRef = useRef<HTMLDivElement>(null);
  const liveTimersRef  = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    const checkHealth = () =>
      fetch("/api/v1/agent-health", { signal: AbortSignal.timeout(3000) })
        .then(() => setBackendOk(true))
        .catch(() => setBackendOk(false));
    checkHealth();
    const id = setInterval(checkHealth, 30_000);
    return () => clearInterval(id);
  }, []);

  // Restore auth session from localStorage on mount
  useEffect(() => {
    const token = localStorage.getItem("ap_token");
    if (!token) return;
    fetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) {
          const user: AuthUser = { ...data, token };
          setAuthUser(user);
          fetchChatList(token);
        } else {
          localStorage.removeItem("ap_token");
        }
      })
      .catch(() => localStorage.removeItem("ap_token"));
  }, []);

  const fetchChatList = (token: string) => {
    fetch(`${API}/chats`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => {
        if (!r.ok) {
          console.warn("fetchChatList failed:", r.status, r.statusText);
          return [];
        }
        return r.json();
      })
      .then(data => setChatList(Array.isArray(data) ? data : []))
      .catch(err => console.error("fetchChatList error:", err));
  };

  useEffect(() => {
    if (!messagesRef.current) return;
    messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
  }, [messages, loading, liveSteps]);

  useEffect(() => {
    if (showIntro && !introFading) {
      introScrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [showIntro, introFading]);

  const launchApp = () => {
    if (!authUser) { setShowAuth(true); return; }
    setIntroFading(true); setTimeout(() => setShowIntro(false), 700);
  };
  const openIntro = () => { setIntroFading(false); setShowIntro(true); setShowAuth(false); };
  const scrollToFeatures = () => document.getElementById("intro-features")?.scrollIntoView({ behavior: "smooth" });

  const handleAuthSuccess = (user: AuthUser, wType: "metamask" | "phantom") => {
    // Cross-wallet cleanup: prevent old wallet's address leaking into the new session.
    // connectMetaMask already removes ap_sol_wallet; mirror that for Phantom.
    if (wType === "phantom") {
      localStorage.removeItem("ap_token");
    }

    // Resolve the new wallet addresses BEFORE comparing with current state.
    const newEvmAddr  = localStorage.getItem("ap_wallet") ?? null;
    const newSolAddr  = wType === "phantom"  ? (getStoredPhantomWalletContext()?.solanaAddress ?? localStorage.getItem("ap_sol_wallet") ?? null) : null;

    // Only wipe chat state when the wallet address actually changes.
    // Same wallet reconnecting (e.g. user clicked Connect again) should keep history intact.
    const prevEvmAddr = connectedWallet;
    const prevSolAddr = solanaWallet;
    const walletChanged = newEvmAddr !== prevEvmAddr || newSolAddr !== prevSolAddr;

    setAuthUser(user);
    setWalletType(wType);
    setShowAuth(false);

    if (walletChanged) {
      setMessages([makeWelcome()]);
      setCurrentChatId(null);
      setChatList([]);
    }

    if (user.token) fetchChatList(user.token);

    // Set wallet addresses strictly per wallet type — never carry over the other type's address.
    setConnectedWallet(newEvmAddr);
    setSolanaWallet(newSolAddr);
    if (wType === "phantom") {
      const stored = getStoredPhantomWalletContext();
      setConnectedChainId(stored?.evmChainId ?? 101);
    }
    setIntroFading(true); setTimeout(() => setShowIntro(false), 700);
  };

  const handleLogout = () => {
    localStorage.removeItem("ap_token");
    localStorage.removeItem("ap_wallet");
    localStorage.removeItem("ap_sol_wallet");
    localStorage.removeItem("ap_phantom_wallet_context");
    localStorage.removeItem("ap_wallet_type");
    setAuthUser(null);
    setWalletType(null);
    setConnectedWallet(null);
    setSolanaWallet(null);
    setExecutionNotice(null);
    setChatList([]);
    setCurrentChatId(null);
    setClientSessionId(createClientSessionId());
    localStorage.removeItem("ap_chat_session");
    openIntro();
  };

  const handleSelectChat = async (chatId: string) => {
    if (!authUser?.token) {
      const loaded = loadLocalChatMessages(chatId);
      setCurrentChatId(chatId);
      setClientSessionId(chatId);
      setMessages(loaded ?? [makeWelcome()]);
      setExecutionNotice(null);
      setShowChatList(false);
      setActiveTab("chat");
      return;
    }
    setCurrentChatId(chatId);
    setClientSessionId(chatId);
    setShowChatList(false);
    // Load chat messages
    try {
      const res = await fetch(`${API}/chats/${chatId}`, { headers: { Authorization: `Bearer ${authUser.token}` } });
      if (res.ok) {
        const data = await res.json();
        const loaded: Message[] = data.messages.map((m: { id: number; role: string; content: string; created_at: string }) => ({
          id: nextId++,
          role: m.role as Role,
          text: m.content,
          ts: new Date(m.created_at),
          ...resolveStructuredContent(m.content),
        }));
        setMessages(loaded.length > 0 ? loaded : [makeWelcome()]);
      }
    } catch {}
    setActiveTab("chat");
  };

  const handleNewChat = async () => {
    setCurrentChatId(null);
    setClientSessionId(createClientSessionId());
    setMessages([makeWelcome()]);
    setExecutionNotice(null);
    setShowChatList(false);
    setActiveTab("chat");
  };

  // Opens the auth modal — handles both MetaMask and Phantom correctly
  const connectWallet = () => setShowAuth(true);

  const disconnectWallet = () => {
    if (walletType === "phantom") {
      disconnectPhantomSolana();
    }
    setConnectedWallet(null);
    setSolanaWallet(null);
    setAuthUser(null);
    setWalletType(null);
    setConnectedChainId(56);
    setMessages([makeWelcome()]);
    setExecutionNotice(null);
    setCurrentChatId(null);
    setClientSessionId(createClientSessionId());
    setChatList([]);
    localStorage.removeItem("ap_wallet");
    localStorage.removeItem("ap_sol_wallet");
    localStorage.removeItem("ap_phantom_wallet_context");
    localStorage.removeItem("ap_wallet_type");
    localStorage.removeItem("ap_token");
    setShowAuth(true);
  };

  const handleDeleteChat = async (chatId: string) => {
    if (!authUser?.token) {
      const key = localChatStorageKey(chatId);
      if (key) localStorage.removeItem(key);
      setChatList(removeLocalChatIndex(chatId));
      if (currentChatId === chatId || clientSessionId === chatId) {
        setCurrentChatId(null);
        setClientSessionId(createClientSessionId());
        setMessages([makeWelcome()]);
      }
      return;
    }
    await fetch(`${API}/chats/${chatId}`, { method: "DELETE", headers: { Authorization: `Bearer ${authUser.token}` } }).catch(() => {});
    setChatList(prev => prev.filter(c => c.id !== chatId));
    if (currentChatId === chatId) {
      setCurrentChatId(null);
      setClientSessionId(createClientSessionId());
      setMessages([makeWelcome()]);
    }
  };

  const send = async (text: string) => {
    const t = text.trim();
    if (!t || loading) return;

    setMessages(p => [...p, { id: nextId++, role: "user", text: t, ts: new Date() }]);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setLoading(true);
    setActiveTab("chat");
    setLiveSteps([]);
    setExecutionNotice(null);

    // Keep legacy synthetic steps only for non-Sentinel JSON fallbacks.
    const fallbackSteps = generateReasoningSteps(t);
    liveTimersRef.current.forEach(clearTimeout);
    const startFallbackReasoning = () => {
      if (fallbackSteps.length === 0) return;
      const DELAYS = [300, 1200, 2400, 3900, 5700, 7800];
      setTotalSteps(fallbackSteps.length);
      liveTimersRef.current = fallbackSteps.map((step, i) =>
        setTimeout(() => setLiveSteps(prev => [...prev, step]), DELAYS[i] ?? i * 800 + 500)
      );
    };

    try {
      const normalizedQuery = (() => {
        const m = t.match(/^\s*🔄\s*Swap\s+(?:([0-9]*\.?[0-9]+)\s+)?([A-Za-z0-9]+)\s*[→>-]+\s*([A-Za-z0-9]+)\s*$/i);
        if (m) {
          const amount = m[1] || "0.01";
          return `Swap ${amount} ${m[2].toUpperCase()} to ${m[3].toUpperCase()}`;
        }
        return t;
      })();

      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (authUser) headers["Authorization"] = `Bearer ${authUser.token}`;
      const solanaIntent = /\b(solana|sol|bonk|jup|msol|jitosol|ray|orca)\b/i.test(normalizedQuery);
      const effectiveChainId = walletType === "phantom" && (solanaIntent || !connectedWallet) ? 101 : connectedChainId;
      const res = await fetch("/api/v1/agent", {
        method: "POST",
        headers,
        body: JSON.stringify({
          query: normalizedQuery,
          message: normalizedQuery,
          session_id: currentChatId ?? clientSessionId,
          chat_id: currentChatId,
          user_address: connectedWallet ?? "",
          solana_address: solanaWallet ?? "",
          solana_wallet: solanaWallet ?? "",
          evm_wallet: connectedWallet && /^0x[a-fA-F0-9]{40}$/.test(connectedWallet) ? connectedWallet : "",
          // Send the right wallet for Solana intent so the backend doesn't
          // hijack a Phantom EVM-mode hex pubkey when the user wants Solana.
          wallet: solanaIntent && solanaWallet ? solanaWallet : (connectedWallet ?? ""),
          chain_id: effectiveChainId,
          wallet_type: walletType ?? undefined,
        }),
      });

      const contentType = res.headers.get("content-type") || "";
      const isSse = contentType.includes("text/event-stream");
      let rawBody = "";
      let parsedSse: ParsedAgentSseResponse | null = null;

      const applyLiveSseFrames = () => {
        const next = parseAgentSseResponse(rawBody);
        if (!next) return;
        parsedSse = next;
        const liveReasoning = reasoningFromAgentFrames(next.agentThoughts, next.agentTools, next.agentObservations);
        if (liveReasoning.length > 0) {
          setTotalSteps(liveReasoning.length);
          setLiveSteps(liveReasoning);
        }
      };

      if (isSse && res.body && typeof res.body.getReader === "function") {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let pending = "";

        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          pending += decoder.decode(value, { stream: true });

          let boundary = pending.indexOf("\n\n");
          while (boundary >= 0) {
            const block = pending.slice(0, boundary);
            pending = pending.slice(boundary + 2);
            if (block.trim()) {
              rawBody += `${block}\n\n`;
              applyLiveSseFrames();
            }
            boundary = pending.indexOf("\n\n");
          }
        }

        pending += decoder.decode();
        if (pending.trim()) {
          rawBody += pending.endsWith("\n\n") ? pending : `${pending}\n\n`;
          applyLiveSseFrames();
        }
      } else {
        startFallbackReasoning();
        rawBody = await res.text();
        parsedSse = parseAgentSseResponse(rawBody);
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let data: any = {};
      try {
        data = parsedSse ?? (rawBody ? JSON.parse(rawBody) : {});
      } catch {
        throw new Error(`Server returned a non-JSON response (HTTP ${res.status}).`);
      }

      if (!res.ok) {
        const detail = typeof data?.detail === "string"
          ? data.detail
          : (data?.detail ? JSON.stringify(data.detail) : "");
        if (res.status === 429) throw new Error(`⏳ ${detail || "Too many requests. Please wait a few seconds and retry."}`);
        if (res.status === 402) throw new Error(`💳 ${detail || "AI provider credits are insufficient right now. Please top up credits and try again."}`);
        if (res.status === 401 && data.detail?.includes("API key")) throw new Error("🔑 Неверный API ключ. Обнови API_KEYS в server/.env и перезапусти сервер.");
        if (res.status === 504) throw new Error(`⏱️ ${detail || "The AI agent timed out. Please retry."}`);
        throw new Error(detail || `Ошибка сервера ${res.status}`);
      }
      setBackendOk(true);
      const responseText = typeof data.response === "string" ? data.response : "*(модель вернула пустой ответ)*";

      const structured = resolveStructuredContent(responseText);
      const swapPreview = structured.swapPreview;
      const compoundData = structured.compoundData;
      const balanceData = structured.balanceData;
      const poolData = structured.poolData;
      const agentCards = Array.isArray(data.agentCards) ? data.agentCards : [];
      const agentThoughts = Array.isArray(data.agentThoughts) ? data.agentThoughts : [];
      const agentTools = Array.isArray(data.agentTools) ? data.agentTools : [];
      const agentObservations = Array.isArray(data.agentObservations) ? data.agentObservations : [];
      const backendReasoning = reasoningFromAgentFrames(agentThoughts, agentTools, agentObservations);
      const universalCards = agentCards.length ? null : (data.universalCards ?? structured.universalCards);

      // Update chat state from response
      if (authUser && data.chat_id) {
        if (!currentChatId) {
          setCurrentChatId(data.chat_id);
          setClientSessionId(data.chat_id);
        }
        fetchChatList(authUser.token);
      }

      const assistantMessageId = nextId++;
      setMessages(p => [...p, {
        id: assistantMessageId, role: "assistant",
        text: responseText, ts: new Date(),
        reasoning: backendReasoning.length ? backendReasoning : fallbackSteps,
        agentCards,
        agentThoughts,
        agentTools,
        agentObservations,
        agentStepStatuses: Array.isArray(data.agentStepStatuses) ? data.agentStepStatuses : [],
        agentPlanCompletions: Array.isArray(data.agentPlanCompletions) ? data.agentPlanCompletions : [],
        elapsedMs: typeof data.elapsedMs === "number" ? data.elapsedMs : undefined,
        swapPreview,
        compoundData,
        balanceData,
        poolData,
        universalCards,
      }]);
      if (backendReasoning.length) setOpenReasoning(assistantMessageId);
    } catch (err: unknown) {
      setBackendOk(false);
      const msg = err instanceof Error ? err.message : "Error";
      setMessages(p => [...p, {
        id: nextId++, role: "assistant", ts: new Date(),
        text: backendOk === false ? "⚠️ Backend offline.\n\nRun: `./start-server.sh`" : `❌ ${msg}`,
        reasoning: fallbackSteps,
      }]);
    } finally {
      liveTimersRef.current.forEach(clearTimeout);
      setLoading(false);
      setLiveSteps([]);
      setTotalSteps(0);
    }
  };

  const sendRef = useRef(send);
  useEffect(() => { sendRef.current = send; });
  useEffect(() => {
    const onExecute = (event: Event) => {
      const detail = (event as CustomEvent).detail as { pool?: string; message?: string } | undefined;
      const pool = detail?.pool || "";
      const message = detail?.message || (pool ? `Execute this pool ${pool} with $100` : "");
      if (!message) return;
      void sendRef.current(message);
    };
    window.addEventListener("ilyon:execute-pool", onExecute as EventListener);
    return () => window.removeEventListener("ilyon:execute-pool", onExecute as EventListener);
  }, []);

  const handleStartSigning = async (payload: ExecutionPlanPayload) => {
    type StepLite = ExecutionPlanPayload["steps"][number] & {
      rawTx?: unknown;
      swapTransaction?: unknown;
      transaction?: { chain_kind?: string; serialized?: string | null; to?: string | null; data?: string | null; value?: string | null };
      unsignedTx?: unknown;
      serializedTransaction?: unknown;
    };
    // First pass: sign every step that already has a baked unsigned tx,
    // sequentially. This is the new default path now that allocate_plan
    // pre-bakes transactions per position.
    const stepsWithTx = (payload.steps as StepLite[]).filter(s => s.transaction && (s.transaction.serialized || s.transaction.data));
    if (stepsWithTx.length > 0) {
      showToast(`Signing ${stepsWithTx.length} step${stepsWithTx.length > 1 ? "s" : ""} sequentially…`, "info");
      for (const step of stepsWithTx) {
        const tx = step.transaction!;
        try {
          if (tx.chain_kind === "solana" && tx.serialized) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const sol = (window as any)?.phantom?.solana ?? (window as any).solana;
            if (!sol?.isPhantom) throw new Error("Phantom wallet not found");
            const { VersionedTransaction } = await import("@solana/web3.js");
            const bytes = Uint8Array.from(atob(tx.serialized), c => c.charCodeAt(0));
            const vtx = VersionedTransaction.deserialize(bytes);
            const { signature } = await sol.signAndSendTransaction(vtx);
            showToast(`Step ${step.index} signed: ${signature.slice(0, 12)}…`, "success");
          } else if (tx.chain_kind === "evm" && tx.to && tx.data) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const eth: any = (window as any).ethereum;
            if (!eth) throw new Error("MetaMask not found");
            const accs = await eth.request({ method: "eth_accounts" });
            const params = [{ from: accs[0], to: tx.to, data: tx.data, value: tx.value || "0x0" }];
            const hash = await eth.request({ method: "eth_sendTransaction", params });
            showToast(`Step ${step.index} signed: ${String(hash).slice(0, 12)}…`, "success");
          }
        } catch (e: unknown) {
          const msg = (e as { message?: string }).message || "Signing failed";
          showToast(`Step ${step.index} wallet error: ${msg}`, "error");
          break;
        }
      }
      return;
    }
    const hasExecutableTransaction = (payload.steps as StepLite[]).some((step) => {
      return Boolean(
        step.rawTx ||
        step.swapTransaction ||
        step.transaction ||
        step.unsignedTx ||
        step.serializedTransaction
      );
    });

    if (!hasExecutableTransaction) {
      // No txs baked in. Drive the same one-click flow used by per-row
      // Execute buttons: kick off execute_pool_position for the first step.
      // The user signs that step in Phantom/MetaMask; subsequent steps
      // unlock as they request follow-ups.
      const firstStep = payload.steps[0] as (ExecutionPlanPayload["steps"][number] & { target?: string; asset?: string; amount?: string }) | undefined;
      if (firstStep) {
        const target = (firstStep.target || "").replace(/\s*·\s*/g, " ").trim();
        const protoPair = target.split(" ").slice(-2).reverse().join(" ");
        const ref = protoPair || target || `${firstStep.asset || ""}`;
        const amt = Number(String(firstStep.amount || "100").replace(/[^0-9.]/g, "")) || 100;
        const message = `execute_pool_position pool="${ref}" amount=${amt}`;
        showToast(`Building unsigned transaction for ${ref}…`, "info");
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("ilyon:execute-pool", { detail: { pool: ref, message } }));
        }
        setActiveTab("chat");
        return;
      }
    }

    setExecutionNotice({
      title: "Wallet transaction build ready",
      body: "Review the generated unsigned transaction payloads before opening wallet approval. Nothing is submitted until you approve it in your wallet.",
      steps: payload.steps,
    });
    setActiveTab("chat");
    showToast("Transaction build ready for wallet review.", "info");
  };

  const handleSignStep = async (planId: string, stepId: string) => {
    type StepLite = {
      step_id?: string;
      transaction?: {
        chain_kind?: string;
        chain_id?: number | null;
        serialized?: string | null;
        to?: string | null;
        data?: string | null;
        value?: string | null;
      } | null;
    };
    type PlanPayload = { plan_id?: string; steps?: StepLite[] };
    let step: StepLite | undefined;
    for (const m of messages) {
      const cards = m.agentCards || [];
      for (const c of cards) {
        if (c.card_type === "execution_plan_v3") {
          const p = c.payload as PlanPayload;
          if (p?.plan_id === planId) {
            step = (p.steps || []).find(s => s.step_id === stepId);
            if (step) break;
          }
        }
      }
      if (step) break;
    }
    if (!step?.transaction) {
      showToast("Step has no unsigned transaction yet — re-run the build.", "info");
      return;
    }
    const tx = step.transaction;
    try {
      if (tx.chain_kind === "solana" && tx.serialized) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const sol = (window as any)?.phantom?.solana ?? (window as any).solana;
        if (!sol?.isPhantom) throw new Error("Phantom wallet not found");
        const { VersionedTransaction } = await import("@solana/web3.js");
        const bytes = Uint8Array.from(atob(tx.serialized), c => c.charCodeAt(0));
        const vtx = VersionedTransaction.deserialize(bytes);
        const { signature } = await sol.signAndSendTransaction(vtx);
        showToast(`Signed: ${signature.slice(0, 12)}…`, "success");
      } else if (tx.chain_kind === "evm" && tx.to && tx.data) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const eth: any = (window as any).ethereum;
        if (!eth) throw new Error("MetaMask not found");
        const params = [{ from: (await eth.request({ method: "eth_accounts" }))[0], to: tx.to, data: tx.data, value: tx.value || "0x0" }];
        const hash = await eth.request({ method: "eth_sendTransaction", params });
        showToast(`Signed: ${String(hash).slice(0, 12)}…`, "success");
      } else {
        showToast("Unsupported transaction kind on this step.", "info");
      }
    } catch (e: unknown) {
      const msg = (e as { message?: string }).message || "Signing failed";
      showToast(`Wallet error: ${msg}`, "error");
    }
  };

  const handleRerunAllocation = () => {
    void send("Re-run the allocation using the latest live market data and rebalance the plan.");
  };

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
  };
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = textareaRef.current;
    if (el) { el.style.height = "auto"; el.style.height = `${Math.min(el.scrollHeight, 140)}px`; }
  };

  const fmt = (d: Date) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const dotClass   = backendOk === null ? "pending" : backendOk ? "online" : "offline";
  const dotText    = backendOk === null ? "Connecting…" : backendOk ? "Backend online" : "Backend offline";
  const isFirstChat = messages.length === 1;
  const TOKENS = TOKENS_BASE.map(t => {
    const live = livePrices[t.symbol];
    return { ...t, price: live?.price ?? "…", change: live?.change ?? "…", pos: live?.pos ?? false };
  });
  const TICKER_ITEMS = TICKER_PAIRS.map(t => {
    const live = livePrices[t.sym];
    return { sym: t.sym, price: live?.price ?? "…", change: live?.change ?? "…", pos: live?.pos ?? false };
  });
  const tickerFull  = [...TICKER_ITEMS, ...TICKER_ITEMS];

  return (
    <>
      <style>{CSS}</style>

      <div className="bg-canvas">
        <div className="blob blob-1" /><div className="blob blob-2" />
        <div className="blob blob-3" /><div className="blob blob-4" />
      </div>

      {/* ══ INTRO / LANDING PAGE ══════════════════════════════════════════════ */}
      {showIntro && (
        <div className={`intro-screen${introFading ? " fading" : ""}`}>
          <div className="intro-scroll" ref={introScrollRef}>
            <nav className="intro-nav">
              <div className="intro-nav-logo">
                <div className="intro-nav-mark">
                  <img src="/ilyon-logo.svg" alt="Ilyon AI" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
                </div>
                <span className="intro-nav-name">Ilyon AI</span>
                <span className="intro-nav-badge">BETA</span>
              </div>
              {authUser
                ? <button className="intro-nav-enter" onClick={launchApp}>Enter App →</button>
                : <button className="intro-nav-enter" onClick={() => setShowAuth(true)}>Sign In →</button>
              }
            </nav>

            <section className="intro-hero">
              <div className="intro-hero-eyebrow">
                <span className="intro-hero-dot" />AI-Powered DeFi on Solana + leading EVM chains
              </div>
              <h1 className="intro-hero-headline">
                <span className="line1">Trade Smarter.</span>
                <span className="line2">Earn More.</span>
              </h1>
              <p className="intro-hero-sub">
                A Solana-forward AI DeFi gateway that also speaks fluent EVM. Ask anything in plain language —
                swap tokens, check balances, and manage your portfolio without leaving the chat.
              </p>
              <div className="intro-hero-btns">
                <button className="intro-btn-primary" onClick={launchApp}>Launch App <span>→</span></button>
                <button className="intro-btn-secondary" onClick={scrollToFeatures}>See Features ↓</button>
              </div>
              <div className="intro-stats-row">
                {INTRO_STATS.map(s => (
                  <div key={s.label} className="intro-stat-item">
                    <div className="intro-stat-val">{s.value}</div>
                    <div className="intro-stat-label">{s.label}</div>
                    <div className="intro-stat-sub">{s.sub}</div>
                  </div>
                ))}
              </div>
            </section>

            <section className="intro-section" id="intro-features">
              <div className="intro-section-tag">Features</div>
              <h2 className="intro-section-title">Everything you need<br />to DeFi smarter</h2>
              <p className="intro-section-sub">One unified interface that connects the best protocols across Solana and the leading EVM ecosystems.</p>
              <div className="intro-feat-grid">
                {PLATFORM_FEATURES.map(f => (
                  <div key={f.title} className="intro-feat-card">
                    <div className="intro-feat-icon">{f.icon}</div>
                    <div className="intro-feat-title">{f.title}</div>
                    <div className="intro-feat-desc">{f.desc}</div>
                  </div>
                ))}
              </div>
            </section>

            <section className="intro-section intro-how-bg">
              <div className="intro-section-tag">How It Works</div>
              <h2 className="intro-section-title">Three steps to smarter trades</h2>
              <p className="intro-section-sub">No documentation needed. No complex interfaces. Just chat.</p>
              <div className="intro-steps">
                {HOW_STEPS.map((step, i) => (
                  <React.Fragment key={step.num}>
                    <div className="intro-step">
                      <div className="intro-step-num">STEP {step.num}</div>
                      <div className="intro-step-icon">{step.icon}</div>
                      <div className="intro-step-title">{step.title}</div>
                      <div className="intro-step-desc">{step.desc}</div>
                    </div>
                    {i < HOW_STEPS.length - 1 && <div className="intro-step-arrow">→</div>}
                  </React.Fragment>
                ))}
              </div>
            </section>

            <section className="intro-section">
              <div className="intro-section-tag">Integrations</div>
              <h2 className="intro-section-title">Powered by the best protocols</h2>
              <p className="intro-section-sub" style={{ marginBottom: 48 }}>Ilyon AI Beta integrates directly with 15+ industry-leading protocols across DeFi, data, and AI.</p>
              {(() => {
                const categories = Array.from(new Set(PARTNERS.map(p => p.category)));
                return categories.map(cat => (
                  <div key={cat} className="intro-partners-section">
                    <div className="intro-partners-category">{cat}</div>
                    <div className="intro-partners-grid">
                      {PARTNERS.filter(p => p.category === cat).map(p => (
                        <div key={p.name} className="intro-partner">
                          {p.logo ? (
                            <img 
                              src={p.logo} 
                              alt={p.name} 
                              className="intro-partner-logo"
                              style={{ width: p.logoSize, height: p.logoSize }}
                              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                            />
                          ) : (
                            <span style={{ fontSize: 32, marginBottom: 12 }}>{p.icon}</span>
                          )}
                          <div className="intro-partner-name">{p.name}</div>
                          <div className="intro-partner-desc">{p.desc}</div>
                          <div className="intro-partner-category-tag">{p.category}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ));
              })()}
            </section>

            <section className="intro-bottom-cta">
              <div className="intro-cta-glow" />
              <div className="intro-cta-content">
                <h2 className="intro-cta-title">Ready to trade smarter?</h2>
                <p className="intro-cta-sub">Start with Solana, bridge into EVM, and manage both from one AI-native DeFi workspace.</p>
                <button className="intro-btn-primary" onClick={launchApp}>Launch App → Free to use</button>
                <p className="intro-cta-terms">Non-custodial &nbsp;·&nbsp; No sign-up &nbsp;·&nbsp; Open source</p>
              </div>
            </section>

            <footer className="intro-footer">
              <div>© 2025 Ilyon AI Beta · Solana + Multi-Chain DeFi AI</div>
              <div className="intro-footer-links">
                <span className="intro-footer-link" onClick={launchApp}>Launch App</span>
                <span className="intro-footer-link">GitHub</span>
                <span className="intro-footer-link">Docs</span>
                <span className="intro-footer-link">Twitter</span>
              </div>
            </footer>
          </div>
        </div>
      )}

      {/* ══ AUTH SCREEN ════════════════════════════════════════════════════════ */}
      <AnimatePresence>
        {showAuth && (
          <motion.div key="auth" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <AuthScreen
              onAuth={handleAuthSuccess}
              onClose={authUser ? () => setShowAuth(false) : undefined}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ══ MAIN APP ══════════════════════════════════════════════════════════ */}
      <div className="app">
        {/* ── Chat List Panel ──────────────────────────────────────────────── */}
        <AnimatePresence>
          {showChatList && (
            <ChatListPanel
              chats={chatList}
              currentChatId={currentChatId}
              onSelect={handleSelectChat}
              onCreate={handleNewChat}
              onDelete={handleDeleteChat}
              onClose={() => setShowChatList(false)}
            />
          )}
        </AnimatePresence>

        {/* ── Sidebar ─────────────────────────────────────────────────────── */}
        <aside className="sidebar">
          <div className="sidebar-logo" onClick={openIntro} style={{ cursor: "pointer" }} title="Back to intro">
            <div className="logo-mark">
              <img src="/ilyon-logo.svg" alt="Ilyon AI" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
            </div>
            <div>
              <div className="logo-text">Ilyon AI Beta</div>
              <div className="logo-sub">Sentinel-style Multi-Chain DeFi AI</div>
            </div>
          </div>

          <div className="sidebar-nav">
            {SIDEBAR_GROUPS.map(group => (
              <div key={group.title} className="sidebar-group">
                <div className="sidebar-group-title">{group.title}</div>
                {group.items.map(item => {
                  const active = item.key ? activeTab === item.key : false;
                  const interactive = Boolean(item.key);
                  return (
                    <button
                      key={`${group.title}-${item.label}`}
                      className={`sidebar-nav-item${active ? " active" : ""}${!interactive ? " disabled" : ""}`}
                      onClick={interactive ? () => setActiveTab(item.key as Tab) : undefined}
                      type="button"
                    >
                      <span className="sidebar-nav-icon">{item.icon}</span>
                      <span>{item.label}</span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>

          <div className="wallet-section">
            <div className="wallet-card">
              <div className="wallet-label">
                {walletType === "phantom" ? "👻 Phantom" : "🦊 MetaMask"}
              </div>
              <div className="wallet-address">
                {walletType === "phantom" && solDisplayAddr
                  ? `${solDisplayAddr.slice(0,6)}…${solDisplayAddr.slice(-4)}`
                  : connectedWallet
                    ? `${connectedWallet.slice(0,6)}…${connectedWallet.slice(-4)}`
                    : "Not connected"}
              </div>
              {(connectedWallet || solanaWallet) ? (
                <button className="disconnect-btn" style={{ width: "100%", marginTop: 6 }} onClick={disconnectWallet}>
                  ✕ Disconnect
                </button>
              ) : (
                <button className="connect-btn" onClick={() => setShowAuth(true)}>
                  <span>🔗</span> Connect Wallet
                </button>
              )}
            </div>
          </div>

          <div className="tokens-section">
            <div className="section-label">Market</div>
            {TOKENS.map(t => (
              <div key={t.symbol} className="token-row" onClick={() => send(`Show me ${t.symbol} price and market data`)}>
                <div className="token-left">
                  <div className="token-icon" style={{ background: t.grad }}>{t.icon}</div>
                  <div><div className="token-sym">{t.symbol}</div><div className="token-net">{t.name}</div></div>
                </div>
                <div className="token-right">
                  <div className="token-amt">{t.price}</div>
                  <div className={`token-change ${t.pos ? "change-pos" : t.change === "0.0%" ? "change-neu" : "change-neg"}`}>
                    {t.pos ? "▲" : t.change === "0.0%" ? "●" : "▼"} {t.change}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="greenfield-row">
            <div className="status-dot purple" />
            <span className="greenfield-icon">🌿</span>
            <span className="greenfield-label">Greenfield Memory</span>
            <span className="greenfield-badge">Active</span>
          </div>

          {authUser ? (
            <>
              <div className="user-row">
                <div className="user-avatar">{(authUser.display_name?.[0] ?? "?").toUpperCase()}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="user-name">{authUser.display_name}</div>
                  <div className="user-badge">{authUser.wallet_address?.slice(0,6)}…{authUser.wallet_address?.slice(-4)}</div>
                </div>
              </div>
              <div className="chat-controls">
                <button className="chat-ctrl-btn primary" onClick={handleNewChat} title="Start a new chat">
                  ✏️ New Chat
                </button>
                <button className="chat-ctrl-btn" onClick={() => setShowChatList(p => !p)} title="All chats">
                  💬 Chats {chatList.length > 0 && `(${chatList.length})`}
                </button>
              </div>
            </>
          ) : null}

          <div className="sidebar-footer">
            <div className="status-row">
              <div className={`status-dot ${dotClass}`} />
              <span>{dotText}</span>
            </div>
            <div className="footer-right">
              {authUser
                ? <button className="about-btn" onClick={handleLogout} title="Sign out">↩ Sign out</button>
                : <button className="about-btn" onClick={openIntro} title="View platform introduction">ℹ About</button>
              }
              <span className="version">v0.1</span>
            </div>
          </div>
        </aside>

        {/* ── Main Content ─────────────────────────────────────────────────── */}
        <main className="main">
          <div className="ticker-bar">
            <div className="ticker-track">
              {tickerFull.map((item, i) => (
                <div key={i} className="ticker-item">
                  <span className="ticker-sym">{item.sym}</span>
                  <span className="ticker-price">{item.price}</span>
                  <span className={`ticker-chg ${item.pos ? "pos" : item.change === "0.0%" ? "neu" : "neg"}`}>
                    {item.pos ? "▲" : item.change === "0.0%" ? "●" : "▼"} {item.change}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="content-canvas">
            <div className="public-testing-banner">
              <span>⚠️ Public testing — report bugs to Telegram <a href="https://t.me/griffiniskid" target="_blank" rel="noopener noreferrer">@griffiniskid</a></span>
            </div>
            <div className="top-banner">
              <div className="top-banner-label" data-agent-build="sentinel-v2-streaming-live">
                <span>✦</span>
                <span>Sentinel Agent v2 live · Real streaming reasoning · Typed execution cards</span>
              </div>
              <div className="top-banner-chip">LIVE NOW</div>
            </div>

            {/* ── Tab Panels ─────────────────────────────────────────────── */}
            <div className="tab-panel">
            <AnimatePresence mode="wait">

              {/* Dashboard */}
              {activeTab === "dashboard" && (
                <motion.div key="dashboard" className="dash" variants={fadeUp} initial="hidden" animate="show">
                  <div className="overview-shell page-shell">
                    <section className="overview-hero">
                      <div className="hero-copy">
                        <div className="hero-pill"><span>✦</span> Unified Token + Pool Analysis</div>
                        <h1 className="hero-heading">
                          Analyze Every
                          <span className="accent">Token And Pool</span>
                        </h1>
                        <p className="hero-sub">
                          Paste any token or pool address or name to open a full risk report. Review token safety,
                          pool sustainability, exit quality, and AI context from one search surface.
                        </p>
                        <div className="hero-search">
                          <span style={{ color: "#94a3b8", fontSize: 26, lineHeight: 1 }}>⌕</span>
                          <input
                            value={overviewSearch}
                            onChange={(e) => setOverviewSearch(e.target.value)}
                            placeholder="Paste any token or pool address"
                          />
                          <button
                            className="hero-search-btn"
                            onClick={() => {
                              if (!overviewSearch.trim()) return;
                              setActiveTab("chat");
                              setTimeout(() => send(overviewSearch), 100);
                            }}
                          >
                            Analyze →
                          </button>
                        </div>
                        <div className="hero-chain-row">
                          <span className="hero-chain-label">Chain:</span>
                          {OVERVIEW_CHAINS.map(chain => (
                            <span key={chain.label} className="hero-chain-pill">
                              <span className="hero-chain-dot" style={{ background: chain.color }} />
                              {chain.label}
                            </span>
                          ))}
                        </div>
                        <div className="hero-footer-row">
                          {[
                            "Free to use",
                            "No signup required",
                            "Token + pool reports",
                          ].map(item => (
                            <div key={item} className="hero-footer-item"><span className="check">◉</span>{item}</div>
                          ))}
                        </div>
                      </div>

                      <div className="hero-preview">
                        <div className="preview-card">
                          <div className="preview-card-head">
                            <div className="preview-card-title">
                              <div className="preview-avatar">T</div>
                              <div>
                                <div className="preview-card-name">Token Analysis</div>
                                <div className="preview-card-sub">Example Output</div>
                              </div>
                            </div>
                            <div className="preview-score">
                              <div className="preview-score-badge">Demo</div>
                              <div className="preview-score-value">85</div>
                              <div className="preview-card-sub">Safety Score</div>
                            </div>
                          </div>

                          <div className="preview-ring-wrap">
                            <div className="preview-ring">
                              <div style={{ fontSize: 26 }}>85</div>
                              <small>SAFE</small>
                            </div>
                          </div>

                          <div className="preview-checks">
                            <div className="preview-check-item"><span>Mint Authority</span><span className="preview-check-state success">◉</span></div>
                            <div className="preview-check-item success"><span>Freeze Authority</span><span className="preview-check-state success">◉</span></div>
                            <div className="preview-check-item warn"><span>LP Locked</span><span className="preview-check-state warn">△</span></div>
                            <div className="preview-check-item"><span>Top 10 Holders</span><span className="preview-check-state success">◉</span></div>
                          </div>
                        </div>
                      </div>
                    </section>

                    <section className="dashboard-lower">
                      {[
                        { icon: "⌕", label: "Overview", desc: "Start from token or pool research", action: () => setActiveTab("chat") },
                        { icon: "⌁", label: "Chat", desc: "Natural language execution surface", action: () => setActiveTab("chat") },
                        { icon: "◔", label: "Portfolio", desc: "Balances and chain-level exposure", action: () => setActiveTab("portfolio") },
                        { icon: "⇄", label: "Swap", desc: "Compose and route live swaps", action: () => setActiveTab("swap") },
                      ].map(a => (
                        <div key={a.label} className="action-card" onClick={a.action}>
                          <div className="action-card-icon">{a.icon}</div>
                          <div className="action-card-label">{a.label}</div>
                          <div className="action-card-desc">{a.desc}</div>
                        </div>
                      ))}
                    </section>
                  </div>
                </motion.div>
              )}

              {/* Chat */}
              {activeTab === "chat" && (
                <MotionDiv key="chat" className="chat-wrap" variants={slideIn} initial="hidden" animate="show">
                  <div className="page-shell chat-page-shell">
                    <div className="chat-shell-head">
                      <span className="chat-shell-title">
                        {currentChatId
                          ? (chatList.find(c => c.id === currentChatId)?.title ?? "Chat")
                          : "New Chat"}
                      </span>
                      <div className="chat-shell-actions">
                        <button className="chat-shell-btn primary" onClick={handleNewChat}>✦ New</button>
                        <button className="chat-shell-btn" onClick={() => setShowChatList(p => !p)}>◫ {chatList.length > 0 ? `${chatList.length} chats` : "Chats"}</button>
                      </div>
                    </div>

                    <div className="messages" ref={messagesRef}>
                    {isFirstChat && (
                      <motion.div className="cap-grid" variants={fadeUp} initial="hidden" animate="show">
                        {CAPABILITIES.map(c => (
                          <div key={c.title} className="cap-card" onClick={() => send(c.prompt)}>
                            <div className="cap-icon">{c.icon}</div>
                            <div>
                              <div className="cap-title">{c.title}</div>
                              <div className="cap-desc">{c.desc}</div>
                            </div>
                          </div>
                        ))}
                      </motion.div>
                    )}

                    {messages.map(msg => {
                      // Resolve structured data: use pre-stored value OR parse inline from text
                      // This makes rendering bullet-proof even if storage-time parsing failed
                      const msgText = msg.text ?? "";
                      const resolvedSwap    = msg.swapPreview    ?? (msg.role === "assistant" ? parseSwapPreview(msgText)    : null);
                      const resolvedCompound = msg.compoundData  ?? (msg.role === "assistant" ? parseCompoundAction(msgText) : null);
                      const resolvedBalance = msg.balanceData    ?? (msg.role === "assistant" ? parseBalanceData(msgText)    : null);
                      const resolvedPool    = msg.poolData       ?? (msg.role === "assistant" ? parseLiquidityPool(msgText)  : null);
                      const resolvedAgentCards = msg.role === "assistant" && msg.agentCards?.length ? orderAgentCards(msg.agentCards) : [];
                      const resolvedCards   = resolvedAgentCards.length ? null : (msg.universalCards ?? (msg.role === "assistant" ? parseUniversalCards(msgText) : null));
                      const looksLikeTxJson = msg.role === "assistant" && (
                        msgText.includes('"type":"evm_action_proposal"') ||
                        msgText.includes('\\"type\\":\\"evm_action_proposal\\"') ||
                        msgText.includes('"swapTransaction"') ||
                        msgText.includes('\\"swapTransaction\\"') ||
                        msgText.includes('"serialized"') ||
                        msgText.includes('"compound_action"') ||
                        (msgText.includes('"status":"ok"') && msgText.includes('"tx"'))
                      );
                      const isStructured    = !!(resolvedSwap || resolvedCompound || resolvedBalance || resolvedPool || resolvedCards || looksLikeTxJson);

                      return (
                      <MotionDiv
                        key={msg.id}
                        className={`msg-row ${msg.role}`}
                        variants={msg.role === "user" ? slideIn : fadeUp}
                        initial="hidden"
                        animate="show"
                      >
                        <div className={`msg-avatar ${msg.role}`}>{msg.role === "user" ? "U" : "A"}</div>
                        <div className="msg-body">
                          <div className={`msg-bubble ${msg.role}`}>
                            {msg.role === "assistant" && resolvedCompound
                              ? <MarkdownText text={resolvedCompound.message} />
                              : msg.role === "assistant" && resolvedSwap
                              ? resolvedSwap.isTransfer
                                ? (() => { const addr = resolvedSwap.transferTo ?? ""; const short = addr.length > 10 ? `${addr.slice(0,6)}…${addr.slice(-4)}` : addr; return `✅ Transfer: ${resolvedSwap.fromAmount} ${resolvedSwap.fromToken} → ${short}. Review and confirm below.`; })()
                                : resolvedSwap.isBridge
                                  ? `✅ Bridge prepared from ${resolvedSwap.sourceChainLabel ?? "source chain"} to ${resolvedSwap.destinationChainLabel ?? "destination chain"}. Review and confirm below.`
                                  : `✅ ${resolvedSwap.actionType === "stake" ? "Staking" : resolvedSwap.actionType === "add_liquidity" ? "Liquidity" : "Swap"} transaction prepared. Review and confirm below.`
                              : msg.role === "assistant" && looksLikeTxJson
                                ? "✅ Transaction prepared. Rendering structured preview..."
                              : msg.role === "assistant" && resolvedBalance
                                ? "Here are your wallet balances:"
                                : msg.role === "assistant" && resolvedPool
                                  ? "🌊 Liquidity pool found:"
                                  : msg.role === "assistant" && resolvedCards
                                    ? (resolvedCards.message || "🔍 Here are the results:")
                                    : isStructured ? null : msg.role === "assistant" ? <MarkdownText text={msg.text} /> : <span>{msg.text}</span>}
                          </div>

                          {/* Reasoning Accordion */}
                          {msg.role === "assistant" && msg.reasoning && msg.id !== 0 && (
                            <ReasoningAccordion
                              steps={msg.reasoning}
                              isOpen={openReasoning === msg.id}
                              onToggle={() => setOpenReasoning(openReasoning === msg.id ? null : msg.id)}
                            />
                          )}

                          {/* Simulation Preview (for swap / transfer responses) */}
                          {msg.role === "assistant" && resolvedSwap && (
                            <SimulationPreview preview={resolvedSwap} fromAddress={connectedWallet} solanaAddress={solanaWallet} walletType={walletType} />
                          )}

                          {msg.role === "assistant" && resolvedCompound && resolvedCompound.previews.map((preview, index) => (
                            <SimulationPreview key={`${msg.id}-${index}`} preview={preview} fromAddress={connectedWallet} solanaAddress={solanaWallet} walletType={walletType} />
                          ))}

                          {/* Liquidity Pool Card */}
                          {msg.role === "assistant" && resolvedPool && (
                            <LiquidityPoolCard data={resolvedPool} />
                          )}

                          {/* Balance Card (for balance report responses) */}
                          {msg.role === "assistant" && resolvedBalance && (
                            <BalanceCard data={resolvedBalance} />
                          )}

                          {/* Typed Agent Cards (allocation, Sentinel matrix, execution plan, swap/bridge/stake, etc.) */}
                          {msg.role === "assistant" && resolvedAgentCards.length > 0 && (
                            <div className="space-y-3 mt-3">
                              {resolvedAgentCards.map((card) => (
                                <CardRenderer key={card.card_id} card={card} onStartSigning={handleStartSigning} onRerunAllocation={handleRerunAllocation} onSignStep={handleSignStep} />
                              ))}
                            </div>
                          )}

                          {/* Universal Cards (DexScreener pairs, token lists, etc.) */}
                          {msg.role === "assistant" && resolvedCards && (
                            <UniversalCardList data={resolvedCards} />
                          )}

                          <div className="msg-ts">{fmt(msg.ts)}</div>
                        </div>
                      </MotionDiv>
                      );
                    })}

                    {executionNotice && (
                      <MotionDiv className="msg-row assistant" variants={fadeUp} initial="hidden" animate="show">
                        <div className="msg-avatar assistant">A</div>
                        <div className="msg-body">
                          <div className="execution-notice-card">
                            <div className="execution-notice-title">{executionNotice.title}</div>
                            <div className="execution-notice-sub">{executionNotice.body}</div>
                            {executionNotice.steps && (
                              <div className="execution-notice-steps">
                              {executionNotice.steps.map(step => (
                                <div key={step.index} className="execution-notice-step">
                                  <span className="execution-notice-index">{step.index}</span>
                                  <span>{step.verb} {step.amount} {step.asset}</span>
                                  <span className="execution-notice-meta">{step.wallet} · {step.gas}</span>
                                </div>
                              ))}
                            </div>
                            )}
                          </div>
                        </div>
                      </MotionDiv>
                    )}

                    {/* Loading state with live reasoning steps */}
                    {loading && (
                      <MotionDiv
                        className="msg-row assistant"
                        variants={fadeUp}
                        initial="hidden"
                        animate="show"
                      >
                        <div className="msg-avatar assistant">A</div>
                        <div>
                          {liveSteps.length === 0 ? (
                            <div className="typing-bubble">
                              <div className="typing-dot" /><div className="typing-dot" /><div className="typing-dot" />
                            </div>
                          ) : (
                            <div className="reasoning-live">
                              <div className="reasoning-live-title">Agent Reasoning</div>
                              {liveSteps.map((step, i) => {
                                const isLast = i === liveSteps.length - 1;
                                const allShown = liveSteps.length >= totalSteps && totalSteps > 0;
                                // last step is "active" only while more steps are pending;
                                // once all steps shown, mark all as "done" and show waiting row
                                const state = (!allShown && isLast) ? "active" : "done";
                                return (
                                  <motion.div
                                    key={step.id}
                                    className={`reasoning-live-step ${state}`}
                                    initial={{ opacity: 0, x: -6 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ duration: 0.2 }}
                                  >
                                    <div className="reasoning-live-step-dot" />
                                    <span className="reasoning-live-step-text">
                                      {STEP_ICONS[step.type]} {step.label}
                                      {step.detail && <span style={{ opacity: 0.5, marginLeft: 6, fontSize: 10 }}>{step.detail}</span>}
                                    </span>
                                  </motion.div>
                                );
                              })}
                              {/* Show waiting row once all steps are rendered but AI hasn't responded yet */}
                              <AnimatePresence>
                                {liveSteps.length >= totalSteps && totalSteps > 0 && (
                                  <motion.div
                                    className="reasoning-live-waiting"
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    transition={{ duration: 0.3 }}
                                  >
                                    <div className="typing-dot" />
                                    <div className="typing-dot" />
                                    <div className="typing-dot" />
                                    <span>Awaiting AI response…</span>
                                  </motion.div>
                                )}
                              </AnimatePresence>
                            </div>
                          )}
                        </div>
                      </MotionDiv>
                    )}

                  </div>

                    <div className="chat-composer">
                      <div className="quick-bar">
                        {QUICK_PROMPTS.map(p => (
                          <button key={p} className="quick-chip" onClick={() => send(p)}>{p}</button>
                        ))}
                      </div>

                      <div className="input-area">
                        <div className="input-row">
                          <textarea
                            ref={textareaRef}
                            className="msg-input"
                            rows={1}
                            placeholder="Ask anything about Solana, swaps, bridges, or portfolio…"
                            value={input}
                            onChange={handleInputChange}
                            onKeyDown={handleKey}
                            disabled={loading}
                          />
                          <button
                            className={`send-btn ${input.trim() && !loading ? "active" : "inactive"}`}
                            onClick={() => send(input)}
                            disabled={!input.trim() || loading}
                          >↑</button>
                        </div>
                        <div className="input-hint">Enter — send &nbsp;·&nbsp; Shift+Enter — new line</div>
                      </div>
                    </div>
                  </div>
                </MotionDiv>
              )}

              {/* Portfolio */}
              {activeTab === "portfolio" && (
                <motion.div key="portfolio" className="page" variants={fadeUp} initial="hidden" animate="show">
                  <div className="page-shell">
                  <div className="page-title">Portfolio</div>
                  <div className="page-sub">
                    {(connectedWallet || solDisplayAddr)
                      ? <>Connected: <span style={{ color: "#34D399", fontFamily: "'JetBrains Mono', monospace" }}>{(connectedWallet || solDisplayAddr)!.slice(0,6)}…{(connectedWallet || solDisplayAddr)!.slice(-4)}</span></>
                      : "Track your assets and performance across all chains"}
                  </div>

                  {/* ── Stats ── */}
                  <div className="stats-grid">
                    {[
                      {
                        label: "Total Balance",
                        value: (connectedWallet || solanaWallet)
                          ? (balanceUnit === "USD"
                              ? `$${portfolioTotalUsd.toFixed(2)}`
                              : `${(walletType === "phantom" ? solPriceUsd : bnbPriceUsd) > 0 ? (portfolioTotalUsd / (walletType === "phantom" ? solPriceUsd : bnbPriceUsd)).toFixed(4) : "—"} ${walletType === "phantom" ? "SOL" : "BNB"}`)
                          : "—",
                        icon: "💼", cls: "gold",
                      },
                      {
                        label: walletType === "phantom" ? "SOL Price" : "BNB Price",
                        value: walletType === "phantom"
                          ? (solPriceUsd > 0 ? `$${solPriceUsd.toFixed(2)}` : "—")
                          : (bnbPriceUsd > 0 ? `$${bnbPriceUsd.toFixed(2)}` : "—"),
                        icon: "📈", cls: "green",
                      },
                      {
                        label: "Tokens",
                        value: (connectedWallet || solanaWallet) ? `${new Set(portfolioTokens.map(t => t.symbol?.toUpperCase())).size}` : "—",
                        icon: "🪙", cls: "blue",
                      },
                    ].map(c => (
                      <div key={c.label} className={`stat-card ${c.cls}`}>
                        <div className="stat-icon">{c.icon}</div>
                        <div className="stat-value">{c.value}</div>
                        <div className="stat-label">{c.label}</div>
                      </div>
                    ))}
                  </div>

                  {!connectedWallet && !solanaWallet ? (
                    <div className="portfolio-empty">
                      <div className="portfolio-empty-icon">🔗</div>
                      <div className="portfolio-empty-title">No wallet connected</div>
                      <div className="portfolio-empty-sub">Connect your wallet to see real-time balances across all supported chains.</div>
                      <button className="portfolio-empty-btn" onClick={() => connectWallet()}>Connect Wallet</button>
                    </div>
                  ) : (
                    <>
                      {/* Unit toggle + refresh */}
                      {(() => {
                        const nativeSym = walletType === "phantom" ? "SOL" : "BNB";
                        const chainName = "All Chains";
                        const doRefresh = () => {
                          const wallet = walletType === "phantom"
                            ? buildPhantomPortfolioAddress(solanaWallet, connectedWallet)
                            : connectedWallet;
                          if (!wallet) return;
                          setPortfolioLoading(true);
                          setPortfolioError(null);
                          fetchPortfolio(wallet)
                            .then(({ tokens, totalUsd, nativePrice, solPrice }) => {
                              setPortfolioTokens(tokens);
                              setPortfolioTotalUsd(totalUsd);
                              setBnbPriceUsd(nativePrice);
                              setSolPriceUsd(solPrice);
                              const nt = tokens.find(t => t.symbol === nativeSym || t.symbol === "ETH" || t.symbol === "SOL");
                              if (nt) setNativeBalance(nt.balance);
                            })
                            .catch(err => setPortfolioError(String(err)))
                            .finally(() => setPortfolioLoading(false));
                        };
                        return (
                          <>
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                                {(["USD", "native"] as const).map(u => (
                                  <button key={u} onClick={() => setBalanceUnit(u)} style={{
                                    padding: "5px 14px", borderRadius: 8, fontSize: 12, fontWeight: 700, fontFamily: "inherit", cursor: "pointer",
                                    background: balanceUnit === u ? "rgba(16,185,129,0.12)" : "rgba(15,23,42,0.72)",
                                    border: balanceUnit === u ? "1px solid rgba(16,185,129,0.28)" : "1px solid rgba(255,255,255,0.08)",
                                    color: balanceUnit === u ? "#34D399" : "rgba(226,232,240,0.55)",
                                  }}>{u === "USD" ? "USD" : nativeSym}</button>
                                ))}
                                <span style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", marginLeft: 4 }}>{chainName}</span>
                              </div>
                              <button onClick={doRefresh} style={{ padding: "5px 12px", borderRadius: 999, fontSize: 12, fontFamily: "inherit", cursor: "pointer", background: "rgba(15,23,42,0.72)", border: "1px solid rgba(255,255,255,0.08)", color: "rgba(226,232,240,0.58)" }}>
                                {portfolioLoading ? "⏳" : "🔄 Refresh"}
                              </button>
                            </div>
                            {portfolioError && (
                              <div style={{ background: "rgba(248,113,113,0.12)", border: "1px solid rgba(248,113,113,0.28)", borderRadius: 12, padding: "10px 14px", fontSize: 12, color: "#FCA5A5", marginBottom: 12 }}>
                                ❌ {portfolioError}
                              </div>
                            )}
                          </>
                        );
                      })()}

                      {/* Token list */}
                      <div className="portfolio-table">
                        <div className="table-head">
                          <span>Token</span><span>Price</span><span>Balance</span><span>Value</span>
                        </div>
                        {portfolioLoading && portfolioTokens.length === 0 ? (
                          <div style={{ textAlign: "center", padding: "32px 0", color: "rgba(255,255,255,0.3)", fontSize: 13 }}>
                            ⏳ Loading balances across all chains…
                          </div>
                        ) : portfolioTokens.length === 0 ? (
                          <div style={{ textAlign: "center", padding: "32px 0", color: "rgba(255,255,255,0.3)", fontSize: 13 }}>
                            No tokens found across supported chains
                          </div>
                        ) : (
                          Object.values(
                            portfolioTokens.reduce((acc: Record<string, PortfolioToken>, t) => {
                              const k = `${(t.symbol ?? "UNKNOWN").toUpperCase()}-${t.chainName ?? ""}`;
                              if (!acc[k]) acc[k] = t;
                              return acc;
                            }, {})
                          ).map(t => (
                            <div key={`${t.symbol}-${t.chainName}`} className="table-row">
                              <div className="table-token">
                                <div className="table-icon" style={{ background: t.grad }}>{t.icon}</div>
                                <div><div className="table-sym">{t.symbol}</div><div className="table-name">{t.name} <span style={{opacity: 0.5, fontSize: "0.8em"}}>({t.chainName})</span></div></div>
                              </div>
                              <span className="table-cell">{t.price > 0 ? `$${t.price.toFixed(2)}` : "—"}</span>
                              <span className="table-cell">{t.balance}</span>
                              <span className="table-cell" style={{ color: t.valueUsd > 0 ? "#34D399" : "rgba(255,255,255,0.25)" }}>
                                {balanceUnit === "USD"
                                  ? `$${(t.valueUsd ?? 0).toFixed(2)}`
                                  : ((walletType === "phantom" ? solPriceUsd : bnbPriceUsd) > 0 && t.valueUsd > 0 ? `${(t.valueUsd / (walletType === "phantom" ? solPriceUsd : bnbPriceUsd)).toFixed(4)} ${walletType === "phantom" ? "SOL" : "BNB"}` : "$0.00")}
                              </span>
                            </div>
                          ))
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: "rgba(255,255,255,0.2)", textAlign: "center", paddingTop: 10 }}>
                        Showing known tokens only · Tokens with unknown price show balance but $0 value
                      </div>
                    </>
                  )}
                  </div>
                </motion.div>
              )}

              {/* Swap */}
              {activeTab === "swap" && (
                <motion.div key="swap" variants={scaleIn} initial="hidden" animate="show" style={{ flex: 1, overflowY: "auto", padding: "24px 24px 40px" }}>
                  <div className="page-shell swap-grid">
                    <div style={{
                      background: "rgba(15,23,42,0.72)",
                      border: "1px solid rgba(255,255,255,0.08)",
                      borderRadius: 24,
                      padding: 24,
                      backdropFilter: "blur(22px)",
                      boxShadow: "0 24px 80px rgba(0,0,0,0.32)",
                    }}>
                      <div style={{ marginBottom: 24 }}>
                        <div style={{ fontSize: 11, color: "#34D399", fontWeight: 800, letterSpacing: "0.18em", textTransform: "uppercase", marginBottom: 10 }}>AI Swap Composer</div>
                        <h2 style={{ color: "#fff", fontSize: 30, fontWeight: 800, letterSpacing: -1, margin: 0 }}>Compose a swap, then confirm in chat</h2>
                        <p style={{ color: "rgba(148,163,184,0.82)", fontSize: 14, marginTop: 8, lineHeight: 1.7 }}>
                          The composer estimates the route and then hands the trade to the AI execution flow with full wallet confirmation.
                        </p>
                      </div>

                      <div style={{
                        background: "rgba(8,15,28,0.82)", border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: 22, padding: "18px 20px", marginBottom: 10,
                      }}>
                        <div style={{ color: "rgba(148,163,184,0.85)", fontSize: 11, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.08em" }}>You Pay</div>
                        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                          <input
                            type="number"
                            placeholder="0.0"
                            value={swapFromAmount}
                            onChange={e => setSwapFromAmount(e.target.value)}
                            style={{
                              flex: 1, background: "none", border: "none", outline: "none",
                              color: "#F8FAFC", fontSize: 34, fontWeight: 800, fontFamily: "'JetBrains Mono', monospace",
                            }}
                          />
                          <div style={{
                            background: "rgba(255,255,255,0.06)", borderRadius: 16, padding: "10px 16px",
                            color: "#F8FAFC", fontWeight: 700, fontSize: 15, display: "flex", alignItems: "center", gap: 6,
                            border: "1px solid rgba(255,255,255,0.08)",
                          }}>
                            {swapFromToken}
                          </div>
                        </div>
                      </div>

                      <div style={{ display: "flex", justifyContent: "center", margin: "4px 0 10px" }}>
                        <button
                          onClick={() => { setSwapFromToken(swapToToken); setSwapToToken(swapFromToken); setSwapFromAmount(""); }}
                          style={{
                            background: "rgba(139,92,246,0.12)", border: "1px solid rgba(139,92,246,0.28)",
                            borderRadius: "50%", width: 42, height: 42, cursor: "pointer",
                            color: "#C4B5FD", fontSize: 18, display: "flex", alignItems: "center", justifyContent: "center",
                            boxShadow: "0 10px 25px rgba(0,0,0,0.18)",
                          }}
                        >⇅</button>
                      </div>

                      <div style={{
                        background: "rgba(8,15,28,0.82)", border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: 22, padding: "18px 20px", marginBottom: 16,
                      }}>
                        <div style={{ color: "rgba(148,163,184,0.85)", fontSize: 11, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.08em" }}>You Receive (Estimated)</div>
                        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                          <div style={{ flex: 1, color: swapQuote ? "#34D399" : "rgba(255,255,255,0.3)", fontSize: 34, fontWeight: 800, fontFamily: "'JetBrains Mono', monospace" }}>
                            {swapQuoteLoading ? "…" : swapQuote?.toAmount ?? "0.0"}
                          </div>
                          <div style={{
                            background: "rgba(255,255,255,0.06)", borderRadius: 16, padding: "10px 16px",
                            color: "#fff", fontWeight: 700, fontSize: 15, border: "1px solid rgba(255,255,255,0.08)",
                          }}>
                            {swapToToken}
                          </div>
                        </div>
                        {swapQuote && (
                          <div style={{ marginTop: 12, fontSize: 12, color: "rgba(196,181,253,0.9)", fontFamily: "'JetBrains Mono', monospace" }}>
                            1 {swapFromToken} ≈ {swapQuote.rate} {swapToToken} · {swapQuote.route}
                          </div>
                        )}
                      </div>

                      <div style={{ display: "flex", gap: 8, marginBottom: 18, flexWrap: "wrap" }}>
                        {([["BNB","USDT"],["ETH","USDC"],["SOL","USDC"],["BNB","ETH"]] as [string,string][]).map(([from, to]) => (
                          <button key={`${from}-${to}`}
                            onClick={() => { setSwapFromToken(from); setSwapToToken(to); }}
                            style={{
                              padding: "7px 14px", borderRadius: 999, fontSize: 12, fontWeight: 700,
                              background: swapFromToken === from && swapToToken === to ? "rgba(16,185,129,0.12)" : "rgba(15,23,42,0.76)",
                              border: `1px solid ${swapFromToken === from && swapToToken === to ? "rgba(16,185,129,0.28)" : "rgba(255,255,255,0.08)"}`,
                              color: swapFromToken === from && swapToToken === to ? "#34D399" : "rgba(226,232,240,0.62)",
                              cursor: "pointer", fontFamily: "inherit",
                            }}
                          >{from} → {to}</button>
                        ))}
                      </div>

                      {!connectedWallet && !solanaWallet ? (
                        <button onClick={() => setShowAuth(true)} style={{
                          width: "100%", padding: "16px", borderRadius: 16, border: "none",
                          background: "linear-gradient(135deg,#10b981,#34d399)",
                          color: "#03150f", fontSize: 16, fontWeight: 800, cursor: "pointer", fontFamily: "inherit",
                          boxShadow: "0 14px 32px rgba(16,185,129,0.22)",
                        }}>Connect Wallet to Swap</button>
                      ) : (
                        <button
                          onClick={() => {
                            if (!swapFromAmount || parseFloat(swapFromAmount) <= 0) {
                              showToast("Enter an amount to swap", "error"); return;
                            }
                            setActiveTab("chat");
                            const query = `Swap ${swapFromAmount} ${swapFromToken} for ${swapToToken}`;
                            setTimeout(() => send(query), 100);
                          }}
                          style={{
                            width: "100%", padding: "16px", borderRadius: 16, border: "none",
                            background: swapQuoteLoading ? "rgba(16,185,129,0.45)" : "linear-gradient(135deg,#10b981,#34d399)",
                            color: "#03150f", fontSize: 16, fontWeight: 800, cursor: "pointer",
                            opacity: swapQuoteLoading ? 0.7 : 1, fontFamily: "inherit",
                            boxShadow: "0 14px 32px rgba(16,185,129,0.22)",
                          }}
                        >
                          {swapQuoteLoading ? "Getting quote…" : `Swap ${swapFromToken} → ${swapToToken}`}
                        </button>
                      )}
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                      <div style={{
                        background: "rgba(15,23,42,0.72)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: 22,
                        padding: 18,
                        backdropFilter: "blur(22px)",
                      }}>
                        <div style={{ fontSize: 11, color: "#C4B5FD", fontWeight: 800, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: 10 }}>Routing Layer</div>
                        <div style={{ fontSize: 20, fontWeight: 800, color: "#fff", marginBottom: 8 }}>Multi-engine execution</div>
                        <div style={{ fontSize: 13, color: "rgba(148,163,184,0.82)", lineHeight: 1.7 }}>
                          Enso handles EVM routing, Jupiter handles Solana swaps, and deBridge handles cross-chain routes. The AI chat remains the execution control room.
                        </div>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
                          {['Enso', 'Jupiter', 'deBridge'].map(label => (
                            <span key={label} style={{ padding: '6px 10px', borderRadius: 999, border: '1px solid rgba(139,92,246,0.22)', background: 'rgba(139,92,246,0.08)', color: '#C4B5FD', fontSize: 11, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace" }}>{label}</span>
                          ))}
                        </div>
                      </div>

                      <div style={{
                        background: "rgba(15,23,42,0.72)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: 22,
                        padding: 18,
                        backdropFilter: "blur(22px)",
                      }}>
                        <div style={{ fontSize: 11, color: "#34D399", fontWeight: 800, letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: 10 }}>Execution Notes</div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                          {[
                            'The final transaction is always reviewed in chat before wallet signing.',
                            'Platform fee remains 0.5% across Enso, Jupiter, and deBridge flows.',
                            'Technical route details use monospace styling once the AI prepares execution.',
                          ].map(note => (
                            <div key={note} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                              <span style={{ color: '#34D399', marginTop: 1 }}>●</span>
                              <span style={{ fontSize: 12, color: 'rgba(226,232,240,0.75)', lineHeight: 1.7 }}>{note}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          </div>
        </main>
      </div>

      {/* Toast notifications */}
      {toasts.length > 0 && (
        <div style={{
          position: "fixed", bottom: 24, right: 24, zIndex: 9999,
          display: "flex", flexDirection: "column", gap: 8, maxWidth: 320,
        }}>
          {toasts.map(t => (
            <div key={t.id} style={{
              padding: "12px 16px", borderRadius: 10, fontSize: 13, fontWeight: 600,
              background: t.type === "success" ? "rgba(74,222,128,0.15)" : t.type === "error" ? "rgba(248,113,113,0.15)" : "rgba(139,92,246,0.15)",
              border: `1px solid ${t.type === "success" ? "rgba(74,222,128,0.4)" : t.type === "error" ? "rgba(248,113,113,0.4)" : "rgba(139,92,246,0.4)"}`,
              color: t.type === "success" ? "#4ADE80" : t.type === "error" ? "#F87171" : "#A78BFA",
              backdropFilter: "blur(10px)",
              boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
            }}>
              {t.type === "success" ? "✅ " : t.type === "error" ? "❌ " : "ℹ️ "}{t.msg}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
