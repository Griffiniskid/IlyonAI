import { render, screen, fireEvent } from "@testing-library/react";
import { vi } from "vitest";
import AlertsPage from "../../app/alerts/page";
import { AlertsBell } from "../../components/layout/alerts-bell";
import { AppShell } from "@/components/layout/app-shell";

const useAlertSummaryMock = vi.fn();
const useAlertsMock = vi.fn();

vi.mock("@/lib/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/hooks")>();
  return {
    ...actual,
    useAlertSummary: () => useAlertSummaryMock(),
    useAlerts: () => useAlertsMock(),
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe("Alerts UI", () => {
  useAlertsMock.mockReturnValue({
    data: [
      { id: "a-high", state: "new", severity: "high", title: "High whale dump", subject_id: "token-high" },
      { id: "a-low", state: "new", severity: "low", title: "Low wallet drift", subject_id: "token-low" },
    ],
  });

  it("shows unread alert count in app shell bell", async () => {
    useAlertSummaryMock.mockReturnValue({ unreadCount: 3 });
    render(<AppShell>{<div>content</div>}</AppShell>);
    expect(screen.getByRole("button", { name: /alerts/i })).toHaveTextContent("3");
  });

  it("shows unread alert count in shell bell", async () => {
    render(<AlertsBell unreadCount={3} />);
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("requests browser notification permission when user enables alerts", async () => {
    const origNotification = global.Notification;
    global.Notification = {
      requestPermission: vi.fn().mockResolvedValue("granted"),
    } as any;
    
    render(<AlertsPage />);
    fireEvent.click(screen.getByRole("button", { name: /enable browser notifications/i }));
    expect(global.Notification.requestPermission).toHaveBeenCalled();
    expect(await screen.findByText(/notification permission: granted/i)).toBeInTheDocument();
    
    global.Notification = origNotification;
  });

  it("shows empty state when backend has no alerts", async () => {
    useAlertsMock.mockReturnValueOnce({ data: [] });
    render(<AlertsPage />);
    expect(screen.getByText(/no alerts yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/high whale dump/i)).not.toBeInTheDocument();
  });
});
