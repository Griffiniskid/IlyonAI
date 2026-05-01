import type { ExecutionPlanV2Payload, StepStatusFrame } from "@/types/agent";

export function mergeStepStatus(
  plan: ExecutionPlanV2Payload,
  frame: StepStatusFrame,
): ExecutionPlanV2Payload {
  if (plan.plan_id !== frame.plan_id) return plan;

  let changed = false;
  const steps = plan.steps.map((step) => {
    if (step.step_id !== frame.step_id) return step;
    changed = true;
    return {
      ...step,
      status: frame.status,
      tx_hash: "tx_hash" in frame ? frame.tx_hash ?? null : step.tx_hash,
      error: "error" in frame ? frame.error ?? null : step.error,
    };
  });

  return changed ? { ...plan, steps } : plan;
}
