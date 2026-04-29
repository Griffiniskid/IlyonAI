import { afterEach, describe, expect, it, vi } from "vitest";

import { connectMetaMask } from "@/components/agent-app/wallets/metamask";

describe("connectMetaMask", () => {
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    Object.defineProperty(window, "ethereum", { configurable: true, value: undefined });
  });

  it("posts MetaMask auth to the assistant backend auth route", async () => {
    const address = "0x1111111111111111111111111111111111111111";
    const provider = {
      isMetaMask: true,
      request: vi.fn(async ({ method }: { method: string }) => {
        if (method === "eth_requestAccounts") return [address];
        if (method === "wallet_switchEthereumChain") return null;
        if (method === "eth_chainId") return "0x38";
        if (method === "personal_sign") return "0xsigned";
        return null;
      }),
    };
    Object.defineProperty(window, "ethereum", { configurable: true, value: provider });

    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        token: "session-token",
        user: { id: 1, display_name: "Wallet", wallet_address: address },
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    await connectMetaMask();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/metamask",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
