"use client";

export const API_BASE = "/api/v1";

export interface AuthUser {
  id: number;
  email: string | null;
  display_name: string | null;
  wallet_address: string | null;
}

export interface AuthSession {
  token: string;
  user: AuthUser;
}

export interface ChatSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ChatDetail extends ChatSummary {
  messages: ChatMessage[];
}

export interface AgentRunResponse {
  session_id: string;
  chat_id: string | null;
  response: string;
}

const STORAGE = {
  token: "ap_token",
  user: "ap_user",
  walletType: "ap_wallet_type",
  evmWallet: "ap_wallet",
  solWallet: "ap_sol_wallet",
  phantomCtx: "ap_phantom_wallet_context",
  chatSession: "ap_chat_session",
} as const;

export const authStorage = {
  getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(STORAGE.token);
  },
  setSession(s: AuthSession): void {
    localStorage.setItem(STORAGE.token, s.token);
    localStorage.setItem(STORAGE.user, JSON.stringify(s.user));
  },
  clear(): void {
    localStorage.removeItem(STORAGE.token);
    localStorage.removeItem(STORAGE.user);
    localStorage.removeItem(STORAGE.walletType);
  },
  getUser(): AuthUser | null {
    if (typeof window === "undefined") return null;
    const raw = localStorage.getItem(STORAGE.user);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AuthUser;
    } catch {
      return null;
    }
  },
  getWalletType(): "metamask" | "phantom" | null {
    if (typeof window === "undefined") return null;
    const v = localStorage.getItem(STORAGE.walletType);
    return v === "metamask" || v === "phantom" ? v : null;
  },
  setWalletType(t: "metamask" | "phantom" | null): void {
    if (t === null) localStorage.removeItem(STORAGE.walletType);
    else localStorage.setItem(STORAGE.walletType, t);
  },
  getOrCreateSessionId(): string {
    if (typeof window === "undefined") return "ssr";
    let id = localStorage.getItem(STORAGE.chatSession);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(STORAGE.chatSession, id);
    }
    return id;
  },
};

async function authedFetch(
  path: string,
  init: RequestInit = {},
  token: string | null = null,
): Promise<Response> {
  const headers = new Headers(init.headers || {});
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  const t = token ?? authStorage.getToken();
  if (t) headers.set("Authorization", `Bearer ${t}`);
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

export const api = {
  async health(): Promise<boolean> {
    try {
      const r = await fetch(`${API_BASE}/agent-health`, {
        signal: AbortSignal.timeout(3000),
      });
      return r.ok;
    } catch {
      return false;
    }
  },
  async me(token?: string): Promise<AuthUser | null> {
    const r = await authedFetch("/auth/me", {}, token ?? null);
    if (!r.ok) return null;
    return (await r.json()) as AuthUser;
  },
  async register(email: string, password: string, display_name?: string): Promise<AuthSession> {
    const r = await authedFetch("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name }),
    });
    if (!r.ok) throw new Error((await r.text()) || "Register failed");
    return (await r.json()) as AuthSession;
  },
  async login(email: string, password: string): Promise<AuthSession> {
    const r = await authedFetch("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    if (!r.ok) throw new Error((await r.text()) || "Login failed");
    return (await r.json()) as AuthSession;
  },
  async metamask(payload: { address: string; signature: string; message: string }): Promise<AuthSession> {
    const r = await authedFetch("/auth/metamask", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error((await r.text()) || "Wallet login failed");
    return (await r.json()) as AuthSession;
  },
  async phantom(payload: { public_key: string; signature: string; message: string; display_name?: string }): Promise<AuthSession> {
    const r = await authedFetch("/auth/phantom", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error((await r.text()) || "Phantom login failed");
    return (await r.json()) as AuthSession;
  },
  async listChats(): Promise<ChatSummary[]> {
    const r = await authedFetch("/chats");
    if (!r.ok) return [];
    return (await r.json()) as ChatSummary[];
  },
  async createChat(title?: string): Promise<ChatSummary> {
    const r = await authedFetch("/chats", {
      method: "POST",
      body: JSON.stringify({ title: title ?? "New Chat" }),
    });
    if (!r.ok) throw new Error("Create chat failed");
    return (await r.json()) as ChatSummary;
  },
  async getChat(id: string): Promise<ChatDetail | null> {
    const r = await authedFetch(`/chats/${id}`);
    if (!r.ok) return null;
    return (await r.json()) as ChatDetail;
  },
  async deleteChat(id: string): Promise<void> {
    await authedFetch(`/chats/${id}`, { method: "DELETE" });
  },
  async runAgent(payload: {
    user_address: string;
    solana_address?: string | null;
    query: string;
    chain_id: number;
    session_id: string;
    chat_id?: string | null;
    wallet_type?: "metamask" | "phantom" | null;
  }): Promise<AgentRunResponse> {
    const r = await authedFetch("/agent", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error((await r.text()) || "Agent request failed");
    return (await r.json()) as AgentRunResponse;
  },
  async portfolio(address: string): Promise<unknown> {
    const r = await fetch(`/api/portfolio/${address}`, { signal: AbortSignal.timeout(60000) });
    if (!r.ok) throw new Error("Portfolio fetch failed");
    return await r.json();
  },
};
