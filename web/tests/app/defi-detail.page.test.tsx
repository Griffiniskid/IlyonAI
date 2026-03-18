import { render, screen } from "@testing-library/react"
import DetailClient from "@/app/defi/_components/detail-client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import React from "react"

import { vi, it, expect, describe } from "vitest"
import { useOpportunityAnalysis } from "@/lib/hooks"

import { CHAIN_MATRIX, SOLANA_FIXTURE, EVM_FIXTURE } from '../fixtures/defi';

// Mock the hook
vi.mock("@/lib/hooks", () => ({
  useOpportunityAnalysis: vi.fn().mockReturnValue({
    data: {
      id: "opp_1",
      title: "Test Opportunity",
      behavior: "some behavior",
      evidence: [{ title: "Test Evidence" }],
      scenarios: [{ title: "Test Scenario" }],
      ai_analysis: {
        headline: "Test AI Analysis",
        summary: "This is a summary",
      },
    },
    isLoading: false,
  })
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

describe("DetailClient", () => {
  it("renders behavior, evidence, scenarios, and AI analyst on the detail page", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <DetailClient opportunityId="opp_1" />
      </QueryClientProvider>
    )
    expect(await screen.findByRole("heading", { name: /behavior/i })).toBeInTheDocument()
    expect(await screen.findByRole("heading", { name: /evidence/i })).toBeInTheDocument()
    expect(await screen.findByRole("heading", { name: /scenarios/i })).toBeInTheDocument()
    expect(await screen.findByRole("heading", { name: /ai analyst/i })).toBeInTheDocument()
    expect(await screen.findByText("some behavior")).toBeInTheDocument()
  })

  it("renders solana fixture opportunity details", async () => {
    vi.mocked(useOpportunityAnalysis).mockReturnValue({
      data: {
        id: "opp_sol",
        title: `${SOLANA_FIXTURE.protocol_slug} Opportunity`,
        behavior: `${SOLANA_FIXTURE.chain} behavior`,
        evidence: [],
        scenarios: [],
        ai_analysis: { headline: "Solana Analyst", summary: "" } as any,
        chain: SOLANA_FIXTURE.chain,
        protocol: SOLANA_FIXTURE.protocol_slug
      } as any,
      isLoading: false,
    } as any);
    render(
      <QueryClientProvider client={queryClient}>
        <DetailClient opportunityId="opp_sol" />
      </QueryClientProvider>
    );
    expect(await screen.findAllByText(new RegExp(SOLANA_FIXTURE.protocol_slug, "i"))).toHaveLength(1);
    expect((await screen.findAllByText(new RegExp(SOLANA_FIXTURE.chain, "i"))).length).toBeGreaterThan(0);
  });

  it("renders evm fixture opportunity details", async () => {
    vi.mocked(useOpportunityAnalysis).mockReturnValue({
      data: {
        id: "opp_evm",
        title: `${EVM_FIXTURE.protocol_slug} Opportunity`,
        behavior: `${EVM_FIXTURE.chain} behavior`,
        evidence: [],
        scenarios: [],
        ai_analysis: { headline: "EVM Analyst", summary: "" } as any,
        chain: EVM_FIXTURE.chain,
        protocol: EVM_FIXTURE.protocol_slug
      } as any,
      isLoading: false,
    } as any);
    render(
      <QueryClientProvider client={queryClient}>
        <DetailClient opportunityId="opp_evm" />
      </QueryClientProvider>
    );
    expect(await screen.findAllByText(new RegExp(EVM_FIXTURE.protocol_slug, "i"))).toHaveLength(1);
    expect((await screen.findAllByText(new RegExp(EVM_FIXTURE.chain, "i"))).length).toBeGreaterThan(0);
  });
})