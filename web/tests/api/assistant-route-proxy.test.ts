import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

describe("assistant route proxy", () => {
  it("uses an explicit node route handler instead of only Next rewrites", () => {
    const route = readFileSync(join(process.cwd(), "app/api/v1/agent/route.ts"), "utf8");

    expect(route).toContain('runtime = "nodejs"');
    expect(route).toContain("ASSISTANT_API_TARGET");
    expect(route).toContain("/api/v1/agent");
    expect(route).toContain("AbortSignal.timeout");
  });
});
