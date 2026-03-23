import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import FlowsPage from "@/app/flows/page";

const refetchMock = vi.fn();

vi.mock("@/lib/hooks", () => ({
  useSmartMoneyOverview: () => ({
    data: {
      net_flow_usd: 1500,
      inflow_usd: 2500,
      outflow_usd: 1000,
      buy_volume_percent: 55,
      sell_volume_percent: 45,
      top_buyers: [],
      top_sellers: [],
      recent_transactions: [
        {
          direction: "inflow",
          wallet_address: "AbcD1234EfGh5678IjKl9012MnOp3456QrSt7890UvWx",
          wallet_label: "whale-1",
          token_symbol: "SOL",
          token_name: "Solana",
          token_address: "So11111111111111111111111111111111111111112",
          amount_tokens: 100,
          amount_usd: 500,
          dex_name: "Raydium",
          signature: "sig1",
          timestamp: new Date().toISOString(),
          chain: "solana",
        },
        {
          direction: "outflow",
          wallet_address: "ZyXw9876VuTs5432RqPo1098NmLk7654JiHg3210FeDc",
          wallet_label: null,
          token_symbol: "USDC",
          token_name: "USD Coin",
          token_address: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
          amount_tokens: 300,
          amount_usd: 300,
          dex_name: "Orca",
          signature: "sig2",
          timestamp: new Date().toISOString(),
          chain: "solana",
        },
        {
          direction: "inflow",
          wallet_address: "MnOp3456QrSt7890UvWxAbcD1234EfGh5678IjKl9012",
          wallet_label: null,
          token_symbol: "BONK",
          token_name: "Bonk",
          token_address: "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
          amount_tokens: 2000000,
          amount_usd: 2000,
          dex_name: "Jupiter",
          signature: "sig3",
          timestamp: new Date().toISOString(),
          chain: "solana",
        },
      ],
      updated_at: "2026-03-19T00:00:00.000Z",
    },
    isLoading: false,
    isFetching: false,
    refetch: refetchMock,
  }),
}));

describe("Flows Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders capital flows header", () => {
    render(<FlowsPage />);
    expect(screen.getByRole("heading", { name: /capital flows/i })).toBeInTheDocument();
  });

  it("renders direction filter buttons (All, Buys, Sells)", () => {
    render(<FlowsPage />);
    expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Buys" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sells" })).toBeInTheDocument();
  });

  it("renders Solana badge instead of multi-chain filters", () => {
    render(<FlowsPage />);
    expect(screen.getByText("Solana")).toBeInTheDocument();
  });

  it("renders summary bar with buy/sell counts and net", () => {
    render(<FlowsPage />);
    expect(screen.getByText(/2 buys/)).toBeInTheDocument();
    expect(screen.getByText(/1 sells/)).toBeInTheDocument();
    expect(screen.getByText(/Net/)).toBeInTheDocument();
  });

  it("renders transaction cards with wallet addresses and token symbols", () => {
    render(<FlowsPage />);
    // Wallet label badge for whale-1
    expect(screen.getByText("whale-1")).toBeInTheDocument();
    // Token info lines include symbol and name
    expect(screen.getByText("SOL (Solana)")).toBeInTheDocument();
    expect(screen.getByText("USDC (USD Coin)")).toBeInTheDocument();
    expect(screen.getByText("BONK (Bonk)")).toBeInTheDocument();
  });

  it("renders DEX name badges on transaction cards", () => {
    render(<FlowsPage />);
    expect(screen.getByText("Raydium")).toBeInTheDocument();
    expect(screen.getByText("Orca")).toBeInTheDocument();
    expect(screen.getByText("Jupiter")).toBeInTheDocument();
  });

  it("renders Solscan explorer links for transactions", () => {
    render(<FlowsPage />);
    const explorerLinks = screen.getAllByLabelText("View on Solscan");
    expect(explorerLinks.length).toBe(3);
    expect(explorerLinks[0]).toHaveAttribute("href", "https://solscan.io/tx/sig1");
  });

  it("renders min amount filter input", () => {
    render(<FlowsPage />);
    const input = screen.getByPlaceholderText("0");
    expect(input).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "400" } });
    expect(input).toHaveValue(400);
  });

  it("renders refresh button that triggers refetch", () => {
    render(<FlowsPage />);
    const refreshBtn = screen.getByRole("button", { name: /refresh/i });
    fireEvent.click(refreshBtn);
    expect(refetchMock).toHaveBeenCalled();
  });

  it("renders last updated timestamp", () => {
    render(<FlowsPage />);
    expect(screen.getByText(/last updated/i)).toBeInTheDocument();
  });
});
