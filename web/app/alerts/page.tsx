"use client";

import { useMemo, useState, type MouseEvent } from "react";
import { useRouter } from "next/navigation";
import { ExternalLink, Loader2 } from "lucide-react";

import { requestAlertPermission } from "../../lib/notifications";
import { getAlertContextHref } from "../../lib/alerts";
import { useAlertRules, useAlerts, useUpdateAlert } from "../../lib/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/card";
import type { AlertSeverity } from "@/types";

const severityFilters: Array<{ key: "all" | AlertSeverity; label: string }> = [
  { key: "all", label: "All" },
  { key: "critical", label: "Critical" },
  { key: "high", label: "High" },
  { key: "medium", label: "Medium" },
  { key: "low", label: "Low" },
];

const severityVariant: Record<AlertSeverity, "secondary" | "danger" | "risky" | "caution"> = {
  critical: "danger",
  high: "risky",
  medium: "caution",
  low: "secondary",
};

export default function AlertsPage() {
  const router = useRouter();
  const [severityFilter, setSeverityFilter] = useState<"all" | AlertSeverity>("all");
  const [permissionResult, setPermissionResult] = useState<string>("unknown");
  const { data, isLoading, error } = useAlerts();
  const { data: rules = [] } = useAlertRules();
  const updateAlert = useUpdateAlert();

  const alerts = data ?? [];
  const filteredAlerts = useMemo(() => {
    if (severityFilter === "all") return alerts;
    return alerts.filter((alert) => alert.severity === severityFilter);
  }, [alerts, severityFilter]);

  const severityCounts = useMemo(() => {
    const counts: Record<string, number> = { all: alerts.length };
    for (const alert of alerts) {
      counts[alert.severity] = (counts[alert.severity] ?? 0) + 1;
    }
    return counts;
  }, [alerts]);

  const handleEnableNotifications = async () => {
    const result = await requestAlertPermission();
    setPermissionResult(result);
  };

  const handleOpenContext = (event: MouseEvent<HTMLAnchorElement>, href: string | null) => {
    event.preventDefault();
    if (!href) return;
    router.push(href);
  };

  const handleAlertAction = async (
    alertId: string,
    action: "seen" | "acknowledge" | "snooze" | "unsnooze" | "resolve",
  ) => {
    const snoozed_until = action === "snooze" ? new Date(Date.now() + 60 * 60 * 1000).toISOString() : undefined;
    await updateAlert.mutateAsync({ alertId, action, snoozed_until });
  };

  return (
    <section className="container mx-auto max-w-4xl px-4 py-8">
      <GlassCard className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-2">
            <h1 className="text-3xl font-bold">Alerts Inbox</h1>
            <div className="flex items-center gap-2">
              <Badge variant="outline">{alerts.filter((alert) => alert.state === "new").length} unread</Badge>
              <p className="text-sm text-muted-foreground">Permission status: {permissionResult}</p>
            </div>
          </div>
          <Button onClick={handleEnableNotifications}>Enable notifications</Button>
        </div>

        <div className="flex flex-wrap gap-2">
          {severityFilters.map((filterOption) => {
            const count = severityCounts[filterOption.key] ?? 0;
            return (
              <Button
                key={filterOption.key}
                variant={severityFilter === filterOption.key ? "secondary" : "outline"}
                size="sm"
                onClick={() => setSeverityFilter(filterOption.key)}
              >
                {filterOption.label}{count > 0 ? ` (${count})` : ""}
              </Button>
            );
          })}
        </div>

        <div className="rounded-xl border border-border/60 bg-background/40 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Watchlist and Channel Rules</p>
          {rules.length === 0 ? (
            <p className="mt-2 text-sm text-muted-foreground">No rules configured yet.</p>
          ) : (
            <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
              {rules.map((rule) => (
                <li key={rule.id}>
                  {rule.name}: {rule.severity.join(", ")}
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
            <Badge variant="outline">Dedupe: 5m window</Badge>
            <Badge variant="outline">Suppression: active for snoozed alerts</Badge>
            <Badge variant="outline">Channel: in-app + browser opt-in</Badge>
          </div>
        </div>

        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading alerts...
          </div>
        ) : error ? (
          <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive-foreground">
            Could not load alerts. Try again shortly.
          </div>
        ) : filteredAlerts.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border/60 p-8 text-center text-muted-foreground space-y-2">
            <p className="font-medium">No alerts yet</p>
            <p className="text-sm">
              Alerts are generated automatically when whale activity or rekt incidents match your watchlist.
              Configure rules above to start receiving alerts.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredAlerts.map((alert) => {
              const contextHref = getAlertContextHref(alert);
              return (
                <div
                  key={alert.id}
                  className="flex flex-col gap-3 rounded-xl border border-border/60 bg-background/40 p-4 md:flex-row md:items-center md:justify-between"
                >
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={severityVariant[alert.severity]}>{alert.severity}</Badge>
                      <Badge variant="outline">{alert.state}</Badge>
                      {alert.kind ? <Badge variant="secondary">{alert.kind}</Badge> : null}
                      {alert.subject_id ? <Badge variant="outline">subject: {alert.subject_id}</Badge> : null}
                      {alert.snoozed_until ? <Badge variant="outline">snoozed</Badge> : null}
                      {alert.resolved_at ? <Badge variant="outline">resolved</Badge> : null}
                    </div>
                    <p className="font-medium">{alert.title}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {contextHref ? (
                      <a
                        href="#"
                        className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                        aria-label={`Open context for ${alert.title}`}
                        onClick={(event) => handleOpenContext(event, contextHref)}
                      >
                        Open context
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                      </a>
                    ) : null}
                    <Button size="sm" variant="outline" onClick={() => void handleAlertAction(alert.id, "seen")}>
                      Mark seen
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => void handleAlertAction(alert.id, "acknowledge")}>
                      Acknowledge
                    </Button>
                    {alert.snoozed_until ? (
                      <Button size="sm" variant="outline" onClick={() => void handleAlertAction(alert.id, "unsnooze")}>
                        Unsnooze
                      </Button>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => void handleAlertAction(alert.id, "snooze")}>
                        Snooze 1h
                      </Button>
                    )}
                    <Button size="sm" variant="outline" onClick={() => void handleAlertAction(alert.id, "resolve")}>
                      Resolve
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </GlassCard>
    </section>
  );
}
