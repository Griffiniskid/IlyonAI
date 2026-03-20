import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppShell } from "@/components/layout/app-shell";
import { vi } from "vitest";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

vi.mock("@/lib/hooks", () => ({
  useAlertSummary: () => ({ unreadCount: 0, alerts: [] }),
}));

describe("AppShell layout", () => {
  it("renders navigation items with correct group labels", async () => {
    render(<AppShell>{<div>content</div>}</AppShell>);

    // Verify main group headings are present in the sidebar
    const headings = ["Discover", "Analyze", "Smart Money", "Protect", "Portfolio", "Settings"];
    for (const heading of headings) {
      // Sidebar group heading (not a link anymore)
      expect(screen.getAllByText(heading)[0]).toBeInTheDocument();
    }

    // Verify some prominent links exist
    const importantLinks = [/Overview/i, /Dashboard/i, /Hub/i, /Shield/i];
    for (const linkText of importantLinks) {
      const links = screen.getAllByRole("link", { name: linkText });
      expect(links.length).toBeGreaterThan(0);
    }
    
    // Test the mobile nav toggle
    const menuBtn = screen.getByRole("button", { name: /Menu/i });
    expect(menuBtn).toBeInTheDocument();
    
    fireEvent.click(menuBtn);
    // After clicking menu, there should be mobile sheet headings as well
    const sheetHeadings = screen.getAllByText("Smart Money");
    expect(sheetHeadings.length).toBeGreaterThan(1); // One in sidebar, one in mobile sheet
  });
});
