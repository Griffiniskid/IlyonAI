import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PortfolioPage from "@/app/portfolio/page";

const useWalletMock = vi.fn();
const useWalletPortfolioMock = vi.fn();
const useTrackWalletMock = vi.fn();
const usePortfolioChainMatrixMock = vi.fn();
const useToastMock = vi.fn();

vi.mock("@solana/wallet-adapter-react", () => ({
  useWallet: () => useWalletMock(),
}));

vi.mock("@/lib/hooks", () => ({
  useWalletPortfolio: () => useWalletPortfolioMock(),
  useTrackWallet: () => useTrackWalletMock(),
  usePortfolioChainMatrix: () => usePortfolioChainMatrixMock(),
}));

vi.mock("@/components/ui/toaster", () => ({
  useToast: () => useToastMock(),
}));

describe("Portfolio multi-chain", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    useWalletMock.mockReturnValue({
      connected: true,
      publicKey: { toBase58: () => "So11111111111111111111111111111111111111112" },
    });

    useWalletPortfolioMock.mockReturnValue({
      data: {
        total_value_usd: 100,
        total_pnl_percent: 1,
        health_score: 80,
        tokens: [],
      },
      isLoading: false,
      refetch: vi.fn(),
    });

    useTrackWalletMock.mockReturnValue({ mutate: vi.fn(), isPending: false });
    usePortfolioChainMatrixMock.mockReturnValue({
      data: {
        capabilities: ["spot_holdings", "lp_positions"],
        chains: {
          solana: {
            spot_holdings: { state: "available", reason: null },
            lp_positions: { state: "available", reason: null },
          },
          ethereum: {
            spot_holdings: { state: "available", reason: null },
            lp_positions: { state: "degraded", reason: "LP tracking requires protocol-specific integrations" },
          },
        },
      },
      isLoading: false,
    });
    useToastMock.mockReturnValue({ addToast: vi.fn() });
  });

  it("renders exposure rows for all supported chains", async () => {
    render(<PortfolioPage />);
    expect(await screen.findByText(/Ethereum/)).toBeInTheDocument();
    expect(await screen.findByText(/Solana/)).toBeInTheDocument();
  });

  it("shows explicit degraded status when a chain capability is missing", async () => {
    render(<PortfolioPage />);
    expect(await screen.findByText(/capabilities degraded/i)).toBeInTheDocument();
    expect(await screen.findByText(/chains active/i)).toBeInTheDocument();
  });
});
