import { render, screen } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import SmartMoneyPage from "@/app/smart-money/page";

const useSmartMoneyOverviewMock = vi.fn();

vi.mock("@/lib/hooks", () => ({
 useSmartMoneyOverview: () => useSmartMoneyOverviewMock(),
}));

describe("SmartMoneyPage", () => {
 beforeEach(() => {
   vi.clearAllMocks();
 });

 it("renders a loading state", async () => {
   useSmartMoneyOverviewMock.mockReturnValue({
     data: undefined,
     isLoading: true,
     isFetching: true,
     error: null,
   });

   render(<SmartMoneyPage />);

   expect(screen.getByText("Smart Money")).toBeInTheDocument();
   expect(screen.getByRole("button", { name: /refresh/i })).toBeInTheDocument();
 });

 it("renders an error state", async () => {
   useSmartMoneyOverviewMock.mockReturnValue({
     data: undefined,
     isLoading: false,
     isFetching: false,
     error: new Error("boom"),
   });

   render(<SmartMoneyPage />);

   expect(screen.getByText("Smart Money")).toBeInTheDocument();
   expect(screen.getByText(/track coordinated flows/i)).toBeInTheDocument();
 });

 it("renders smart money overview cards", async () => {
   useSmartMoneyOverviewMock.mockReturnValue({
     data: {
       net_flow_usd: 12345,
       inflow_usd: 67890,
       outflow_usd: 55545,
       flow_direction: "accumulating",
       sell_volume_percent: 45,
       top_buyers: [],
       top_sellers: [],
       recent_transactions: [],
       updated_at: new Date().toISOString(),
     },
     isLoading: false,
     isFetching: false,
     error: null,
   });

   render(<SmartMoneyPage />);

   expect(await screen.findByText("Net Flow")).toBeInTheDocument();
   expect(screen.getByText("Inflow")).toBeInTheDocument();
   expect(screen.getByText("Outflow")).toBeInTheDocument();
   expect(screen.getByText("Flow Direction")).toBeInTheDocument();
   expect(screen.getByText("Accumulating")).toBeInTheDocument();
 });

 it("renders top buyers and sellers tables", async () => {
   useSmartMoneyOverviewMock.mockReturnValue({
     data: {
       net_flow_usd: 1000,
       inflow_usd: 3000,
       outflow_usd: 2000,
       flow_direction: "neutral",
       sell_volume_percent: 50,
       top_buyers: [
         {
           wallet_address: "AbcD1234EfGh5678IjKl9012MnOp3456QrSt7890UvWx",
           label: "whale-1",
           amount_usd: 50000,
           tx_count: 12,
           last_seen: new Date().toISOString(),
           token_symbol: "SOL",
           dex_name: "Raydium",
         },
       ],
       top_sellers: [
         {
           wallet_address: "ZyXw9876VuTs5432RqPo1098NmLk7654JiHg3210FeDc",
           label: null,
           amount_usd: 30000,
           tx_count: 5,
           last_seen: new Date().toISOString(),
           token_symbol: "USDC",
           dex_name: "Orca",
         },
       ],
       recent_transactions: [],
       updated_at: new Date().toISOString(),
     },
     isLoading: false,
     isFetching: false,
     error: null,
   });

   render(<SmartMoneyPage />);

   expect(screen.getByText("Top Buyers")).toBeInTheDocument();
   expect(screen.getByText("Top Sellers")).toBeInTheDocument();
   expect(screen.getByText("whale-1")).toBeInTheDocument();
   expect(screen.getByText("Raydium")).toBeInTheDocument();
   expect(screen.getByText("Orca")).toBeInTheDocument();
 });

 it("renders recent transactions feed", async () => {
   useSmartMoneyOverviewMock.mockReturnValue({
     data: {
       net_flow_usd: 0,
       inflow_usd: 0,
       outflow_usd: 0,
       flow_direction: "distributing",
       sell_volume_percent: 70,
       top_buyers: [],
       top_sellers: [],
       recent_transactions: [
         {
           direction: "buy",
           wallet_address: "AbcD1234EfGh5678IjKl9012MnOp3456QrSt7890UvWx",
           wallet_label: "fund-a",
           token_symbol: "SOL",
           token_name: "Solana",
           token_address: "So11111111111111111111111111111111111111112",
           amount_tokens: 100,
           amount_usd: 15000,
           dex_name: "Raydium",
           signature: "sig123",
           timestamp: new Date().toISOString(),
           chain: "solana",
         },
       ],
       updated_at: new Date().toISOString(),
     },
     isLoading: false,
     isFetching: false,
     error: null,
   });

   render(<SmartMoneyPage />);

   expect(screen.getByText("Recent Transactions")).toBeInTheDocument();
   expect(screen.getByText("fund-a")).toBeInTheDocument();
   expect(screen.getByText("solana")).toBeInTheDocument();
   expect(screen.getByText("Distributing")).toBeInTheDocument();
 });
});
