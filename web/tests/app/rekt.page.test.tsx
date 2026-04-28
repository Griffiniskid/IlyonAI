import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RektPage from "@/app/rekt/page";
import RektIncidentPage from "@/app/rekt/[id]/page";
import { getRektIncident, getRektIncidents } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getRektIncidents: vi.fn(),
    getRektIncident: vi.fn(),
  };
});

describe("Rekt page", () => {
  it("renders rekt list page content", async () => {
    vi.mocked(getRektIncidents).mockResolvedValue({
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
      count: 1,
      total_stolen_usd: 1000000,
      meta: { cursor: null, freshness: "warm" },
    });

    const page = await RektPage();
    render(page);

    expect(await screen.findByText(/rekt database/i)).toBeInTheDocument();
    expect(await screen.findByText(/test exploit/i)).toBeInTheDocument();
  });

  it("renders detail page via dedicated detail endpoint", async () => {
    vi.mocked(getRektIncident).mockResolvedValue({
      id: "incident-1",
      name: "Test Exploit",
      date: "2024-01-01",
      amount_usd: 1000000,
      protocol: "Test Protocol",
      chains: ["Ethereum"],
      attack_type: "Exploit",
      description: "detail description",
      post_mortem_url: "",
      funds_recovered: false,
      severity: "HIGH",
    });

    const page = await RektIncidentPage({ params: Promise.resolve({ id: "incident-1" }) });
    render(page);

    expect(await screen.findByText(/detail description/i)).toBeInTheDocument();
    expect(getRektIncident).toHaveBeenCalledWith("incident-1");
  });
});
