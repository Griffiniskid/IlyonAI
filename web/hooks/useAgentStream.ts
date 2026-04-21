"use client";
import { useState, useCallback } from "react";
import { streamAgent } from "@/lib/agent-client";
import type { SSEFrame, ThoughtFrame, ToolFrame, CardFrame, FinalFrame } from "@/types/agent";

interface AgentMessage {
  role: "user" | "assistant";
  content: string;
  cards: CardFrame[];
  thoughts: ThoughtFrame[];
  tools: ToolFrame[];
  elapsed_ms?: number;
}

export function useAgentStream(sessionId: string, token: string | null) {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentSteps, setCurrentSteps] = useState<{ thoughts: ThoughtFrame[]; tools: ToolFrame[]; cards: CardFrame[] }>({
    thoughts: [], tools: [], cards: [],
  });

  const send = useCallback(async (message: string, wallet?: string) => {
    setIsStreaming(true);
    // Add user message
    setMessages(prev => [...prev, { role: "user", content: message, cards: [], thoughts: [], tools: [] }]);

    const steps = { thoughts: [] as ThoughtFrame[], tools: [] as ToolFrame[], cards: [] as CardFrame[] };
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
        } else if (frame.kind === "final") {
          const f = frame as FinalFrame;
          finalContent = f.content;
          elapsedMs = f.elapsed_ms;
        }
      }
    } catch (e) {
      finalContent = `Error: ${e instanceof Error ? e.message : "stream failed"}`;
    }

    setMessages(prev => [...prev, {
      role: "assistant", content: finalContent, cards: steps.cards,
      thoughts: steps.thoughts, tools: steps.tools, elapsed_ms: elapsedMs,
    }]);
    setCurrentSteps({ thoughts: [], tools: [], cards: [] });
    setIsStreaming(false);
  }, [sessionId, token]);

  return { messages, isStreaming, currentSteps, send };
}

export type { AgentMessage };
