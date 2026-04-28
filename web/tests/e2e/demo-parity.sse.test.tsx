import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AgentMessage } from "@/hooks/useAgentStream";
import { MessageList } from "@/components/agent/MessageList";

vi.mock("next/navigation", () => ({
  usePathname: () => "/agent/chat",
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn() }),
}));

function demoMessages(): AgentMessage[] {
  const allocationPayload = {
    total_usd: "$10,000",
    blended_apy: "~5.6%",
    chains: 3,
    weighted_sentinel: 89,
    risk_mix: { low: 4, medium: 1, high: 0 },
    combined_tvl: "$31.2B",
    positions: [
      { rank: 1, protocol: "Lido", asset: "stETH", chain: "eth", apy: "3.1%", sentinel: 94, risk: "low", fit: "conservative", weight: 35, usd: "$3,500", tvl: "$24.5B", router: "Enso", safety: 96, durability: 92, exit: 98, confidence: 95, flags: [] },
      { rank: 2, protocol: "Rocket Pool", asset: "rETH", chain: "eth", apy: "2.9%", sentinel: 91, risk: "low", fit: "conservative", weight: 20, usd: "$2,000", tvl: "$3.4B", router: "Enso", safety: 93, durability: 89, exit: 91, confidence: 92, flags: ["Node operator set"] },
      { rank: 3, protocol: "Jito", asset: "JitoSOL", chain: "sol", apy: "7.2%", sentinel: 88, risk: "low", fit: "balanced", weight: 20, usd: "$2,000", tvl: "$2.1B", router: "Jupiter", safety: 89, durability: 87, exit: 85, confidence: 90, flags: ["MEV rebate dependency"] },
      { rank: 4, protocol: "Aave v3", asset: "aArbUSDC", chain: "arb", apy: "4.8%", sentinel: 90, risk: "low", fit: "balanced", weight: 15, usd: "$1,500", tvl: "$890M", router: "Enso", safety: 95, durability: 85, exit: 96, confidence: 88, flags: [] },
      { rank: 5, protocol: "Pendle", asset: "PT-sUSDe", chain: "mainnet", apy: "18.2%", sentinel: 71, risk: "medium", fit: "aggressive", weight: 10, usd: "$1,000", tvl: "$320M", router: "Enso", safety: 68, durability: 62, exit: 72, confidence: 82, flags: ["Fixed maturity", "Ethena dependency"] },
    ],
  };
  const matrixPayload = {
    ...allocationPayload,
    low_count: 4,
    medium_count: 1,
    high_count: 0,
    weighted_sentinel: 89,
  };
  const execPlanPayload = {
    tx_count: 5,
    total_gas: "~$17.16",
    slippage_cap: "0.5%",
    wallets: "MetaMask + Phantom",
    requires_signature: true,
    steps: [
      { index: 1, verb: "Stake", amount: "1.612", asset: "ETH", target: "stETH · Lido", chain: "eth", router: "Enso", wallet: "MetaMask", gas: "~$4.80" },
      { index: 2, verb: "Stake", amount: "0.921", asset: "ETH", target: "rETH · Rocket Pool", chain: "eth", router: "Enso", wallet: "MetaMask", gas: "~$5.10" },
      { index: 3, verb: "Liquid stake", amount: "22.32", asset: "SOL", target: "JitoSOL · Jito", chain: "sol", router: "Jupiter", wallet: "Phantom", gas: "~$0.01" },
      { index: 4, verb: "Supply", amount: "1,500", asset: "USDC", target: "aArbUSDC · Aave v3", chain: "arb", router: "Enso", wallet: "MetaMask", gas: "~$0.35" },
      { index: 5, verb: "Deposit", amount: "1,000", asset: "USDC", target: "PT-sUSDe · Pendle", chain: "mainnet", router: "Enso", wallet: "MetaMask", gas: "~$6.90" },
    ],
  };
  return [
    {
      role: "user",
      content: "I have $10,000 USDC. Allocate it across the best staking and yield opportunities, risk-weighted using Sentinel scores.",
      cards: [],
      thoughts: [],
      tools: [],
    },
    {
      role: "assistant",
      content:
        "Here's a risk-weighted allocation across 5 top-rated positions. Weighted Sentinel score lands at **89 / 100** with 4 Low-risk and 1 Medium. Blended APY is ≈ **~5.6%** net of gas.\n\nBelow is the Sentinel scoring breakdown for each pool — this is the Ilyon safety lens layered on top of the allocation.\n\nReady to execute? I'll prepare 5 transactions — you'll approve each one in your wallet; I never touch keys.",
      cards: [
        { kind: "card", step_index: 1, card_id: "a", card_type: "allocation", payload: allocationPayload as unknown as Record<string, unknown> },
        { kind: "card", step_index: 1, card_id: "s", card_type: "sentinel_matrix", payload: matrixPayload as unknown as Record<string, unknown> },
        { kind: "card", step_index: 1, card_id: "e", card_type: "execution_plan", payload: execPlanPayload as unknown as Record<string, unknown> },
      ],
      thoughts: [
        { kind: "thought", step_index: 1, content: "Parsed intent: allocate $10,000 across staking + yield." },
        { kind: "thought", step_index: 2, content: "Selected 5 positions with 0.5% slippage cap." },
      ],
      tools: [
        { kind: "tool", step_index: 1, name: "allocate_plan", args: { usd_amount: 10000, risk_budget: "balanced" } },
      ],
      elapsed_ms: 1381,
    },
  ];
}

describe("Agent chat demo parity (jsdom)", () => {
  it("renders user bubble, reasoning, assistant text + three purple cards + exec plan", () => {
    const messages = demoMessages();
    render(
      <MessageList messages={messages} currentSteps={{ thoughts: [], tools: [], cards: [] }} isStreaming={false} />,
    );

    expect(screen.getByTestId("user-bubble")).toHaveTextContent(/10,000/);
    expect(screen.getByTestId("reasoning-accordion")).toBeInTheDocument();
    const assistantBubbles = screen.getAllByTestId("assistant-bubble");
    expect(assistantBubbles.length).toBeGreaterThanOrEqual(2);

    const allocation = screen.getByTestId("allocation-card");
    expect(allocation).toBeInTheDocument();
    expect(allocation).toHaveTextContent(/Allocation Proposal/);
    expect(allocation).toHaveTextContent(/Sentinel × DefiLlama/);
    expect(allocation).toHaveTextContent(/\$10,000/);

    const matrix = screen.getByTestId("sentinel-matrix-card");
    expect(matrix).toHaveTextContent(/Sentinel Pool Scores/);
    expect(matrix).toHaveTextContent(/Weighted/);
    const rows = screen.getAllByTestId("sentinel-matrix-row");
    expect(rows).toHaveLength(5);

    const plan = screen.getByTestId("execution-plan-card");
    expect(plan).toHaveTextContent(/Execution Plan/);
    expect(plan).toHaveTextContent(/Start [Ss]igning/);
    const execRows = screen.getAllByTestId("execution-row");
    expect(execRows).toHaveLength(5);
  });
});
