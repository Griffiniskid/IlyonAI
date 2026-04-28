import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import MainApp from "@/components/agent-app/MainApp";

vi.mock("framer-motion", () => {
  const React = require("react") as typeof import("react");
  const filteredProps = new Set([
    "animate",
    "exit",
    "initial",
    "layout",
    "transition",
    "variants",
    "whileHover",
    "whileTap",
  ]);

  const motion = new Proxy({}, {
    get: (_target, tag: string) => React.forwardRef<HTMLElement, Record<string, unknown>>((props, ref) => {
      const domProps = Object.fromEntries(Object.entries(props).filter(([key]) => !filteredProps.has(key)));
      return React.createElement(tag, { ...domProps, ref });
    }),
  });

  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    motion,
  };
});

const jsonResponse = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  }));

function installFetchMock() {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);

    if (url.includes("coingecko")) {
      return jsonResponse({});
    }

    if (url.includes("/api/v1/agent-health")) {
      return Promise.resolve(new Response("ok", { status: 200 }));
    }

    if (url.includes("/api/v1/auth/me")) {
      return jsonResponse({
        id: 7,
        display_name: "Test Wallet",
        wallet_address: "0x1234567890abcdef",
      });
    }

    if (url.endsWith("/api/v1/chats")) {
      return jsonResponse([
        { id: "chat-1", title: "Balance check", updated_at: "2026-04-27T21:00:00.000Z" },
      ]);
    }

    if (url.endsWith("/api/v1/chats/chat-1")) {
      return jsonResponse({
        messages: [
          { id: 1, role: "user", content: "My balance", created_at: "2026-04-27T21:00:00.000Z" },
          { id: 2, role: "assistant", content: "Here is your balance", created_at: "2026-04-27T21:00:01.000Z" },
        ],
      });
    }

    if (url.includes("/api/v1/agent")) {
      return jsonResponse({ response: "Assistant response", chat_id: "chat-1" });
    }

    return jsonResponse({});
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("agent chat regressions", () => {
  beforeEach(() => {
    localStorage.clear();
    window.history.pushState({}, "", "/agent/chat?tab=chat");
    HTMLElement.prototype.scrollIntoView = vi.fn();
    HTMLElement.prototype.scrollTo = vi.fn();
    installFetchMock();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("keeps the agent route constrained to its parent shell instead of sizing to the viewport", () => {
    const css = readFileSync(path.join(process.cwd(), "app/agent/agent-overrides.css"), "utf8");
    const layout = readFileSync(path.join(process.cwd(), "app/agent/layout.tsx"), "utf8");

    expect(layout).toMatch(/data-agent-route/);
    expect(css).not.toMatch(/height:\s*calc\(100vh\s*-\s*28px\)/);
    expect(css).toMatch(/body:has\(\[data-agent-route\]\)\s+div:has\(>\s*main\s*>\s*\[data-agent-route\]\)\s*{[\s\S]*height:\s*calc\(100vh\s*-\s*2rem\)\s*!important/);
    expect(css).toMatch(/body:has\(\[data-agent-route\]\)\s+main:has\(>\s*\[data-agent-route\]\)\s*{[\s\S]*height:\s*100%\s*!important/);
    expect(css).toMatch(/\.app\s*{[\s\S]*height:\s*100%\s*!important/);
    expect(css).toMatch(/\.app\s+\.main\s+\.content-canvas\s*>\s*\.tab-panel\s*{[\s\S]*min-height:\s*0\s*!important/);
    expect(css).toMatch(/\.app\s+\.content-canvas:has\(\.chat-wrap\)\s*{[\s\S]*overflow:\s*hidden\s*!important/);
    expect(css).toMatch(/body:has\(\[data-agent-route\]\)\s*{[\s\S]*overflow-y:\s*hidden\s*!important/);
  });

  it("uses a messenger layout where footer is hidden and only the message transcript scrolls", () => {
    const css = readFileSync(path.join(process.cwd(), "app/agent/agent-overrides.css"), "utf8");

    expect(css).toMatch(/body:has\(\[data-agent-route\]\)\s+footer\s*{[\s\S]*display:\s*none\s*!important/);
    expect(css).toMatch(/\.chat-wrap\s*>\s*\.page-shell\s*{[\s\S]*grid-template-rows:\s*auto\s+minmax\(0,\s*1fr\)\s+auto\s*!important/);
    expect(css).toMatch(/\.chat-wrap\s+\.messages\s*{[\s\S]*overflow-y:\s*auto\s*!important/);
    expect(css).toMatch(/\.chat-wrap\s+\.chat-composer\s*{[\s\S]*grid-row:\s*3\s*!important/);
  });

  it("keeps the composer outside the scrollable message transcript", () => {
    render(<MainApp />);

    const transcript = document.querySelector(".chat-wrap .messages");
    const composer = document.querySelector(".chat-wrap .chat-composer");
    const quickBar = document.querySelector(".chat-wrap .quick-bar");
    const inputArea = document.querySelector(".chat-wrap .input-area");

    expect(transcript).toBeTruthy();
    expect(composer).toBeTruthy();
    expect(quickBar).toBeTruthy();
    expect(inputArea).toBeTruthy();
    expect(transcript?.contains(quickBar)).toBe(false);
    expect(transcript?.contains(inputArea)).toBe(false);
    expect(composer?.contains(quickBar)).toBe(true);
    expect(composer?.contains(inputArea)).toBe(true);
    expect(transcript?.nextElementSibling).toBe(composer);
  });

  it("autoscrolls the transcript container instead of calling scrollIntoView on the page", () => {
    const source = readFileSync(path.join(process.cwd(), "components/agent-app/MainApp.tsx"), "utf8");

    expect(source).not.toMatch(/bottomRef\.current\?\.scrollIntoView/);
    expect(source).toMatch(/messagesRef\s*=\s*useRef<HTMLDivElement>\(null\)/);
    expect(source).toMatch(/messagesRef\.current\.scrollTop\s*=\s*messagesRef\.current\.scrollHeight/);
    expect(source).toMatch(/<div className="messages" ref=\{messagesRef\}>/);
  });

  it("opens the Chats panel from the visible route header even before authenticated history exists", async () => {
    localStorage.setItem("ap_sol_wallet", "So11111111111111111111111111111111111111112");

    render(<MainApp />);

    fireEvent.click(screen.getByRole("button", { name: /Chats$/ }));

    expect(await screen.findByText(/No chats yet/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /New Chat/ })).toBeTruthy();
  });

  it("loads authenticated chat history and starts a clean new conversation", async () => {
    localStorage.setItem("ap_token", "token-123");

    render(<MainApp />);

    await waitFor(() => expect(screen.getByRole("button", { name: /1 chats/ })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /1 chats/ }));
    fireEvent.click(await screen.findByText("Balance check"));

    expect(await screen.findByText("My balance")).toBeInTheDocument();
    expect(await screen.findByText("Here is your balance")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /New$/ }));

    expect(screen.queryByText("My balance")).not.toBeInTheDocument();
    expect(screen.queryByText("Here is your balance")).not.toBeInTheDocument();
    expect(screen.getByText(/Hello! I'm your AI crypto assistant/)).toBeInTheDocument();
  });
});
