"use client";
import { useState, useEffect } from "react";
import { Plus, MessageSquare } from "lucide-react";

interface Props {
  currentId: string;
  onSelect: (id: string) => void;
}

export function Sidebar({ currentId, onSelect }: Props) {
  const [sessions, setSessions] = useState<{ id: string; title: string }[]>([]);

  useEffect(() => {
    fetch("/api/v1/agent/sessions")
      .then(r => r.json())
      .then(d => setSessions(d.sessions || []))
      .catch(() => {});
  }, [currentId]);

  return (
    <div className="w-64 border-r border-slate-700 flex flex-col bg-slate-900">
      <div className="p-3 border-b border-slate-700">
        <button onClick={() => onSelect(crypto.randomUUID())}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800 text-sm text-slate-300 hover:bg-slate-700">
          <Plus className="h-4 w-4" /> New Chat
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {sessions.map(s => (
          <button key={s.id} onClick={() => onSelect(s.id)}
            className={`w-full text-left px-3 py-2 rounded text-sm truncate ${s.id === currentId ? "bg-slate-700 text-white" : "text-slate-400 hover:bg-slate-800"}`}>
            <MessageSquare className="inline h-3 w-3 mr-1" />{s.title}
          </button>
        ))}
      </div>
    </div>
  );
}
