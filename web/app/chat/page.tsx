"use client";

import { Fragment, useState, useRef, useEffect, useCallback } from "react";
import type { ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sparkles,
  Send,
  Loader2,
  RefreshCw,
  Bot,
  User,
  Zap,
  Shield,
  TrendingUp,
  Search,
  ChevronDown,
  ChevronUp,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import * as api from "@/lib/api";
import type { ChatMessageResponse, ChatToolCall } from "@/types";

interface Message {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ChatToolCall[];
  latencyMs?: number;
}

function renderInline(text: string) {
  const segments = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g);

  return segments.filter(Boolean).map((segment, index) => {
    if (segment.startsWith("`") && segment.endsWith("`")) {
      return (
        <code key={index} className="rounded bg-black/30 px-1.5 py-0.5 font-mono text-[0.9em] text-emerald-300">
          {segment.slice(1, -1)}
        </code>
      );
    }

    if (segment.startsWith("**") && segment.endsWith("**")) {
      return <strong key={index} className="font-semibold text-foreground">{segment.slice(2, -2)}</strong>;
    }

    if (segment.startsWith("*") && segment.endsWith("*")) {
      return <em key={index} className="italic">{segment.slice(1, -1)}</em>;
    }

    return <Fragment key={index}>{segment}</Fragment>;
  });
}

function MarkdownContent({ content }: { content: string }) {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const language = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      i += 1;

      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i += 1;
      }

      i += 1;
      blocks.push(
        <div key={blocks.length} className="overflow-hidden rounded-xl border border-white/10 bg-black/30">
          {language && <div className="border-b border-white/10 px-3 py-2 text-[11px] uppercase tracking-[0.2em] text-muted-foreground">{language}</div>}
          <pre className="overflow-x-auto px-3 py-3 font-mono text-xs text-emerald-200">
            <code>{codeLines.join("\n")}</code>
          </pre>
        </div>
      );
      continue;
    }

    if (trimmed.includes("|") && i + 1 < lines.length && /^\s*\|?\s*[-:]+[-| :]*\|?\s*$/.test(lines[i + 1])) {
      const tableLines: string[] = [line, lines[i + 1]];
      i += 2;

      while (i < lines.length && lines[i].includes("|")) {
        tableLines.push(lines[i]);
        i += 1;
      }

      const rows = tableLines
        .filter((tableLine, index) => index !== 1)
        .map((tableLine) => tableLine.split("|").map((cell) => cell.trim()).filter((_, index, arr) => !(index === 0 && !arr[0]) && !(index === arr.length - 1 && !arr[arr.length - 1])));

      const [header, ...body] = rows;
      blocks.push(
        <div key={blocks.length} className="overflow-x-auto rounded-xl border border-white/10 bg-white/[0.03]">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-white/[0.04] text-muted-foreground">
              <tr>
                {header.map((cell, index) => (
                  <th key={index} className="px-3 py-2 font-medium">{renderInline(cell)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((row, rowIndex) => (
                <tr key={rowIndex} className="border-t border-white/10">
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex} className="px-3 py-2 align-top text-muted-foreground">{renderInline(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    if (/^#{1,3}\s+/.test(trimmed)) {
      const level = trimmed.match(/^#+/)?.[0].length ?? 1;
      const text = trimmed.replace(/^#{1,3}\s+/, "");
      const className = level === 1 ? "text-lg font-semibold" : level === 2 ? "text-base font-semibold" : "text-sm font-semibold uppercase tracking-wide text-muted-foreground";
      blocks.push(<div key={blocks.length} className={className}>{renderInline(text)}</div>);
      i += 1;
      continue;
    }

    if (/^[-*+]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*+]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*+]\s+/, ""));
        i += 1;
      }
      blocks.push(
        <ul key={blocks.length} className="space-y-1 pl-5 text-sm text-muted-foreground list-disc">
          {items.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ul>
      );
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
        i += 1;
      }
      blocks.push(
        <ol key={blocks.length} className="space-y-1 pl-5 text-sm text-muted-foreground list-decimal">
          {items.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ol>
      );
      continue;
    }

    const paragraphLines: string[] = [trimmed];
    i += 1;

    while (i < lines.length) {
      const next = lines[i].trim();
      if (!next || next.startsWith("```") || /^#{1,3}\s+/.test(next) || /^[-*+]\s+/.test(next) || /^\d+\.\s+/.test(next)) {
        break;
      }
      if (next.includes("|") && i + 1 < lines.length && /^\s*\|?\s*[-:]+[-| :]*\|?\s*$/.test(lines[i + 1])) {
        break;
      }
      paragraphLines.push(next);
      i += 1;
    }

    blocks.push(
      <p key={blocks.length} className="text-sm leading-7 text-muted-foreground">
        {renderInline(paragraphLines.join(" "))}
      </p>
    );
  }

  return <div className="space-y-3">{blocks}</div>;
}

function formatToolArgs(args: Record<string, unknown>) {
  const entries = Object.entries(args ?? {});
  if (!entries.length) {
    return "No arguments";
  }

  return entries
    .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join("\n");
}

const SUGGESTIONS = [
  { icon: Shield, text: "Is this token safe? 0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984" },
  { icon: TrendingUp, text: "What are the best yield farms on Arbitrum right now?" },
  { icon: Search, text: "Has Curve Finance ever been hacked?" },
  { icon: Zap, text: "Scan my wallet for risky approvals: 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045" },
];

function ToolCallBadge({ call }: { call: ChatToolCall }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-white/10 bg-white/5 text-xs">
      <button
        className="flex items-center gap-2 w-full px-3 py-2 hover:bg-white/5 transition-colors text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <Wrench className="h-3 w-3 text-blue-400 shrink-0" />
        <span className="text-blue-400 font-mono">{call.tool}</span>
        <span className="ml-auto max-w-[45%] truncate text-right text-muted-foreground">
          {call.result_preview.slice(0, 60)}
          {call.result_preview.length > 60 ? "..." : ""}
        </span>
        {open ? <ChevronUp className="h-3 w-3 shrink-0" /> : <ChevronDown className="h-3 w-3 shrink-0" />}
      </button>
      {open && (
        <div className="space-y-3 border-t border-white/10 px-3 py-3">
          <div>
            <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-muted-foreground">Arguments</div>
            <pre className="overflow-x-auto rounded-lg bg-black/25 px-3 py-2 font-mono text-[11px] text-slate-300">
              <code>{formatToolArgs(call.args)}</code>
            </pre>
          </div>
          <div>
            <div className="mb-1 text-[11px] uppercase tracking-[0.2em] text-muted-foreground">Result</div>
            <div className="rounded-lg bg-black/20 px-3 py-3">
              <MarkdownContent content={call.result_preview} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      {/* Avatar */}
      <div className={cn(
        "w-8 h-8 rounded-full shrink-0 flex items-center justify-center",
        isUser ? "bg-emerald-500/20 border border-emerald-500/30" : "bg-blue-500/20 border border-blue-500/30"
      )}>
        {isUser ? (
          <User className="h-4 w-4 text-emerald-400" />
        ) : (
          <Bot className="h-4 w-4 text-blue-400" />
        )}
      </div>

      {/* Content */}
      <div className={cn("max-w-[80%] space-y-1", isUser ? "items-end" : "items-start")}>
        <div className={cn(
          "rounded-2xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-emerald-600 text-black rounded-tr-sm"
            : "bg-card border border-white/10 rounded-tl-sm"
        )}>
          {isUser ? (
            <div className="whitespace-pre-wrap">{message.content}</div>
          ) : (
            <MarkdownContent content={message.content} />
          )}
        </div>

        {/* Tool calls */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="space-y-1 w-full">
            {message.toolCalls.map((call, i) => (
              <ToolCallBadge key={i} call={call} />
            ))}
          </div>
        )}

        {/* Latency */}
        {message.latencyMs != null && (
          <div className="text-xs text-muted-foreground px-1">
            {(message.latencyMs / 1000).toFixed(1)}s
          </div>
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center bg-blue-500/20 border border-blue-500/30">
        <Bot className="h-4 w-4 text-blue-400" />
      </div>
      <div className="rounded-2xl rounded-tl-sm px-4 py-3 bg-card border border-white/10">
        <div className="flex items-center gap-1">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="w-2 h-2 rounded-full bg-muted-foreground animate-bounce"
              style={{ animationDelay: `${i * 150}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const sendMutation = useMutation({
    mutationFn: (message: string) => api.sendChatMessage(message, sessionId),
    onSuccess: (data: ChatMessageResponse) => {
      setSessionId(data.session_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.reply,
          toolCalls: data.tool_calls_made,
          latencyMs: data.latency_ms,
        },
      ]);
    },
    onError: () => {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, something went wrong. Please try again.",
        },
      ]);
    },
  });

  const handleSend = (text?: string) => {
    const message = (text ?? input).trim();
    if (!message || sendMutation.isPending) return;

    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setInput("");
    sendMutation.mutate(message);
    inputRef.current?.focus();
  };

  const handleNewSession = async () => {
    setMessages([]);
    setSessionId(undefined);
    try {
      const { session_id } = await api.newChatSession();
      setSessionId(session_id);
    } catch {
      // ignore
    }
  };

  const isWaiting = sendMutation.isPending;
  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] max-w-3xl mx-auto px-4">
      {/* Header */}
      <div className="flex items-center justify-between py-4 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-semibold">Ilyon AI Chat</h1>
            <p className="text-xs text-muted-foreground">
              Ask anything about DeFi security, tokens, or protocols
            </p>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={handleNewSession} disabled={isWaiting}>
          <RefreshCw className="h-4 w-4 mr-2" />
          New Chat
        </Button>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto space-y-6 pb-4">
        {/* Empty state */}
        {isEmpty && (
          <div className="flex flex-col items-center justify-center h-full py-8">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500/20 to-purple-600/20 border border-blue-500/30 flex items-center justify-center mb-6">
              <Sparkles className="h-8 w-8 text-blue-400" />
            </div>
            <h2 className="text-xl font-semibold mb-2">How can I help?</h2>
            <p className="text-sm text-muted-foreground text-center max-w-sm mb-8">
              I can analyze tokens, scan wallets, review protocol risk, find yield opportunities, and more.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-xl">
              {SUGGESTIONS.map(({ icon: Icon, text }) => (
                <button
                  key={text}
                  onClick={() => handleSend(text)}
                  className="flex items-start gap-3 p-3 rounded-xl bg-card border border-white/10 hover:border-emerald-500/30 hover:bg-emerald-500/5 text-left transition-all text-sm group"
                >
                  <Icon className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5 group-hover:scale-110 transition-transform" />
                  <span className="text-muted-foreground group-hover:text-foreground transition-colors">{text}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Message list */}
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}

        {/* Typing indicator */}
        {isWaiting && <TypingIndicator />}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="py-4 shrink-0">
        <div className={cn(
          "flex gap-2 p-2 rounded-2xl transition-all border",
          "bg-card/60 border-white/10 focus-within:border-emerald-500/40 focus-within:shadow-lg focus-within:shadow-emerald-500/5"
        )}>
          <Input
            ref={inputRef}
            placeholder="Ask about any token, wallet, or DeFi protocol…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            className="border-none bg-transparent focus-visible:ring-0 text-sm"
            disabled={isWaiting}
          />
          <Button
            onClick={() => handleSend()}
            disabled={!input.trim() || isWaiting}
            className="h-10 w-10 p-0 rounded-xl bg-emerald-600 hover:bg-emerald-500 shrink-0"
          >
            {isWaiting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground text-center mt-2">
          AI may make mistakes. Always verify critical information independently.
        </p>
      </div>
    </div>
  );
}
