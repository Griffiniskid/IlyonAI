import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/agent-app/MainApp", () => ({
  default: () => null,
}));

describe("agent layout imports", () => {
  it("loads the mounted agent app without missing modules", async () => {
    const mod = await import("@/app/agent/layout");

    expect(mod.default).toBeTypeOf("function");
  });
});
