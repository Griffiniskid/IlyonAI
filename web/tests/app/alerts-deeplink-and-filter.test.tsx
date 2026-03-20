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
    useAlerts: () => ({
      data: [
        { id: "a-high", state: "new", severity: "high", title: "High whale dump", subject_id: "token-high" },
        { id: "a-low", state: "new", severity: "low", title: "Low wallet drift", subject_id: "token-low" },
      ],
    }),
  };
});

describe("Alerts Filtering and Deep Linking", () => {
  it("filters alerts by severity and opens row-specific deep link action", async () => {
    render(<AlertsPage />);

    expect(screen.getByRole("link", { name: /view token context for high whale dump/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view token context for low wallet drift/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: /view token context for low wallet drift/i }));
    expect(mockPush).toHaveBeenCalledWith("/token/token-low");

    fireEvent.click(screen.getByRole("button", { name: /severity: high/i }));

    expect(screen.getByRole("link", { name: /view token context for high whale dump/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /view token context for low wallet drift/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: /view token context for high whale dump/i }));
    expect(mockPush).toHaveBeenCalledWith("/token/token-high");
  });
});
