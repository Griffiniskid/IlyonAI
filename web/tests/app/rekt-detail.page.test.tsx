import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RektIncidentPage from "@/app/rekt/[id]/page";
import { getRektIncident } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getRektIncident: vi.fn(),
}));

describe("Rekt Incident Detail Page", () => {
  it("renders incident details when found", async () => {
    vi.mocked(getRektIncident).mockResolvedValue({
      id: "ronin-2022",
      name: "Ronin Bridge Hack",
      date: "2022-03-23",
      amount_usd: 620000000,
      protocol: "Ronin / Axie Infinity",
      chains: ["Ethereum", "Ronin"],
      attack_type: "Private Key Compromise",
      description: "Attackers compromised validator private keys to withdraw funds from the Ronin bridge.",
      post_mortem_url: "https://example.com/post-mortem",
      funds_recovered: false,
      severity: "CRITICAL",
    });

    const page = await RektIncidentPage({ params: Promise.resolve({ id: "ronin-2022" }) });
    render(page);

    expect(screen.getByText("Ronin Bridge Hack")).toBeInTheDocument();
    expect(screen.getByText("Ronin / Axie Infinity")).toBeInTheDocument();
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
    expect(screen.getByText("Private Key Compromise")).toBeInTheDocument();
    expect(screen.getByText(/\$620.*M/)).toBeInTheDocument();
  });

  it("renders not found message when incident missing", async () => {
    vi.mocked(getRektIncident).mockResolvedValue(null);

    const page = await RektIncidentPage({ params: Promise.resolve({ id: "nonexistent" }) });
    render(page);

    expect(screen.getByText("Incident Not Found")).toBeInTheDocument();
  });

  it("renders affected chains badges", async () => {
    vi.mocked(getRektIncident).mockResolvedValue({
      id: "test-incident",
      name: "Test Incident",
      date: "2023-01-01",
      amount_usd: 1000000,
      protocol: "Test Protocol",
      chains: ["Ethereum", "BSC"],
      attack_type: "Flash Loan",
      description: "Test description",
      post_mortem_url: null,
      funds_recovered: false,
      severity: "HIGH",
    });

    const page = await RektIncidentPage({ params: Promise.resolve({ id: "test-incident" }) });
    render(page);

    expect(screen.getByText("Ethereum")).toBeInTheDocument();
    expect(screen.getByText("BSC")).toBeInTheDocument();
  });

  it("renders funds recovered badge when applicable", async () => {
    vi.mocked(getRektIncident).mockResolvedValue({
      id: "recovered-incident",
      name: "Recovered Incident",
      date: "2023-01-01",
      amount_usd: 500000,
      protocol: "Test Protocol",
      chains: ["Solana"],
      attack_type: "Exploit",
      description: "Funds were recovered",
      post_mortem_url: null,
      funds_recovered: true,
      severity: "MEDIUM",
    });

    const page = await RektIncidentPage({ params: Promise.resolve({ id: "recovered-incident" }) });
    render(page);

    expect(screen.getByText(/Funds Recovered/i)).toBeInTheDocument();
  });

  it("renders post-mortem link when available", async () => {
    vi.mocked(getRektIncident).mockResolvedValue({
      id: "incident-with-pm",
      name: "Incident With PM",
      date: "2023-01-01",
      amount_usd: 100000,
      protocol: "Test Protocol",
      chains: ["Ethereum"],
      attack_type: "Hack",
      description: "Test",
      post_mortem_url: "https://example.com/pm",
      funds_recovered: false,
      severity: "LOW",
    });

    const page = await RektIncidentPage({ params: Promise.resolve({ id: "incident-with-pm" }) });
    render(page);

    const postMortemLink = screen.getByRole("link", { name: /post-mortem/i });
    expect(postMortemLink).toHaveAttribute("href", "https://example.com/pm");
  });
});