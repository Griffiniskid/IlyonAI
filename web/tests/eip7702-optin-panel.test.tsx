import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import Eip7702OptInPanel from "@/components/settings/Eip7702OptInPanel";

// Mock the wallet helpers so we can assert orchestration without a real
// MetaMask / Phantom-EVM provider.
vi.mock("@/lib/wallets/metamask", () => ({
  signMessage: vi.fn(async () =>
    "0x" + "ab".repeat(65),
  ),
  sendTransaction: vi.fn(async () =>
    "0x" + "cd".repeat(32),
  ),
  waitForReceipt: vi.fn(async () => ({
    status: "0x1",
    blockNumber: "0x1",
  })),
  getChainId: vi.fn(async () => 1),
}));

import {
  signMessage as evmSignMessage,
  sendTransaction as evmSendTx,
  waitForReceipt as evmWaitReceipt,
} from "@/lib/wallets/metamask";

const WALLET = "0x1111111111111111111111111111111111111111";

function jsonResponse(body: object, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Eip7702OptInPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("walks prepare → sign → authorize → install-calldata → broadcast → register", async () => {
    const calls: string[] = [];
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const u = url.toString();
      calls.push(u);
      if (u.endsWith(`/api/v1/eip7702/${WALLET}`)) {
        return jsonResponse({ ok: true, authorizations: [] });
      }
      if (u.endsWith("/api/v1/eip7702/prepare")) {
        return jsonResponse({
          ok: true,
          digest: "0x" + "11".repeat(32),
          chain_id: 1,
          nonce: 0,
          impl: "0x000000aC74357BFEa72BBD0781833631F732cf19",
        });
      }
      if (u.endsWith("/api/v1/eip7702/authorize")) {
        return jsonResponse({
          ok: true,
          auth_id: "auth-1",
          impl_addr: "0x000000aC74357BFEa72BBD0781833631F732cf19",
          chain_id: 1,
          nonce: 0,
        });
      }
      if (u.endsWith("/api/v1/eip7702/install-module-calldata")) {
        return jsonResponse({
          ok: true,
          selector: "0x9517e29f",
          calldata: "0x9517e29f" + "00".repeat(128),
        });
      }
      if (u.endsWith("/api/v1/eip7702/broadcast")) {
        return jsonResponse({ ok: true, persisted: false });
      }
      throw new Error(`unexpected fetch: ${u}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Eip7702OptInPanel userWallet={WALLET} />);

    const btn = await screen.findByRole("button", {
      name: /Sign \+ install Nexus validator/i,
    });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(evmSignMessage).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(evmSendTx).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(evmWaitReceipt).toHaveBeenCalledTimes(1);
    });

    // Fetch order must be: list → prepare → authorize → calldata → broadcast
    // (one extra list at the end via reload).
    const order = calls.map((c) => c.split("/api/v1/eip7702")[1]);
    expect(order[0]).toMatch(/^\/0x/); // initial list
    expect(order[1]).toBe("/prepare");
    expect(order[2]).toBe("/authorize");
    expect(order[3]).toBe("/install-module-calldata");
    expect(order[4]).toBe("/broadcast");

    // sendTransaction received the impl_addr + calldata
    const txArg = (evmSendTx as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(txArg.to).toBe("0x000000aC74357BFEa72BBD0781833631F732cf19");
    expect(txArg.data).toMatch(/^0x9517e29f/);
    expect(txArg.value).toBe("0x0");
  });

  it("surfaces backend error from prepare without broadcasting", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const u = url.toString();
      if (u.endsWith(`/api/v1/eip7702/${WALLET}`)) {
        return jsonResponse({ ok: true, authorizations: [] });
      }
      if (u.endsWith("/api/v1/eip7702/prepare")) {
        return jsonResponse({ ok: false, error: "unsupported_chain" });
      }
      throw new Error(`unexpected fetch: ${u}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Eip7702OptInPanel userWallet={WALLET} />);
    const btn = await screen.findByRole("button", {
      name: /Sign \+ install Nexus validator/i,
    });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByText(/unsupported_chain/)).toBeInTheDocument();
    });
    expect(evmSignMessage).not.toHaveBeenCalled();
    expect(evmSendTx).not.toHaveBeenCalled();
  });
});
