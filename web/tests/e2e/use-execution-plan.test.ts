import { describe, expect, it } from "vitest";

import { mergeStepStatus } from "@/hooks/useExecutionPlan";
import type { ExecutionPlanV2Payload, StepStatusFrame } from "@/types/agent";

describe("useExecutionPlan helpers", () => {
  it("merges step_status frames into an execution plan payload", () => {
    const plan: ExecutionPlanV2Payload = {
      plan_id: "p1",
      title: "Bridge and stake",
      total_steps: 2,
      total_gas_usd: 8,
      total_duration_estimate_s: 120,
      blended_sentinel: 82,
      requires_signature_count: 2,
      risk_warnings: [],
      risk_gate: "clear",
      requires_double_confirm: false,
      chains_touched: ["1"],
      user_assets_required: {},
      steps: [
        { step_id: "approve", order: 1, action: "approve", params: {}, depends_on: [], resolves_from: {}, shield_flags: [], status: "ready" },
        { step_id: "bridge", order: 2, action: "bridge", params: {}, depends_on: ["approve"], resolves_from: {}, shield_flags: [], status: "pending" },
      ],
    };
    const frame: StepStatusFrame = { kind: "step_status", plan_id: "p1", step_id: "bridge", order: 2, status: "broadcast", tx_hash: "0xaaa" };

    const merged = mergeStepStatus(plan, frame);

    expect(merged.steps[1].status).toBe("broadcast");
    expect(merged.steps[1].tx_hash).toBe("0xaaa");
    expect(plan.steps[1].status).toBe("pending");
  });
});
