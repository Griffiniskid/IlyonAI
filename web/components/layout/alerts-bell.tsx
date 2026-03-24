import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bell } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getAlertContextHref } from "@/lib/alerts";
import { useUpdateAlert } from "@/lib/hooks";
import type { AlertRecordResponse } from "@/types";

export function AlertsBell({ unreadCount, alerts = [] }: { unreadCount: number; alerts?: AlertRecordResponse[] }) {
  const [isTrayOpen, setIsTrayOpen] = useState(false);
  const updateAlert = useUpdateAlert();
  const router = useRouter();
  const trayAlerts = alerts.slice(0, 5);

  const quickAction = async (alertId: string, action: "seen" | "acknowledge") => {
    await updateAlert.mutateAsync({ alertId, action });
  };

  return (
    <div className="relative">
      <Button variant="ghost" size="icon" className="relative" aria-label="alerts" onClick={() => setIsTrayOpen((open) => !open)}>
        <Bell className="h-4 w-4" aria-hidden="true" />
        {unreadCount > 0 ? (
          <Badge
            variant="destructive"
            className="absolute -right-1 -top-1 min-w-5 justify-center px-1 py-0 text-[10px]"
          >
            {unreadCount}
          </Badge>
        ) : null}
      </Button>

      {isTrayOpen ? (
        <div className="absolute right-0 z-40 mt-2 w-80 rounded-xl border border-border/70 bg-background/95 p-3 shadow-xl backdrop-blur">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-semibold">Alert Tray</p>
            <Button asChild size="sm" variant="ghost" onClick={() => setIsTrayOpen(false)}>
              <Link href="/alerts">Open inbox</Link>
            </Button>
          </div>

          {trayAlerts.length === 0 ? (
            <p className="text-xs text-muted-foreground">No active alerts.</p>
          ) : (
            <div className="space-y-2">
              {trayAlerts.map((alert) => {
                const contextHref = getAlertContextHref(alert);
                return (
                  <div key={alert.id} className="rounded-lg border border-border/60 p-2">
                    <p className="text-xs font-medium">{alert.title}</p>
                    <div className="mt-2 flex flex-wrap gap-1">
                      <Button size="sm" variant="outline" onClick={() => void quickAction(alert.id, "seen")}>Seen</Button>
                      <Button size="sm" variant="outline" onClick={() => void quickAction(alert.id, "acknowledge")}>Ack</Button>
                      {contextHref ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            router.push(contextHref);
                            setIsTrayOpen(false);
                          }}
                        >
                          Context
                        </Button>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
