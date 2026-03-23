import { render, screen, fireEvent } from "@testing-library/react";
import { vi } from "vitest";
import AlertsPage from "../../app/alerts/page";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("@/lib/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/hooks")>();
  return {
    ...actual,
    useAlertRules: () => ({ data: [] }),
    useUpdateAlert: () => ({ mutateAsync: vi.fn() }),
    useAlerts: () => ({
      data: [
        { id: "a-high", state: "new", severity: "high", title: "High whale dump", subject_id: "token-high" },
        { id: "a-low", state: "new", severity: "low", title: "Low wallet drift", kind: "wallet_drain", subject_id: "wallet-low" },
      ],
    }),
  };
});

describe("Alerts Filtering and Deep Linking", () => {
  it("filters alerts by severity and opens row-specific deep link action", async () => {
    render(<AlertsPage />);

    expect(screen.getByRole("link", { name: /open context for high whale dump/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open context for low wallet drift/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: /open context for low wallet drift/i }));
    expect(mockPush).toHaveBeenCalledWith("/wallet/wallet-low");

    fireEvent.click(screen.getByRole("button", { name: /^high/i }));

    expect(screen.getByRole("link", { name: /open context for high whale dump/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open context for low wallet drift/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: /open context for high whale dump/i }));
    expect(mockPush).toHaveBeenCalledWith("/token/token-high");
  });
});
