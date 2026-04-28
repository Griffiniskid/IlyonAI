"use client";

import type { ReactNode } from "react";
import { MobileNav } from "@/components/layout/mobile-nav";
import { Sidebar } from "@/components/layout/sidebar";
import { CommandPalette } from "@/components/layout/command-palette";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="h-full md:flex overflow-hidden">
      <Sidebar />
      <div className="flex h-full flex-1 flex-col pb-16 md:pb-0 overflow-hidden">
        {children}
        <CommandPalette />
      </div>
      <MobileNav />
    </div>
  );
}
