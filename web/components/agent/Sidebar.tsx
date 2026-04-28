"use client";

import { useEffect, useMemo, useState } from "react";
import { MessageSquare, Plus, Trash2 } from "lucide-react";

import { deleteGuestSession, loadGuestSessions, type StoredAgentMessage, type StoredAgentSession } from "@/lib/agent-sessions";

interface Props {
  currentId: string;
  messages: StoredAgentMessage[];
  onSelect: (id: string) => void;
}

function formatUpdatedAt(updatedAt: string): string {
  const date = new Date(updatedAt);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function Sidebar({ currentId, messages, onSelect }: Props) {
  const [sessions, setSessions] = useState<StoredAgentSession[]>([]);

  useEffect(() => {
    setSessions(loadGuestSessions());
  }, [currentId, messages]);

  const visibleSessions = useMemo(() => {
    if (sessions.some((session) => session.id === currentId)) {
      return sessions;
    }
    return [
      {
        id: currentId,
        title: messages[0]?.content ? messages[0].content.slice(0, 56) : "New chat",
        updatedAt: new Date().toISOString(),
        messages,
      },
      ...sessions,
    ];
  }, [currentId, messages, sessions]);

  return (
    <aside className="hidden w-72 shrink-0 border-r border-white/10 bg-card/35 lg:flex lg:flex-col">
      <div className="border-b border-white/10 p-3">
        <button
          type="button"
          onClick={() => onSelect(crypto.randomUUID())}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-300 transition hover:bg-emerald-500/15"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </button>
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto p-2">
        {visibleSessions.map((session) => {
          const active = session.id === currentId;
          return (
            <div
              key={session.id}
              className={`group relative rounded-xl border transition ${
                active
                  ? "border-emerald-500/30 bg-emerald-500/10"
                  : "border-transparent bg-transparent hover:border-white/10 hover:bg-white/5"
              }`}
            >
              <button
                type="button"
                onClick={() => onSelect(session.id)}
                className="flex w-full items-start gap-3 px-3 py-2 text-left"
              >
                <div className={`mt-0.5 rounded-lg p-1.5 ${active ? "bg-emerald-500/15 text-emerald-300" : "bg-white/5 text-muted-foreground"}`}>
                  <MessageSquare className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-foreground">{session.title || "New chat"}</div>
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    {session.messages.length} message{session.messages.length === 1 ? "" : "s"}
                    {session.updatedAt ? ` · ${formatUpdatedAt(session.updatedAt)}` : ""}
                  </div>
                </div>
              </button>
              {session.messages.length > 0 && !active && (
                <button
                  type="button"
                  aria-label={`Remove ${session.title || "chat"}`}
                  onClick={() => {
                    deleteGuestSession(session.id);
                    setSessions(loadGuestSessions());
                  }}
                  className="absolute right-2 top-2 hidden items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground transition hover:bg-white/5 hover:text-foreground group-hover:flex"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
