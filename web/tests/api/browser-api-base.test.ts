import { beforeEach, describe, expect, it, vi } from "vitest";

describe("browser API base URL", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8080");
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () => Promise.resolve({ query: "sol", input_type: "search_query", results: [] }),
    });
  });

  it("uses the Next proxy from the browser to avoid CORS failures", async () => {
    const api = await import("../../lib/api");

    await api.searchTokens("sol", "solana", 8);

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/v1/search?query=sol&limit=8&chain=solana",
      expect.any(Object),
    );
  });
});
