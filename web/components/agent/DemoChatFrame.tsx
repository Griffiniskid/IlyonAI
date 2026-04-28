"use client";
import { useEffect, useMemo, useState } from "react";
import { MessagesSquare, Sparkles } from "lucide-react";

import { useAgentStream } from "@/hooks/useAgentStream";
import { Composer } from "./Composer";
import { MessageList } from "./MessageList";
import { QuickChips } from "./QuickChips";
import { Sidebar } from "./Sidebar";

interface Props {
  token: string | null;
  wallet?: string;
  initialPrompt?: string;
}

function titleFromMessages(messages: { role: string; content: string }[]): string {
  const first = messages.find((m) => m.role === "user");
  if (!first) return "New session";
  return first.content.slice(0, 72) + (first.content.length > 72 ? "…" : "");
}

export function DemoChatFrame({ token, wallet, initialPrompt }: Props) {
  const [sessionId, setSessionId] = useState<string>(() => crypto.randomUUID());
  const { messages, isStreaming, currentSteps, send } = useAgentStream(sessionId, token);

  useEffect(() => {
    if (initialPrompt && messages.length === 0 && !isStreaming) {
      send(initialPrompt, wallet);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPrompt]);

  const title = useMemo(() => titleFromMessages(messages), [messages]);

  const onNew = () => {
    setSessionId(crypto.randomUUID());
  };

  return (
    <div className="mx-auto flex h-full w-full max-w-7xl flex-col px-4 py-4">
      <div className="mb-3 flex items-center justify-between gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-2.5 text-sm">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-emerald-400" />
          <span className="text-foreground/90">
            Preview of the AI Agent Chat layout · Sentinel scoring layered in
          </span>
        </div>
        <span className="rounded-full bg-emerald-500/15 px-3 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300">
          Live
        </span>
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden rounded-2xl border border-white/10 bg-card/40 backdrop-blur">
        <Sidebar currentId={sessionId} messages={messages} onSelect={setSessionId} />

        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span className="truncate text-foreground/90 max-w-[48vw] sm:max-w-xl">{title}</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onNew}
                className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-300 transition hover:bg-emerald-500/20"
              >
                <Sparkles className="h-3.5 w-3.5" />
                New
              </button>
              <div className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-card/40 px-3 py-1.5 text-xs font-medium text-foreground/80">
                <MessagesSquare className="h-3.5 w-3.5" />
                {messages.filter((message) => message.role === "assistant").length || 1} chat
              </div>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-hidden">
            <MessageList
              messages={messages}
              currentSteps={currentSteps}
              isStreaming={isStreaming}
            />
          </div>

          <div className="border-t border-white/10 bg-background/30 px-5 py-3">
            <QuickChips onSelect={(p) => send(p, wallet)} disabled={isStreaming} />
            <Composer onSend={(msg) => send(msg, wallet)} disabled={isStreaming} />
          </div>
        </div>
      </div>

      <p className="mt-6 text-center text-xs text-muted-foreground/70">
        Ilyon Agent handles intent capture, tool routing, and wallet execution; Sentinel layers in
        multi-dimensional pool scoring (Safety · Yield durability · Exit liquidity · Confidence) and
        cross-checks every protocol against the Shield risk surface.
      </p>
    </div>
  );
}
