import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppShell } from "@/components/layout/app-shell";

import { vi } from "vitest";

vi.mock("@/lib/hooks", () => ({
  useAlertSummary: () => ({ unreadCount: 0, alerts: [] }),
}));

describe("AppShell layout", () => {
  it("renders all top-level navigation groups", async () => {
    render(<AppShell>{<div>content</div>}</AppShell>);

    const labels = ["Discover", "Analyze", "Smart Money", "Protect", "Portfolio"];
    
    for (const label of labels) {
      const links = screen.getAllByRole("link", { name: new RegExp(label, "i") });
      expect(links).toHaveLength(2); // Desktop sidebar link and Mobile nav link
    }
  });
});
