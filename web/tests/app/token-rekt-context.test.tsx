import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TokenAnalysisPage from "@/app/token/[address]/page";

const useAnalyzeTokenMock = vi.fn();
const useRefreshAnalysisMock = vi.fn();
const useWhaleActivityMock = vi.fn();
const useToastMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ address: "So11111111111111111111111111111111111111112" }),
  useRouter: () => ({ back: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock("@/lib/hooks", () => ({
  useAnalyzeToken: () => useAnalyzeTokenMock(),
  useRefreshAnalysis: () => useRefreshAnalysisMock(),
  useWhaleActivity: () => useWhaleActivityMock(),
}));

vi.mock("@/components/ui/toaster", () => ({
  useToast: () => useToastMock(),
}));

vi.mock("@/components/token/score-card", () => ({
  ScoreCard: () => <div>score-card</div>,
}));

vi.mock("@/components/token/security-checks", () => ({
  SecurityChecks: () => <div>security-checks</div>,
}));

vi.mock("@/components/token/market-data", () => ({
  MarketData: () => <div>market-data</div>,
}));

vi.mock("@/components/token/website-analysis", () => ({
  WebsiteAnalysis: () => <div>website-analysis</div>,
}));

vi.mock("@/components/token/ai-analysis", () => ({
  AIAnalysis: () => <div>ai-analysis</div>,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getRektIncidents: vi.fn().mockResolvedValue({
      incidents: [
        {
          id: "incident-1",
          name: "Test Exploit",
          date: "2024-01-01",
          amount_usd: 1000000,
          protocol: "Test Protocol",
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

describe("Token rekt context", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    useAnalyzeTokenMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
      data: {
        token: {
          address: "So11111111111111111111111111111111111111112",
          name: "Wrapped SOL",
          symbol: "SOL",
          logo_url: null,
          chain: "solana",
        },
        scores: { overall: 85, grade: "A" },
        market: {
          price_usd: 100,
          price_change_24h: 2,
          market_cap: 1000000,
          liquidity_usd: 500000,
          volume_24h: 150000,
        },
        security: {},
        holders: {
          top_holder_pct: 12,
          holder_concentration: 30,
          suspicious_wallets: 1,
          dev_wallet_risk: false,
        },
        ai: { verdict: "SAFE", confidence: 0.12 },
        socials: {
          has_website: false,
          has_twitter: false,
          has_telegram: false,
        },
        deployer: {
          available: true,
          reputation_score: 88,
          risk_level: "LOW",
          is_known_scammer: false,
        },
        website: {},
      },
    });

    useRefreshAnalysisMock.mockReturnValue({ mutate: vi.fn(), isPending: false });
    useWhaleActivityMock.mockReturnValue({
      data: { entity_confidence: 73, transactions: [] },
      isLoading: false,
      isFetching: false,
    });
    useToastMock.mockReturnValue({ addToast: vi.fn() });
  });

  it("renders rekt risk context", async () => {
    render(<TokenAnalysisPage />);

    expect(await screen.findByText(/risk context: hacks & exploits/i)).toBeInTheDocument();
  });
});
