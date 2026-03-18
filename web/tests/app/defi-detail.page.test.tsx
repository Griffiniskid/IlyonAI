import { render, screen } from "@testing-library/react"
import DetailClient from "@/app/defi/_components/detail-client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import React from "react"

import { vi, it, expect } from "vitest"

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