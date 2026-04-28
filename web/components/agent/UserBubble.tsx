"use client";

interface Props {
  content: string;
  time?: string;
}

export function UserBubble({ content, time }: Props) {
  return (
    <div data-testid="user-bubble" className="flex items-start justify-end gap-3">
      <div className="flex flex-col items-end">
        <div className="max-w-xl rounded-2xl rounded-tr-sm border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-100 whitespace-pre-wrap">
          {content}
        </div>
        {time && <span className="mt-1 mr-1 text-[11px] text-muted-foreground/70">{time}</span>}
      </div>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-300">
        <span className="text-xs font-semibold">U</span>
      </div>
    </div>
  );
}
