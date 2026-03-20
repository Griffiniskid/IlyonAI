"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";

export function CommandPalette() {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsOpen((open) => !open);
      } else if (e.key === "Escape") {
        setIsOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 z-50 flex items-start justify-center pt-32 sm:pt-48 bg-black/50 backdrop-blur-sm"
      onClick={() => setIsOpen(false)}
    >
      <div 
        className="w-full max-w-xl overflow-hidden rounded-xl bg-slate-900 border border-slate-800 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center border-b border-slate-800 px-3">
          <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
          <input
            className="flex h-12 w-full rounded-md bg-transparent py-3 text-sm outline-none placeholder:text-slate-400 disabled:cursor-not-allowed disabled:opacity-50"
            placeholder="Search tokens, wallets, pages..."
            autoFocus
          />
        </div>
        <div className="max-h-80 overflow-y-auto p-2 text-sm text-slate-400">
          <div className="px-2 py-1.5 text-xs font-medium text-slate-500">Suggestions</div>
          <div className="flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none hover:bg-slate-800 hover:text-slate-50">
            Go to Dashboard
          </div>
          <div className="flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none hover:bg-slate-800 hover:text-slate-50">
            View Analytics
          </div>
        </div>
      </div>
    </div>
  );
}
