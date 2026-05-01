import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { streamAgent } from "@/lib/agent-client";
import { useAgentStream } from "@/hooks/useAgentStream";
import type { SSEFrame } from "@/types/agent";

vi.mock("@/lib/agent-client", () => ({
  streamAgent: vi.fn(),
}));

function StreamHarness() {
  const { messages, send } = useAgentStream("status-session", "test-token");
  const assistant = messages.find((message) => message.role === "assistant");
  const status = assistant?.stepStatuses?.[0]?.status ?? "none";
  const planPayload = assistant?.cards[0]?.payload as { steps?: Array<{ status?: string; tx_hash?: string | null }> } | undefined;

  return (
    <div>
      <button type="button" onClick={() => void send("bridge then stake")}>Send</button>
      <div data-testid="message-status">{status}</div>
      <div data-testid="plan-step-status">{planPayload?.steps?.[0]?.status ?? "none"}</div>
      <div data-testid="plan-step-tx">{planPayload?.steps?.[0]?.tx_hash ?? "none"}</div>
    </div>
  );
}

describe("useAgentStream step status handling", () => {
  it("persists step_status frames and merges them into execution plan cards", async () => {
    async function* frames(): AsyncGenerator<SSEFrame, void, void> {
      yield {
        kind: "card",
        step_index: 1,
        card_id: "plan-card",
        card_type: "execution_plan_v2",
        payload: {
          plan_id: "p1",
          title: "Bridge and stake",
          total_steps: 1,
          total_gas_usd: 1,
          total_duration_estimate_s: 30,
          blended_sentinel: 80,
          requires_signature_count: 1,
          risk_warnings: [],
          risk_gate: "clear",
          requires_double_confirm: false,
          chains_touched: [],
          user_assets_required: {},
          steps: [
            { step_id: "bridge", order: 1, action: "bridge", params: {}, depends_on: [], resolves_from: {}, shield_flags: [], status: "pending" },
          ],
        },
      };
      yield { kind: "step_status", plan_id: "p1", step_id: "bridge", order: 1, status: "broadcast", tx_hash: "0xabc" };
      yield { kind: "final", content: "Plan started", card_ids: ["plan-card"], elapsed_ms: 5, steps: 1 };
      yield { kind: "done" };
    }
    vi.mocked(streamAgent).mockReturnValue(frames());

    render(<StreamHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(screen.getByTestId("message-status")).toHaveTextContent("broadcast"));
    expect(screen.getByTestId("plan-step-status")).toHaveTextContent("broadcast");
    expect(screen.getByTestId("plan-step-tx")).toHaveTextContent("0xabc");
  });
});
