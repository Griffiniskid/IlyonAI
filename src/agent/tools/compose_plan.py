"""compose_plan — validate multi-step intent DAGs and return execution plan cards."""
from __future__ import annotations

from src.agent.planner import build_plan
from src.api.schemas.agent import ToolEnvelope
from src.agent.tools._base import err_envelope, ok_envelope


def _validate_intent(intent: dict) -> tuple[bool, str]:
    if not isinstance(intent, dict):
        return False, "intent must be a dict"
    steps = intent.get("steps")
    if not isinstance(steps, list):
        return False, "intent['steps'] must be a list"
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            return False, f"step {index} must be a dict"
        if "action" not in step:
            return False, f"step {index} missing required 'action' key"
        if not isinstance(step.get("params", {}), dict):
            return False, f"step {index} 'params' must be a dict"
    return True, ""


async def compose_plan(ctx, *, intent: dict):
    """Validate a multi-step intent and return an execution plan v2 card.

    Args:
        intent: Dict with keys:
            - title (str, optional): Human-readable plan title
            - steps (list): Ordered list of step dicts, each with:
                - action (str): One of the PlanStepV2 actions
                - params (dict): Action-specific parameters
                - step_id (str, optional): Explicit step UUID
                - resolves_from (dict, optional): Value resolution mapping
    """
    valid, reason = _validate_intent(intent)
    if not valid:
        return err_envelope("bad_intent", reason)

    plan = build_plan(intent)
    return ok_envelope(
        data={"plan_id": plan.plan_id, "title": plan.title},
        card_type="execution_plan_v2",
        card_payload=plan.model_dump(),
    )
