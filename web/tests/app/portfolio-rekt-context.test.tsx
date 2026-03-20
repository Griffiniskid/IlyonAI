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

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getRektIncidents: vi.fn().mockResolvedValue({
      incidents: [
        {
          id: "incident-1",
          name: "Portfolio Exploit",
          date: "2024-01-01",
          amount_usd: 1000000,
          protocol: "Portfolio",
          chains: ["Ethereum"],
          attack_type: "Exploit",
          description: "test",
          post_mortem_url: "",
          funds_recovered: false,
          severity: "HIGH",
        },
      ],
      meta: { cursor: null, freshness: "warm" },
    }),
  };
});

describe("Portfolio rekt context", () => {
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
    usePortfolioChainMatrixMock.mockReturnValue({ data: null });
    useToastMock.mockReturnValue({ addToast: vi.fn() });
  });

  it("renders rekt risk context", async () => {
    render(<PortfolioPage />);
    expect(await screen.findByText(/risk context: hacks & exploits/i)).toBeInTheDocument();
  });
});
