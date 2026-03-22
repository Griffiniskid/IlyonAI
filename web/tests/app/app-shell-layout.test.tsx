import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppShell } from "@/components/layout/app-shell";
import { vi } from "vitest";

const mockPathname = vi.fn(() => "/");

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname(),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/hooks", () => ({
  useAlertSummary: () => ({ unreadCount: 0, alerts: [] }),
  useUpdateAlert: () => ({ mutateAsync: vi.fn() }),
}));

describe("AppShell layout", () => {
  it("renders discoverable nav routes and mobile core domains", async () => {
    mockPathname.mockReturnValue("/");
    render(<AppShell>{<div>content</div>}</AppShell>);

    const headings = ["Discover", "Smart Money", "Protect", "Portfolio", "Settings"];
    for (const heading of headings) {
      expect(screen.getAllByText(heading)[0]).toBeInTheDocument();
    }

    const expectedRoutes = [
      "/",
      "/dashboard",
      "/trending",
      "/defi",
      "/smart-money",
      "/whales",
      "/flows",
      "/wallet",
      "/entity",
      "/shield",
      "/audits",
      "/rekt",
      "/alerts",
      "/portfolio",
      "/settings",
    ];

    for (const href of expectedRoutes) {
      const link = screen.getAllByRole("link").find((node) => node.getAttribute("href") === href);
      expect(link, `Expected to find nav link for ${href}`).toBeTruthy();
    }

    expect(screen.getAllByText("Entity")[0]).toBeInTheDocument();

    const mobileNav = screen.getByRole("navigation", { name: /Primary mobile/i });
    for (const domain of ["Discover", "Smart Money", "Protect", "Portfolio"]) {
      expect(within(mobileNav).getByRole("link", { name: domain })).toBeInTheDocument();
    }

    const menuBtn = screen.getByRole("button", { name: /Menu/i });
    expect(menuBtn).toBeInTheDocument();

    fireEvent.click(menuBtn);
    expect(screen.getAllByRole("link", { name: "Settings" }).length).toBeGreaterThan(0);
  });

  it("marks nested wallet routes active in mobile sheet", async () => {
    mockPathname.mockReturnValue("/wallet/abc123");
    render(<AppShell>{<div>content</div>}</AppShell>);

    fireEvent.click(screen.getByRole("button", { name: /Menu/i }));

    const walletLinks = screen.getAllByRole("link", { name: "Wallet" });
    const activeWalletLink = walletLinks.find((link) => {
      const className = link.getAttribute("class") ?? "";
      return className.includes("bg-primary/10") && className.includes("text-primary");
    });

    expect(activeWalletLink).toBeTruthy();
  });

  it("marks settings link active for /settings route", async () => {
    mockPathname.mockReturnValue("/settings");
    render(<AppShell>{<div>content</div>}</AppShell>);

    const settingsLinks = screen.getAllByRole("link", { name: "Settings" });
    const activeSettingsLink = settingsLinks.find((link) => {
      const className = link.getAttribute("class") ?? "";
      return className.includes("bg-primary/10") && className.includes("text-primary");
    });

    expect(activeSettingsLink).toBeTruthy();
  });
});
