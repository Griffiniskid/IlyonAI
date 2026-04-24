"use client";
import { useRef, useState } from "react";
import { ArrowUp } from "lucide-react";

interface Props {
  onSend: (msg: string) => void;
  disabled: boolean;
  placeholder?: string;
}

export function Composer({ onSend, disabled, placeholder }: Props) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const onChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const canSend = !!text.trim() && !disabled;
  return (
    <div data-testid="composer">
      <div className="flex items-end gap-2 rounded-2xl border border-white/10 bg-card/60 p-2">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={onChange}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder={placeholder ?? 'Refine the plan — e.g. "drop Pendle, split that 10% into Lido and Jito"...'}
          disabled={disabled}
          className="flex-1 resize-none bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/80 focus:outline-none disabled:opacity-50"
        />
        <button
          type="button"
          onClick={submit}
          disabled={!canSend}
          className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-background/40 text-muted-foreground disabled:opacity-50 enabled:hover:bg-background/80 enabled:hover:text-foreground transition"
          aria-label="Send"
        >
          <ArrowUp className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-2 text-center text-[11px] text-muted-foreground/70">
        Enter — send · Shift+Enter — new line
      </div>
    </div>
  );
}
