import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import SessionKeyPanel from "@/components/settings/SessionKeyPanel";

vi.mock("@/lib/wallets/metamask", () => ({
  sendTransaction: vi.fn(async () => "0x" + "ef".repeat(32)),
  waitForReceipt: vi.fn(async () => ({
    status: "0x1",
    blockNumber: "0x10",
  })),
  getChainId: vi.fn(async () => 8453),
}));

import {
  sendTransaction as evmSendTx,
  waitForReceipt as evmWaitReceipt,
} from "@/lib/wallets/metamask";

const WALLET = "0xabcdabcdabcdabcdabcdabcdabcdabcdabcdabcd";

function jsonResponse(body: object): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("SessionKeyPanel revoke", () => {
  beforeEach(() => vi.clearAllMocks());

  it("calls off-chain revoke then broadcasts uninstallModule via 0xa71763a8", async () => {
    const policy = {
      policy_id: "policy-abc",
      scope: "uniswap-v4-position",
      spend_cap_24h_usd: "1000",
      expires_at: null,
      revoked_at: null,
      smart_account_address: WALLET,
      validator_module: "0x0000000000F8c1deDD7D60ce4e2B1b9D7f78f3a6",
    };
    const calls: string[] = [];
    const fetchMock = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const u = url.toString();
      calls.push(`${init?.method ?? "GET"} ${u}`);
      if (u.endsWith(`/api/v1/sessions/${WALLET.toLowerCase()}`)) {
        return jsonResponse({ ok: true, policies: [policy] });
      }
      if (u.endsWith(`/api/v1/sessions/policy-abc/revoke`)) {
        return jsonResponse({
          ok: true,
          policy_id: "policy-abc",
          revoked_at: "2026-05-17T00:00:00Z",
        });
      }
      if (u.endsWith("/api/v1/eip7702/uninstall-module-calldata")) {
        return jsonResponse({
          ok: true,
          selector: "0xa71763a8",
          calldata: "0xa71763a8" + "00".repeat(96),
        });
      }
      if (u.endsWith("/api/v1/eip7702/broadcast")) {
        return jsonResponse({ ok: true, persisted: false });
      }
      throw new Error(`unexpected fetch: ${u}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionKeyPanel userWallet={WALLET} />);

    const revokeBtn = await screen.findByRole("button", { name: /^Revoke$/ });
    fireEvent.click(revokeBtn);

    await waitFor(() => {
      expect(evmSendTx).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(evmWaitReceipt).toHaveBeenCalledTimes(1);
    });

    const tx = (evmSendTx as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(tx.data).toMatch(/^0xa71763a8/);
    expect(tx.to).toBe(WALLET);
    expect(tx.value).toBe("0x0");

    // Order: list → off-chain revoke → uninstall-calldata → broadcast register
    const seq = calls.map((c) => c.replace(/^[A-Z]+ /, "").split("/api/v1/")[1]);
    expect(seq[0]).toMatch(/^sessions\/0x/);
    expect(seq[1]).toBe(`sessions/policy-abc/revoke`);
    expect(seq[2]).toBe("eip7702/uninstall-module-calldata");
    expect(seq[3]).toBe("eip7702/broadcast");
  });

  it("shows error if off-chain revoke fails and skips broadcast", async () => {
    const policy = {
      policy_id: "policy-xyz",
      scope: "scope",
      revoked_at: null,
    };
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const u = url.toString();
      if (u.endsWith(`/api/v1/sessions/${WALLET.toLowerCase()}`)) {
        return jsonResponse({ ok: true, policies: [policy] });
      }
      if (u.endsWith("/api/v1/sessions/policy-xyz/revoke")) {
        return jsonResponse({ ok: false, error: "db_offline" });
      }
      throw new Error(`unexpected: ${u}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionKeyPanel userWallet={WALLET} />);
    fireEvent.click(await screen.findByRole("button", { name: /^Revoke$/ }));

    await waitFor(() => {
      expect(screen.getByText(/db_offline/)).toBeInTheDocument();
    });
    expect(evmSendTx).not.toHaveBeenCalled();
  });
});
