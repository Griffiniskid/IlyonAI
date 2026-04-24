import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/app-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn() }),
}));

function expectLinkPath(label: string, expectedHref: string) {
  const links = screen.getAllByRole("link", { name: new RegExp(label, "i") });
  const hasExpectedHref = links.some((link) => link.getAttribute("href") === expectedHref);
  expect(hasExpectedHref).toBe(true);
}

describe("Platform overhaul smoke journey", () => {
  it("keeps the Discover -> Smart Money -> Portfolio path navigable", () => {
    render(
      <AppShell>
        <div>content</div>
      </AppShell>
    );

    expectLinkPath("Discover", "/");
    expectLinkPath("Smart Money", "/smart-money");
    expectLinkPath("Portfolio", "/portfolio");
  });
});
