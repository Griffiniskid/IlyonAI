import { describe, expect, it } from "vitest";
import DefiRedirect from "@/app/defi/page";
import DefiDetailRedirect from "@/app/defi/[id]/page";

function expectDashboardRedirect(run: () => unknown) {
  try {
    run();
  } catch (error) {
    const redirectError = error as Error & { digest?: string };
    expect(redirectError.message).toBe("NEXT_REDIRECT");
    expect(redirectError.digest).toContain("/dashboard");
    return;
  }

  throw new Error("Expected Next redirect to be thrown");
}

describe("Defi redirects", () => {
  it("redirects defi discover to dashboard", () => {
    expectDashboardRedirect(() => DefiRedirect());
  });

  it("redirects defi detail to dashboard", () => {
    expectDashboardRedirect(() => DefiDetailRedirect());
  });
});
