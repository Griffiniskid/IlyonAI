"use client";
import { useState } from "react";
import { useAgentStream } from "@/hooks/useAgentStream";
import { MessageList } from "./MessageList";
import { Composer } from "./Composer";
import { Sidebar } from "./Sidebar";

interface ChatShellProps {
  token: string | null;
  wallet?: string;
}

export function ChatShell({ token, wallet }: ChatShellProps) {
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const { messages, isStreaming, currentSteps, send } = useAgentStream(sessionId, token);

  return (
    <div className="flex h-full">
      <Sidebar currentId={sessionId} onSelect={setSessionId} />
      <div className="flex-1 flex flex-col">
        <MessageList messages={messages} currentSteps={currentSteps} isStreaming={isStreaming} />
        <Composer onSend={(msg) => send(msg, wallet)} disabled={isStreaming} />
      </div>
    </div>
  );
}
