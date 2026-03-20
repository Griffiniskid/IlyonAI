import { describe, expect, it, vi } from "vitest";

import { RealtimeClient } from "@/lib/realtime";

describe("RealtimeClient fallback", () => {
  it("falls back to polling when socket closes", async () => {
    const stream = new RealtimeClient("http://localhost:8080");
    stream._force_socket_failure_for_test = true;

    const mode = await stream.connect_or_fallback("analysis.progress");

    expect(mode).toBe("polling");
  });

  it("falls back to polling when websocket connect times out", async () => {
    class HangingWebSocket {
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;

      constructor(_url: string) {}

      close() {}
    }

    vi.stubGlobal("WebSocket", HangingWebSocket as unknown as typeof WebSocket);
    const stream = new RealtimeClient("http://localhost:8080", { connectionTimeoutMs: 20 });

    const mode = await stream.connect_or_fallback("analysis.progress");

    expect(mode).toBe("polling");
    vi.unstubAllGlobals();
  });
});
