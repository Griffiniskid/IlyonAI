"use client";
import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
}

export function AssistantBubble({ children }: Props) {
  return (
    <div data-testid="assistant-bubble" className="flex items-start gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-purple-500/15 text-purple-300">
        <span className="text-xs font-semibold">A</span>
      </div>
      <div className="max-w-2xl rounded-2xl rounded-tl-sm border border-white/10 bg-card/70 px-4 py-3 text-sm text-foreground/90 backdrop-blur">
        {children}
      </div>
    </div>
  );
}

export function renderAssistantMarkdown(text: string): ReactNode[] {
  // Inline-bold (**x**) + *italic*. Keeps everything in a single <p> per call.
  const parts: ReactNode[] = [];
  const regex = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let lastIdx = 0;
  let match: RegExpExecArray | null;
  let keyIdx = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIdx) parts.push(text.slice(lastIdx, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      parts.push(
        <strong key={`b-${keyIdx++}`} className="font-semibold text-foreground">
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      parts.push(
        <em key={`i-${keyIdx++}`} className="italic">
          {token.slice(1, -1)}
        </em>,
      );
    }
    lastIdx = match.index + token.length;
  }
  if (lastIdx < text.length) parts.push(text.slice(lastIdx));
  return parts;
}
