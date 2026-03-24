import type { AlertRecordResponse } from "@/types";

export function getAlertContextHref(alert: Pick<AlertRecordResponse, "subject_id" | "kind">): string | null {
  if (!alert.subject_id) return null;

  const kind = (alert.kind ?? "").toLowerCase();
  if (kind.includes("wallet")) return `https://solscan.io/account/${alert.subject_id}`;
  if (kind.includes("pool")) return `/pool/${alert.subject_id}`;
  if (kind.includes("entity")) return `/entity/${alert.subject_id}`;
  if (kind.includes("rekt")) return `/rekt/${alert.subject_id}`;
  return `/token/${alert.subject_id}`;
}
