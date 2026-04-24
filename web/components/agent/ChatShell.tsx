"use client";
import { useState, useEffect } from "react";
import { useAgentStream } from "@/hooks/useAgentStream";
import { MessageList } from "./MessageList";
import { Composer } from "./Composer";
import { Sidebar } from "./Sidebar";

interface ChatShellProps {
  token: string | null;
  wallet?: string;
  initialPrompt?: string;
}

export function ChatShell({ token, wallet, initialPrompt }: ChatShellProps) {
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const { messages, isStreaming, currentSteps, send } = useAgentStream(sessionId, token);

  useEffect(() => {
    if (initialPrompt && !isStreaming) {
      send(initialPrompt, wallet);
    }
  }, [initialPrompt]);

  return (
    <div className="flex h-full">
      <Sidebar currentId={sessionId} messages={messages} onSelect={setSessionId} />
      <div className="flex-1 flex flex-col">
        <MessageList messages={messages} currentSteps={currentSteps} isStreaming={isStreaming} />
        <Composer onSend={(msg) => send(msg, wallet)} disabled={isStreaming} />
      </div>
    </div>
  );
}
