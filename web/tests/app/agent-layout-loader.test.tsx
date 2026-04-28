import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/agent/chat",
  useSearchParams: () => new URLSearchParams("tab=chat"),
}));

vi.mock("@/components/agent-app/MainApp", () => ({
  default: () => null,
}));

describe("Agent layout loader", () => {
  it("exports the loader imported by the agent layout", async () => {
    const mod = await import("@/components/agent-app/MainAppLoader");

    expect(mod.default).toBeTypeOf("function");
  });
});
