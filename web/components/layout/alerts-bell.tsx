import React from "react";

export function AlertsBell({ unreadCount }: { unreadCount: number }) {
  return <button aria-label="alerts">{unreadCount}</button>;
}
