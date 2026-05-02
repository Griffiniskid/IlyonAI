"""ReAct runtime: wires LLM + memory + tools + SSE streaming."""
from __future__ import annotations

import json as _json
import uuid
from typing import AsyncIterator

from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate

from src.agent.llm import IlyonChatModel
from src.agent.streaming import StreamCollector, encode_sse, frame_event_name
from src.agent.session import PersistentWindowMemory
from src.storage.chat import get_chat, append_message, create_chat
from src.api.schemas.agent import CardFrame, ThoughtFrame, ToolEnvelope, PlanBlockedFrame

SYSTEM_PROMPT = PromptTemplate.from_template(
    """You are Ilyon Sentinel's crypto agent. You answer questions about
DeFi, quote swaps, find pools, and assemble allocations. For every
allocation or pool, you MUST cite Sentinel scoring (Safety, Durability,
Exit, Confidence), risk_level (HIGH|MEDIUM|LOW), strategy_fit
(conservative|balanced|aggressive), and any Shield flags. You never
broadcast transactions -- only return unsigned tx payloads via build_*
tools. When unsure, use read-only tools first.

You have access to the following tools:
{tools}

Tool Names: {tool_names}

Use this format:
Thought: I need to ...
Action: <tool-name>
Action Input: <json>
Observation: ...
Thought: I now know the answer
Final Answer: ...

Question: {input}
{agent_scratchpad}
"""
)


def _compose_plan_from_message(message: str):
    """Return a deterministic execution plan for direct multi-step intents."""
    from src.agent.simple_runtime import detect_intent

    intent = detect_intent(message)
    if not intent or intent[0] != "compose_plan":
        return None

    from src.agent.planner import build_plan

    return build_plan(intent[1])


async def run_turn(
    *,
    db,
    router,
    tools,
    chat_id: str,
    user_id: int,
    message: str,
    wallet: str | None = None,
) -> AsyncIterator[bytes]:
    """Execute one agent turn and yield SSE-encoded frames.

    Parameters
    ----------
    db : AsyncSession
        Database session for persistence.
    router
        Duck-typed object with ``complete()`` (used by IlyonChatModel).
    tools : list
        LangChain tools available to the agent.
    chat_id : str
        UUID of the chat session.
    user_id : int
        Owner of the chat.
    message : str
        User's input message.
    wallet : str | None
        Optional wallet address (forwarded to tools via metadata).
    """
    # Ensure the chat row exists.
    chat = await get_chat(db, chat_id, user_id)
    if chat is None:
        chat = await create_chat(db, user_id=user_id, title=message[:60])
    await append_message(db, chat.id, role="user", content=message)

    direct_plan = _compose_plan_from_message(message)
    if direct_plan is not None:
        collector = StreamCollector()
        collector._step += 1
        collector._queue.append(ThoughtFrame(
            step_index=collector._step,
            content="Decomposing the request into a safe, ordered execution plan...",
        ))
        collector._queue.append(CardFrame(
            step_index=collector._step,
            card_id=direct_plan.plan_id,
            card_type="execution_plan_v2",
            payload=direct_plan.model_dump(),
        ))
        final_text = (
            f"I prepared a {direct_plan.total_steps}-step execution plan. Review the full plan, "
            "then sign each step in order; follow-up actions stay locked until the prior on-chain receipt confirms."
        )
        collector.emit_final(final_text, [direct_plan.plan_id])
        for frame in collector.drain():
            yield encode_sse(frame_event_name(frame), frame.model_dump())
        await append_message(
            db,
            chat.id,
            role="assistant",
            content=final_text,
            cards=[{"card_id": direct_plan.plan_id}],
        )
        return

    memory = await PersistentWindowMemory.load(db, chat.id, k=10)
    llm = IlyonChatModel(router=router, model="default")
    agent = create_react_agent(llm, tools, SYSTEM_PROMPT)
    collector = StreamCollector()
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        callbacks=[collector],
        max_iterations=10,
        handle_parsing_errors=True,
    )

    card_ids: list[str] = []
    final_text: str = ""

    async for event in executor.astream_events({"input": message}, version="v2"):
        # Drain queued frames from the callback.
        for frame in collector.drain():
            yield encode_sse(frame_event_name(frame), frame.model_dump())
            if isinstance(frame, CardFrame):
                card_ids.append(frame.card_id)

        # Check for tool results that contain enriched envelopes.
        if event["event"] == "on_tool_end":
            try:
                raw = event["data"].get("output", "")
                env = (
                    ToolEnvelope.model_validate_json(raw)
                    if isinstance(raw, str)
                    else None
                )
                # Critical Shield short-circuit
                if env is not None:
                    shield = getattr(env, "shield", None)
                    if shield is not None:
                        verdict = (getattr(shield, "verdict", "") or "").upper()
                        grade = (getattr(shield, "grade", "") or "").upper()
                        if verdict == "SCAM" or grade == "F":
                            blocked = PlanBlockedFrame(
                                plan_id=env.card_id or "tool-block",
                                reasons=list(shield.reasons or []),
                                severity="critical",
                            )
                            collector._queue.append(blocked)
                            final_text = (
                                "Blocked: this transaction triggered a critical Shield "
                                "warning and will not be signed.\n\n"
                                f"Reasons:\n- " + "\n- ".join(shield.reasons or [])
                            )
                            collector.emit_final(final_text, [])
                            for frame in collector.drain():
                                yield encode_sse(frame_event_name(frame), frame.model_dump())
                            return
                if env and env.card_type and env.card_payload is not None:
                    collector.emit_card(env.card_id, env.card_type, env.card_payload)
                if env and env.extra_cards:
                    for extra in env.extra_cards:
                        collector.emit_card(extra.card_id, extra.card_type, extra.payload)
                        card_ids.append(extra.card_id)
            except Exception:
                pass

        if event["event"] == "on_chain_end" and event.get("name") == "AgentExecutor":
            output = event["data"].get("output", {})
            final_text = (
                output.get("output", "") if isinstance(output, dict) else str(output)
            )

    from src.agent.clean import clean_agent_output

    final_text = clean_agent_output(final_text)
    collector.emit_final(final_text, card_ids)
    for frame in collector.drain():
        yield encode_sse(frame_event_name(frame), frame.model_dump())

    await append_message(
        db,
        chat.id,
        role="assistant",
        content=final_text,
        cards=[{"card_id": cid} for cid in card_ids],
    )


async def run_ephemeral_turn(
    *,
    router,
    tools,
    message: str,
    wallet: str | None = None,
) -> AsyncIterator[bytes]:
    """Execute one agent turn without DB persistence and yield SSE-encoded frames.

    Used for guest/unauthenticated sessions where chat history is not stored.
    Uses a simple direct LLM approach instead of ReAct agent.
    """
    from src.agent.simple_runtime import run_ephemeral_turn as _simple_run
    async for chunk in _simple_run(router=router, tools=tools, message=message, wallet=wallet):
        yield chunk
