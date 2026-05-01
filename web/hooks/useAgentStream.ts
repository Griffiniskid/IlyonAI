"use client";
import { useState, useCallback, useEffect } from "react";
import { streamAgent } from "@/lib/agent-client";
import { loadGuestSession, touchGuestSession } from "@/lib/agent-sessions";
import { mergeStepStatus } from "./useExecutionPlan";
import type { SSEFrame, ThoughtFrame, ToolFrame, CardFrame, FinalFrame, StepStatusFrame, PlanCompleteFrame, ExecutionPlanV2Payload } from "@/types/agent";

interface AgentCurrentSteps {
  thoughts: ThoughtFrame[];
  tools: ToolFrame[];
  cards: CardFrame[];
  stepStatuses: StepStatusFrame[];
  planCompletions: PlanCompleteFrame[];
}

function emptyCurrentSteps(): AgentCurrentSteps {
  return { thoughts: [], tools: [], cards: [], stepStatuses: [], planCompletions: [] };
}

interface AgentMessage {
  role: "user" | "assistant";
  content: string;
  cards: CardFrame[];
  thoughts: ThoughtFrame[];
  tools: ToolFrame[];
  stepStatuses?: StepStatusFrame[];
  planCompletions?: PlanCompleteFrame[];
  elapsed_ms?: number;
}

export function useAgentStream(sessionId: string, token: string | null) {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentSteps, setCurrentSteps] = useState<AgentCurrentSteps>(emptyCurrentSteps);

  useEffect(() => {
    if (token) {
      setMessages([]);
      setCurrentSteps(emptyCurrentSteps());
      return;
    }
    const session = loadGuestSession(sessionId);
    setMessages(session?.messages ?? []);
    setCurrentSteps(emptyCurrentSteps());
  }, [sessionId, token]);

  useEffect(() => {
    if (token || isStreaming) return;
    touchGuestSession(sessionId, messages);
  }, [isStreaming, messages, sessionId, token]);

  const send = useCallback(async (message: string, wallet?: string) => {
    setIsStreaming(true);
    // Add user message
    setMessages(prev => [...prev, { role: "user", content: message, cards: [], thoughts: [], tools: [] }]);

    const steps = emptyCurrentSteps();
    let finalContent = "";
    let elapsedMs = 0;

    try {
      for await (const frame of streamAgent({ session_id: sessionId, message, wallet }, token)) {
        if (frame.kind === "thought") {
          steps.thoughts.push(frame as ThoughtFrame);
          setCurrentSteps({ ...steps });
        } else if (frame.kind === "tool") {
          steps.tools.push(frame as ToolFrame);
          setCurrentSteps({ ...steps });
        } else if (frame.kind === "card") {
          steps.cards.push(frame as CardFrame);
          setCurrentSteps({ ...steps });
        } else if (frame.kind === "step_status") {
          const statusFrame = frame as StepStatusFrame;
          steps.stepStatuses.push(statusFrame);
          steps.cards = steps.cards.map((card) => {
            if (card.card_type !== "execution_plan_v2") return card;
            return {
              ...card,
              payload: mergeStepStatus(card.payload as unknown as ExecutionPlanV2Payload, statusFrame) as unknown as Record<string, unknown>,
            };
          });
          setCurrentSteps({ ...steps });
        } else if (frame.kind === "plan_complete") {
          steps.planCompletions.push(frame as PlanCompleteFrame);
          setCurrentSteps({ ...steps });
        } else if (frame.kind === "final") {
          const f = frame as FinalFrame;
          finalContent = f.content;
          elapsedMs = f.elapsed_ms;
        } else {
          const anyFrame = frame as unknown as { kind?: string; error?: string };
          if (anyFrame.kind === "error") {
            finalContent = `⚠️ Agent error: ${anyFrame.error ?? "unknown"}`;
          }
        }
      }
    } catch (e) {
      finalContent = `⚠️ ${e instanceof Error ? e.message : "Connection lost. Please retry."}`;
    }
    if (!finalContent) {
      finalContent = "⚠️ The agent closed the stream without a final answer. Please retry.";
    }

    setMessages(prev => [...prev, {
      role: "assistant", content: finalContent, cards: steps.cards,
      thoughts: steps.thoughts, tools: steps.tools, stepStatuses: steps.stepStatuses,
      planCompletions: steps.planCompletions, elapsed_ms: elapsedMs,
    }]);
    setCurrentSteps(emptyCurrentSteps());
    setIsStreaming(false);
  }, [sessionId, token]);

  return { messages, isStreaming, currentSteps, send };
}

export type { AgentMessage };
