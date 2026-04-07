"use client";

import type { ReactNode } from "react";
import { MobileNav } from "@/components/layout/mobile-nav";
import { Sidebar } from "@/components/layout/sidebar";
import { CommandPalette } from "@/components/layout/command-palette";
import { AlertsBell } from "@/components/layout/alerts-bell";
import { useAlertSummary } from "@/lib/hooks";
import { COMING_SOON } from "@/lib/feature-flags";

export function AppShell({ children }: { children: ReactNode }) {
  const { unreadCount, alerts } = useAlertSummary();

  return (
    <div className="min-h-screen md:flex">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col pb-16 md:pb-0">
        {!COMING_SOON && (
          <div className="flex justify-end p-4">
            <AlertsBell unreadCount={unreadCount} alerts={alerts} />
          </div>
        )}
        {children}
        <CommandPalette />
      </div>
      <MobileNav />
    </div>
  );
}
