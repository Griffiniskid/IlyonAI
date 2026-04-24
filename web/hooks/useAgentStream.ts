"use client";
import { useState, useCallback, useEffect } from "react";
import { streamAgent } from "@/lib/agent-client";
import { loadGuestSession, touchGuestSession } from "@/lib/agent-sessions";
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

  useEffect(() => {
    if (token) {
      setMessages([]);
      setCurrentSteps({ thoughts: [], tools: [], cards: [] });
      return;
    }
    const session = loadGuestSession(sessionId);
    setMessages(session?.messages ?? []);
    setCurrentSteps({ thoughts: [], tools: [], cards: [] });
  }, [sessionId, token]);

  useEffect(() => {
    if (token || isStreaming) return;
    touchGuestSession(sessionId, messages);
  }, [isStreaming, messages, sessionId, token]);

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
      thoughts: steps.thoughts, tools: steps.tools, elapsed_ms: elapsedMs,
    }]);
    setCurrentSteps({ thoughts: [], tools: [], cards: [] });
    setIsStreaming(false);
  }, [sessionId, token]);

  return { messages, isStreaming, currentSteps, send };
}

export type { AgentMessage };
