"use client";
import { useState } from "react";
import { Send } from "lucide-react";

interface Props {
  onSend: (msg: string) => void;
  disabled: boolean;
}

export function Composer({ onSend, disabled }: Props) {
  const [text, setText] = useState("");
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  };
  return (
    <form onSubmit={handleSubmit} className="border-t border-slate-700 p-4 flex gap-2">
      <input
        type="text" value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Ask about DeFi, swaps, pools..." disabled={disabled}
        className="flex-1 bg-slate-800 rounded-lg px-4 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
      <button type="submit" disabled={disabled || !text.trim()}
        className="p-2 rounded-lg bg-blue-600 text-white disabled:opacity-50 hover:bg-blue-700">
        <Send className="h-4 w-4" />
      </button>
    </form>
  );
}
