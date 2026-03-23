import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WalletAddressPage from "@/app/wallet/[address]/page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ address: "TestWallet123ABC" }),
  useRouter: () => ({ back: vi.fn() }),
}));

const mockProfile = {
  wallet: "TestWallet123ABC",
  label: "Whale",
  volume_usd: 5000,
  transaction_count: 42,
  entity_id: "entity-abc",
  linked_wallets: ["LinkedWallet1XXXX", "LinkedWallet2YYYY"],
  link_reason: "common funding source",
  recent_transactions: [
    {
      direction: "buy",
      wallet_address: "TestWallet123ABC",
      wallet_label: "Whale",
      token_symbol: "SOL",
      token_name: "Solana",
      token_address: "So11111111111111111111111111111111111111112",
      amount_tokens: 100,
      amount_usd: 2500,
      dex_name: "Raydium",
      signature: "sig123abc",
      timestamp: "2026-03-23T00:00:00.000Z",
      chain: "solana",
    },
  ],
};

const mockForensics = {
  wallet: "TestWallet123ABC",
  risk_level: "HIGH",
  reputation_score: 35,
  tokens_deployed: 10,
  rugged_tokens: 3,
  active_tokens: 7,
  rug_percentage: 0.3,
  patterns_detected: ["wash-trading", "pump-and-dump"],
  pattern_severity: "HIGH",
  funding_risk: 0.6,
  confidence: 0.85,
  evidence_summary: "Wallet linked to multiple rug events.",
};

vi.mock("@/lib/hooks", () => ({
  useWalletProfile: vi.fn(() => ({
    data: mockProfile,
    isLoading: false,
    error: null,
  })),
  useWalletForensics: vi.fn(() => ({
    data: mockForensics,
    isLoading: false,
    error: null,
  })),
}));

Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn().mockResolvedValue(undefined),
  },
});

describe("Wallet Intelligence Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders wallet intelligence header", () => {
    render(<WalletAddressPage />);
    expect(screen.getByRole("heading", { name: /wallet intelligence/i })).toBeInTheDocument();
  });

  it("displays full address in code block", () => {
    render(<WalletAddressPage />);
    expect(screen.getByText("TestWallet123ABC")).toBeInTheDocument();
  });

  it("renders label badge from profile", () => {
    render(<WalletAddressPage />);
    expect(screen.getByText("Whale")).toBeInTheDocument();
  });

  it("renders copy button that copies address to clipboard", async () => {
    render(<WalletAddressPage />);
    const copyBtn = screen.getByRole("button", { name: /copy/i });
    fireEvent.click(copyBtn);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("TestWallet123ABC");
  });

  it("renders Solscan explorer link", () => {
    render(<WalletAddressPage />);
    const link = screen.getByText("Solscan").closest("a");
    expect(link).toHaveAttribute("href", "https://solscan.io/account/TestWallet123ABC");
  });

  it("renders risk level from forensics", () => {
    render(<WalletAddressPage />);
    expect(screen.getByText("HIGH")).toBeInTheDocument();
  });

  it("renders volume metric", () => {
    render(<WalletAddressPage />);
    expect(screen.getByText("$5.00K")).toBeInTheDocument();
  });

  it("renders transaction count metric", () => {
    render(<WalletAddressPage />);
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders entity id", () => {
    render(<WalletAddressPage />);
    expect(screen.getByText("entity-abc")).toBeInTheDocument();
  });

  it("renders recent transactions section", () => {
    render(<WalletAddressPage />);
    expect(screen.getByText("Recent Transactions")).toBeInTheDocument();
    expect(screen.getByText("SOL")).toBeInTheDocument();
    expect(screen.getByText("Solana")).toBeInTheDocument();
    expect(screen.getByText("Raydium")).toBeInTheDocument();
  });

  it("renders forensics section with reputation score", () => {
    render(<WalletAddressPage />);
    expect(screen.getByText("Forensics")).toBeInTheDocument();
    expect(screen.getByText("35")).toBeInTheDocument();
    expect(screen.getByText("out of 100")).toBeInTheDocument();
  });

  it("renders deployment stats", () => {
    render(<WalletAddressPage />);
    expect(screen.getByText("10")).toBeInTheDocument(); // tokens deployed
    expect(screen.getByText("3")).toBeInTheDocument(); // rugged
    expect(screen.getByText("7")).toBeInTheDocument(); // active
    expect(screen.getByText("30.0%")).toBeInTheDocument(); // rug percentage
  });

  it("renders risk metrics (funding risk, confidence)", () => {
    render(<WalletAddressPage />);
    expect(screen.getByText("60%")).toBeInTheDocument(); // funding risk
    expect(screen.getByText("85%")).toBeInTheDocument(); // confidence
  });

  it("renders detected patterns as badges", () => {
    render(<WalletAddressPage />);
    expect(screen.getByText("wash-trading")).toBeInTheDocument();
    expect(screen.getByText("pump-and-dump")).toBeInTheDocument();
  });

  it("renders evidence summary", () => {
    render(<WalletAddressPage />);
    expect(screen.getByText("Wallet linked to multiple rug events.")).toBeInTheDocument();
  });

  it("renders linked wallets section with clickable links", () => {
    render(<WalletAddressPage />);
    expect(screen.getByText("Linked Wallets")).toBeInTheDocument();
    expect(screen.getByText("common funding source")).toBeInTheDocument();

    // Linked wallets should be links to their wallet pages
    const links = screen.getAllByRole("link").filter(
      (link) => link.getAttribute("href")?.startsWith("/wallet/Linked")
    );
    expect(links.length).toBe(2);
    expect(links[0]).toHaveAttribute("href", "/wallet/LinkedWallet1XXXX");
    expect(links[1]).toHaveAttribute("href", "/wallet/LinkedWallet2YYYY");
  });

  it("shows empty state when profile has no data", async () => {
    const { useWalletProfile } = await import("@/lib/hooks");
    (useWalletProfile as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      data: null,
      isLoading: false,
      error: new Error("not found"),
    });
    render(<WalletAddressPage />);
    expect(screen.getByText(/no whale activity found/i)).toBeInTheDocument();
  });

  it("shows forensics unavailable when forensics errors", async () => {
    const { useWalletForensics } = await import("@/lib/hooks");
    (useWalletForensics as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      data: null,
      isLoading: false,
      error: new Error("failed"),
    });
    render(<WalletAddressPage />);
    expect(screen.getByText(/forensics unavailable/i)).toBeInTheDocument();
  });
});
