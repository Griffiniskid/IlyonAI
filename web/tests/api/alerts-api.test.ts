import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../lib/api";

describe("Alerts API", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as typeof fetch;
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8080");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("unwraps envelope payload for getAlerts", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          status: "ok",
          data: [
            {
              id: "alert-1",
              state: "new",
              severity: "high",
              title: "High Risk Alert",
            },
          ],
          meta: {},
          errors: [],
          trace_id: null,
          freshness: "live",
        }),
    });

    const result = await api.getAlerts();

    expect(Array.isArray(result)).toBe(true);
    expect(result).toHaveLength(1);
    expect(result[0]?.id).toBe("alert-1");
  });

  it("unwraps envelope payload for getDashboardStats", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          status: "ok",
          data: {
            total_volume_24h: 1000,
            volume_change_24h: 2.5,
            solana_tvl: 500,
            sol_price: 120,
            sol_price_change_24h: 1.2,
            active_tokens: 10,
            active_tokens_change: 1,
            safe_tokens_percent: 75,
            safe_tokens_change: 0,
            scams_detected: 1,
            scams_change: 0,
            high_risk_tokens: 2,
            volume_chart: [],
            risk_distribution: [],
            market_distribution: [],
            top_tokens_by_volume: [],
            tokens_analyzed_today: 3,
            total_tokens_analyzed: 42,
            avg_liquidity: 100,
            total_liquidity: 1000,
            updated_at: "2026-03-20T00:00:00Z",
          },
          meta: {},
          errors: [],
          trace_id: null,
          freshness: "live",
        }),
    });

    const result = await api.getDashboardStats();

    expect(result.total_tokens_analyzed).toBe(42);
  });

  it("unwraps envelope payload for getWhaleActivity", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          status: "ok",
          data: {
            transactions: [
              {
                signature: "sig-1",
                wallet_address: "wallet-1",
                wallet_label: "Whale 1",
                token_address: "token-1",
                token_symbol: "AAA",
                token_name: "Token AAA",
                type: "buy",
                amount_tokens: 100,
                amount_usd: 1000,
                price_usd: 10,
                timestamp: "2026-03-20T00:00:00Z",
                dex_name: "Jupiter",
              },
            ],
            updated_at: "2026-03-20T00:00:00Z",
            filter_token: null,
            min_amount_usd: 1000,
          },
          meta: {},
        }),
    });

    const result = await api.getWhaleActivity();

    expect(Array.isArray(result.transactions)).toBe(true);
    expect(result.transactions).toHaveLength(1);
    expect(result.transactions[0]?.signature).toBe("sig-1");
  });

  it("supports raw non-envelope payload for getWhaleActivity", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          transactions: [
            {
              signature: "sig-raw-1",
              wallet_address: "wallet-raw-1",
              token_address: "token-raw-1",
              token_symbol: "RAW",
              token_name: "Raw Token",
              type: "sell",
              amount_tokens: "12.5",
              amount_usd: "625",
              price_usd: "50",
              timestamp: "2026-03-20T00:01:00Z",
              dex_name: "Raydium",
            },
          ],
          updated_at: "2026-03-20T00:01:00Z",
          filter_token: "token-raw-1",
          min_amount_usd: "500",
        }),
    });

    const result = await api.getWhaleActivity();

    expect(result.transactions).toHaveLength(1);
    expect(result.transactions[0]).toMatchObject({
      signature: "sig-raw-1",
      type: "sell",
      amount_tokens: 12.5,
      amount_usd: 625,
      price_usd: 50,
    });
    expect(result.filter_token).toBe("token-raw-1");
    expect(result.min_amount_usd).toBe(500);
  });

  it("normalizes aliases and confidence for getWhaleActivityForToken", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          status: "ok",
          data: {
            transactions: [],
            updated_at: "2026-03-20T00:02:00Z",
            filter_token: "token-xyz",
            chain: "eth",
            minAmountUsd: "2500",
            entity_confidence: 0.836,
          },
          meta: {},
        }),
    });

    const result = await api.getWhaleActivityForToken("token-xyz", 25);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8080/api/v1/whales/token/token-xyz?limit=25",
      expect.any(Object)
    );
    expect(result.filter_chain).toBe("ethereum");
    expect(result.min_amount_usd).toBe(2500);
    expect(result.entity_confidence).toBe(84);
  });

  it("unwraps envelope payload for getSmartMoneyOverview and derives metrics", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          status: "ok",
          data: {
            entities: [
              {
                wallet_address: "buyer-1",
                label: "Buyer 1",
                side: "buy",
                amount_usd: 300,
              },
              {
                wallet_address: "seller-1",
                label: "Seller 1",
                side: "sell",
                amount_usd: 125,
              },
            ],
            flows: [
              { direction: "inflow", amount_usd: 500 },
              { direction: "inflow", amount_usd: 75 },
              { direction: "outflow", amount_usd: 125 },
            ],
            updated_at: "2026-03-20T00:00:00Z",
          },
          meta: {},
        }),
    });

    const result = await api.getSmartMoneyOverview();

    expect(result).toMatchObject({
      inflow_usd: 575,
      outflow_usd: 125,
      net_flow_usd: 450,
      updated_at: "2026-03-20T00:00:00Z",
    });
    expect(result.top_buyers).toEqual([
      {
        wallet_address: "buyer-1",
        label: "Buyer 1",
        amount_usd: 300,
        tx_count: 0,
        last_seen: "",
        token_symbol: "",
        dex_name: "",
      },
    ]);
    expect(result.top_sellers).toEqual([
      {
        wallet_address: "seller-1",
        label: "Seller 1",
        amount_usd: 125,
        tx_count: 0,
        last_seen: "",
        token_symbol: "",
        dex_name: "",
      },
    ]);
  });

  it("unwraps envelope payload for getPortfolio", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          status: "ok",
          data: {
            wallet_address: "wallet-1",
            total_value_usd: 1000,
            total_pnl_usd: 100,
            total_pnl_percent: 10,
            tokens: [
              {
                address: "token-1",
                symbol: "AAA",
                name: "Token AAA",
                logo_url: null,
                balance: 25,
                balance_usd: 250,
                price_usd: 10,
                price_change_24h: 2,
                safety_score: 78,
                risk_level: "medium",
              },
            ],
            health_score: 80,
            last_updated: "2026-03-20T00:00:00Z",
          },
          meta: {},
        }),
    });

    const result = await api.getPortfolio();

    expect(Array.isArray(result.tokens)).toBe(true);
    expect(result.tokens[0]).toMatchObject({
      address: "token-1",
      symbol: "AAA",
      name: "Token AAA",
      balance: 25,
      balance_usd: 250,
      price_usd: 10,
      safety_score: 78,
      risk_level: "medium",
    });
    expect(result.wallet_address).toBe("wallet-1");
    expect(result.total_value_usd).toBe(1000);
    expect(result.health_score).toBe(80);
    expect(result.last_updated).toBe("2026-03-20T00:00:00Z");
  });

  it("supports raw non-envelope payload for getPortfolio", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          wallet_address: "wallet-raw-1",
          total_value_usd: 4200,
          total_pnl_usd: 200,
          total_pnl_percent: 5,
          tokens: [],
          health_score: 91,
          last_updated: "2026-03-20T00:03:00Z",
        }),
    });

    const result = await api.getPortfolio();

    expect(result.wallet_address).toBe("wallet-raw-1");
    expect(result.total_value_usd).toBe(4200);
    expect(result.tokens).toEqual([]);
    expect(result.health_score).toBe(91);
    expect(result.last_updated).toBe("2026-03-20T00:03:00Z");
  });

  it("supports raw non-envelope payload for getSmartMoneyOverview", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          entities: [
            {
              wallet_address: "buyer-2",
              label: "Buyer 2",
              side: "buy",
              amount_usd: 90,
            },
          ],
          flows: [{ direction: "inflow", amount_usd: 90 }],
          updated_at: "2026-03-20T00:00:00Z",
        }),
    });

    const result = await api.getSmartMoneyOverview();

    expect(result.inflow_usd).toBe(90);
    expect(result.outflow_usd).toBe(0);
    expect(result.net_flow_usd).toBe(90);
    expect(result.top_buyers[0]).toMatchObject({
      wallet_address: "buyer-2",
      label: "Buyer 2",
      amount_usd: 90,
    });
  });

  it("normalizes numeric-string smart-money metrics without flows", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          status: "ok",
          data: {
            inflow_usd: "575.5",
            outflow_usd: "125.25",
            net_flow_usd: "450.25",
            updated_at: "2026-03-20T00:05:00Z",
          },
        }),
    });

    const result = await api.getSmartMoneyOverview();

    expect(result.inflow_usd).toBe(575.5);
    expect(result.outflow_usd).toBe(125.25);
    expect(result.net_flow_usd).toBe(450.25);
    expect(result.flows).toEqual([]);
  });

  it("normalizes entities and flows amount_usd from strings", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          entities: [
            {
              wallet_address: "buyer-3",
              label: "Buyer 3",
              side: "buy",
              amount_usd: "101.75",
            },
          ],
          flows: [{ direction: "inflow", amount_usd: "101.75" }],
          updated_at: "2026-03-20T00:06:00Z",
        }),
    });

    const result = await api.getSmartMoneyOverview();

    expect(result.entities).toEqual([
      {
        wallet_address: "buyer-3",
        label: "Buyer 3",
        side: "buy",
        amount_usd: 101.75,
      },
    ]);
    expect(result.flows).toEqual([{
      direction: "inflow",
      wallet_address: "",
      wallet_label: null,
      token_symbol: "",
      token_name: "",
      token_address: "",
      amount_tokens: 0,
      amount_usd: 101.75,
      dex_name: "",
      signature: "",
      timestamp: "",
      chain: "",
    }]);
  });
});
