import { render, screen, fireEvent } from "@testing-library/react";
import { vi } from "vitest";
import AlertsPage from "../../app/alerts/page";
import { AlertsBell } from "../../components/layout/alerts-bell";
import { AppShell } from "@/components/layout/app-shell";

const useAlertSummaryMock = vi.fn();
const useAlertsMock = vi.fn();
const useAlertRulesMock = vi.fn();
const updateAlertMutateAsyncMock = vi.fn();

vi.mock("@/lib/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/hooks")>();
  return {
    ...actual,
    useAlertSummary: () => useAlertSummaryMock(),
    useAlerts: () => useAlertsMock(),
    useAlertRules: () => useAlertRulesMock(),
    useUpdateAlert: () => ({ mutateAsync: updateAlertMutateAsyncMock }),
  };
});

vi.mock("next/navigation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("next/navigation")>();
  return {
    ...actual,
    useRouter: () => ({ push: vi.fn() }),
    usePathname: () => "/alerts",
  };
});

describe("Alerts UI", () => {
  useAlertRulesMock.mockReturnValue({ data: [] });
  useAlertsMock.mockReturnValue({
    data: [
      { id: "a-high", state: "new", severity: "high", title: "High whale dump", subject_id: "token-high" },
      { id: "a-low", state: "new", severity: "low", title: "Low wallet drift", subject_id: "token-low" },
    ],
  });

  it("shows unread alert count in app shell bell", async () => {
    useAlertSummaryMock.mockReturnValue({ unreadCount: 3 });
    render(<AppShell>{<div>content</div>}</AppShell>);
    expect(screen.getByLabelText(/alerts/i)).toHaveTextContent("3");
  });

  it("shows unread alert count in shell bell", async () => {
    render(
      <AlertsBell
        unreadCount={3}
        alerts={[{ id: "a-high", state: "new", severity: "high", title: "High whale dump", subject_id: "token-high" }]}
      />
    );
    expect(screen.getByLabelText(/alerts/i)).toHaveTextContent("3");
  });

  it("opens tray and executes quick action", async () => {
    render(
      <AlertsBell
        unreadCount={2}
        alerts={[{ id: "a-high", state: "new", severity: "high", title: "High whale dump", subject_id: "token-high" }]}
      />
    );

    fireEvent.click(screen.getByLabelText(/alerts/i));
    fireEvent.click(screen.getByRole("button", { name: /^Seen$/i }));
    expect(updateAlertMutateAsyncMock).toHaveBeenCalledWith({ alertId: "a-high", action: "seen" });
  });

  it("requests browser notification permission when user enables alerts", async () => {
    const origNotification = global.Notification;
    global.Notification = {
      requestPermission: vi.fn().mockResolvedValue("granted"),
    } as any;
    
    render(<AlertsPage />);
    fireEvent.click(screen.getByRole("button", { name: /enable notifications/i }));
    expect(global.Notification.requestPermission).toHaveBeenCalled();
    expect(await screen.findByText(/permission status: granted/i)).toBeInTheDocument();
    
    global.Notification = origNotification;
  });

  it("shows empty state when backend has no alerts", async () => {
    useAlertsMock.mockReturnValueOnce({ data: [] });
    render(<AlertsPage />);
    expect(screen.getByText(/no alerts yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/high whale dump/i)).not.toBeInTheDocument();
  });
});
