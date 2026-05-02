"use client";
import { useEffect, useLayoutEffect, useRef } from "react";
import { AssistantBubble, renderAssistantMarkdown } from "./AssistantBubble";
import { UserBubble } from "./UserBubble";
import { ReasoningAccordion } from "./ReasoningAccordion";
import { CardRenderer } from "./cards/CardRenderer";
import { StepStatusCard } from "./cards/StepStatusCard";
import { ChipPresets } from "./ChipPresets";
import type { AgentMessage } from "@/hooks/useAgentStream";
import type { CardFrame, PlanCompleteFrame, StepStatusFrame, ThoughtFrame, ToolFrame } from "@/types/agent";

interface Props {
  messages: AgentMessage[];
  currentSteps: {
    thoughts: ThoughtFrame[];
    tools: ToolFrame[];
    cards: CardFrame[];
    stepStatuses?: StepStatusFrame[];
    planCompletions?: PlanCompleteFrame[];
  };
  isStreaming: boolean;
  onSelect?: (prompt: string) => void;
}

function formatTime(d: Date = new Date()): string {
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

function formatElapsed(ms?: number): string {
  if (!ms) return "";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function splitParagraphs(content: string): string[] {
  return content
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
}

function thoughtLines(thoughts: ThoughtFrame[], tools: ToolFrame[]): string[] {
  // Interleave thoughts with a short summary of each tool call.
  const out: string[] = [];
  for (const t of thoughts) {
    const line = t.content.replace(/^Thought:\s*/i, "").trim();
    if (line) out.push(line);
  }
  for (const tl of tools) {
    out.push(`Called tool ${tl.name}(${Object.keys(tl.args || {}).join(", ")})`);
  }
  return out;
}

function AssistantParagraphs({
  content,
  cards,
  reasoning,
}: {
  content: string;
  cards: CardFrame[];
  reasoning?: { steps: number; lines: string[]; time?: string } | null;
}) {
  const paragraphs = splitParagraphs(content);
  // Keep a stable order: allocation → sentinel_matrix → execution_plan; other cards after.
  const byType = new Map<string, CardFrame>();
  for (const c of cards) if (!byType.has(c.card_type)) byType.set(c.card_type, c);
  const orderedTypes = ["allocation", "sentinel_matrix", "execution_plan"];
  const orderedCards: CardFrame[] = [];
  for (const t of orderedTypes) {
    const c = byType.get(t);
    if (c) orderedCards.push(c);
  }
  for (const c of cards) {
    if (!orderedTypes.includes(c.card_type) && !orderedCards.includes(c)) orderedCards.push(c);
  }
  const count = Math.max(paragraphs.length, orderedCards.length);
  const items: React.ReactNode[] = [];
  for (let i = 0; i < count; i++) {
    const p = paragraphs[i];
    if (p) {
      items.push(
        <AssistantBubble key={`p-${i}`}>
          <div className="space-y-2">
            {p.split(/\n/).map((ln, li) => (
              <p key={li} className="leading-relaxed">
                {renderAssistantMarkdown(ln)}
              </p>
            ))}
          </div>
        </AssistantBubble>,
      );
    }
    const card = orderedCards[i];
    if (card) items.push(<CardRenderer key={`c-${i}`} card={card} />);
  }
  return (
    <div className="space-y-3">
      {reasoning && reasoning.steps > 0 && (
        <ReasoningAccordion steps={reasoning.steps} time={reasoning.time} expanded lines={reasoning.lines} />
      )}
      {items}
    </div>
  );
}

export function MessageList({ messages, currentSteps, isStreaming, onSelect }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  useLayoutEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const threshold = 80;
    const distance = el.scrollHeight - el.clientHeight - el.scrollTop;
    if (distance < threshold) stickToBottom.current = true;
  }, [messages.length, currentSteps]);

  useEffect(() => {
    if (!stickToBottom.current) return;
    const node = bottomRef.current;
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, currentSteps.cards.length, currentSteps.thoughts.length]);

  const onScroll = () => {
    const el = scrollerRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.clientHeight - el.scrollTop;
    stickToBottom.current = distance < 120;
  };

  return (
    <div
      ref={scrollerRef}
      onScroll={onScroll}
      className="h-full space-y-5 overflow-y-auto px-5 py-6"
    >
      {messages.length === 0 && !isStreaming && (
        <div
          data-testid="chat-empty-state"
          className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-muted-foreground/80"
        >
          <div className="text-base font-semibold text-foreground/80">
            Ask the Ilyon agent something.
          </div>
          <div className="max-w-md leading-relaxed">
            Try an allocation prompt — e.g. <em>&quot;I have $10,000 USDC. Allocate it across the best staking and yield opportunities, risk-weighted using Sentinel scores.&quot;</em>
          </div>
        </div>
      )}
      {messages.map((msg, i) => {
        if (msg.role === "user") {
          return <UserBubble key={i} content={msg.content} time={formatTime()} />;
        }
        const reasoning = msg.thoughts.length > 0
          ? {
              steps: msg.thoughts.length,
              lines: thoughtLines(msg.thoughts, msg.tools),
              time: msg.elapsed_ms ? formatElapsed(msg.elapsed_ms) : undefined,
            }
          : null;
        return (
          <div key={i} className="space-y-3">
            <AssistantParagraphs
              content={msg.content}
              cards={msg.cards}
              reasoning={reasoning}
            />
            {msg.stepStatuses?.map((frame) => (
              <StepStatusCard key={`${frame.plan_id}-${frame.step_id}-${frame.status}-${frame.tx_hash ?? ""}`} frame={frame} />
            ))}
          </div>
        );
      })}
      {isStreaming && (currentSteps.thoughts.length > 0 || currentSteps.cards.length > 0 || (currentSteps.stepStatuses?.length ?? 0) > 0) && (
        <div className="space-y-3">
          {currentSteps.thoughts.length > 0 && (
            <ReasoningAccordion
              steps={currentSteps.thoughts.length}
              lines={thoughtLines(currentSteps.thoughts, currentSteps.tools)}
              expanded
            />
          )}
          {currentSteps.cards.map((c) => (
            <CardRenderer key={c.card_id} card={c} />
          ))}
          {currentSteps.stepStatuses?.map((frame) => (
            <StepStatusCard key={`${frame.plan_id}-${frame.step_id}-${frame.status}-${frame.tx_hash ?? ""}`} frame={frame} />
          ))}
        </div>
      )}
      {isStreaming && currentSteps.thoughts.length === 0 && (
        <div className="flex items-center gap-2 ml-11 text-[11px] text-muted-foreground">
          <span className="h-2 w-2 animate-ping rounded-full bg-purple-400" />
          <span>Thinking…</span>
        </div>
      )}
      {messages.length > 0 && onSelect && (
        <div className="ml-11">
          <ChipPresets onSelect={onSelect} disabled={isStreaming} />
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
