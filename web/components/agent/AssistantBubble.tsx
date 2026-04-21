"use client";
import type { CardFrame } from "@/types/agent";
import { CardRenderer } from "./cards/CardRenderer";

interface Props {
  content: string;
  cards: CardFrame[];
}

export function AssistantBubble({ content, cards }: Props) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] rounded-lg bg-slate-800 p-4 space-y-3">
        <p className="text-sm text-slate-200 whitespace-pre-wrap">{content}</p>
        {cards.map((card) => (
          <CardRenderer key={card.card_id} card={card} />
        ))}
      </div>
    </div>
  );
}
