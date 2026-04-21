"use client";
import { useRef, useEffect } from "react";
import { AssistantBubble } from "./AssistantBubble";
import { UserBubble } from "./UserBubble";
import { ReasoningAccordion } from "./ReasoningAccordion";
import type { AgentMessage } from "@/hooks/useAgentStream";
import type { ThoughtFrame, ToolFrame, CardFrame } from "@/types/agent";

interface Props {
  messages: AgentMessage[];
  currentSteps: { thoughts: ThoughtFrame[]; tools: ToolFrame[]; cards: CardFrame[] };
  isStreaming: boolean;
}

export function MessageList({ messages, currentSteps, isStreaming }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, currentSteps]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.map((msg, i) => (
        msg.role === "user"
          ? <UserBubble key={i} content={msg.content} />
          : <AssistantBubble key={i} content={msg.content} cards={msg.cards} />
      ))}
      {isStreaming && currentSteps.thoughts.length > 0 && (
        <ReasoningAccordion
          steps={currentSteps.thoughts.map(t => t.content)}
          time={0}
          lines={currentSteps.thoughts.length}
        />
      )}
      <div ref={bottomRef} />
    </div>
  );
}
