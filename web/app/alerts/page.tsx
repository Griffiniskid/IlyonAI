"use client";

import { useMemo, useState, type MouseEvent } from "react";
import { useRouter } from "next/navigation";

import { requestAlertPermission } from "../../lib/notifications";
import { useAlerts } from "../../lib/hooks";

export default function AlertsPage() {
  const router = useRouter();
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [permissionResult, setPermissionResult] = useState<string>("unknown");
  const { data } = useAlerts();

  const alerts = data ?? [];
  const filteredAlerts = useMemo(() => {
    if (severityFilter === "all") return alerts;
    return alerts.filter((alert) => alert.severity === severityFilter);
  }, [alerts, severityFilter]);

  const handleEnableNotifications = async () => {
    const result = await requestAlertPermission();
    setPermissionResult(result);
  };

  const handleOpenTokenContext = (event: MouseEvent<HTMLAnchorElement>, subjectId: string | null | undefined) => {
    event.preventDefault();
    if (!subjectId) return;
    router.push(`/token/${subjectId}`);
  };

  return (
    <div>
      <button onClick={handleEnableNotifications}>Enable browser notifications</button>
      <button onClick={() => setSeverityFilter("high")}>severity: high</button>
      <p>Notification permission: {permissionResult}</p>

      <div>
        {filteredAlerts.length == 0 ? (
          <p>No alerts yet</p>
        ) : (
          filteredAlerts.map((alert) => (
            <div key={alert.id}>
              <div>{alert.title}</div>
              <a
                href="#"
                onClick={(event) => handleOpenTokenContext(event, alert.subject_id)}
              >
                View token context for {alert.title}
              </a>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
