import type { CardFrame, ThoughtFrame, ToolFrame } from "@/types/agent";

export interface StoredAgentMessage {
  role: "user" | "assistant";
  content: string;
  cards: CardFrame[];
  thoughts: ThoughtFrame[];
  tools: ToolFrame[];
  elapsed_ms?: number;
}

export interface StoredAgentSession {
  id: string;
  title: string;
  updatedAt: string;
  messages: StoredAgentMessage[];
}

const STORAGE_KEY = "ilyon.agent.guest-sessions";

function hasWindow(): boolean {
  return typeof window !== "undefined";
}

export function deriveSessionTitle(messages: StoredAgentMessage[]): string {
  const firstUser = messages.find((message) => message.role === "user");
  if (!firstUser) return "New chat";
  const title = firstUser.content.trim().replace(/\s+/g, " ");
  return title.length > 56 ? `${title.slice(0, 56)}...` : title;
}

export function loadGuestSessions(): StoredAgentSession[] {
  if (!hasWindow()) return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function loadGuestSession(sessionId: string): StoredAgentSession | null {
  return loadGuestSessions().find((session) => session.id === sessionId) ?? null;
}

export function saveGuestSession(session: StoredAgentSession): void {
  if (!hasWindow()) return;
  const sessions = loadGuestSessions().filter((entry) => entry.id !== session.id);
  sessions.unshift(session);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions.slice(0, 20)));
}

export function deleteGuestSession(sessionId: string): void {
  if (!hasWindow()) return;
  const sessions = loadGuestSessions().filter((session) => session.id !== sessionId);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

export function touchGuestSession(sessionId: string, messages: StoredAgentMessage[]): void {
  saveGuestSession({
    id: sessionId,
    title: deriveSessionTitle(messages),
    updatedAt: new Date().toISOString(),
    messages,
  });
}
