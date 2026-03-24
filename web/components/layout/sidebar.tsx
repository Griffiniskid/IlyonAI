"use client";

import { useEffect, useState } from "react";
import { navGroups } from "@/components/layout/nav-config";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export function Sidebar() {
  const pathname = usePathname();
  const [locationHash, setLocationHash] = useState("");

  useEffect(() => {
    const syncHash = () => {
      setLocationHash(window.location.hash || "");
    };

    syncHash();
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, [pathname]);

  return (
    <aside className="hidden md:flex md:w-64 md:flex-col md:border-r md:border-border/50 md:bg-background/70 md:backdrop-blur" aria-label="Primary">
      <nav className="flex-1 overflow-y-auto sticky top-0 flex flex-col gap-6 p-4">
        {navGroups.map((group) => (
          <div key={group.label} className="flex flex-col gap-2">
            <h4 className="px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground/70">
              {group.label}
            </h4>
            <div className="flex flex-col gap-1">
              {group.items.map((item) => {
                const itemBaseHref = item.href.split("#")[0] || "/";
                const itemHash = item.href.includes("#") ? `#${item.href.split("#")[1]}` : "";

                const hashLinkIsActive = itemHash !== "" && pathname === itemBaseHref && locationHash === itemHash;

                const siblingHashIsActive = group.items.some((candidate) => {
                  const candidateBaseHref = candidate.href.split("#")[0] || "/";
                  const candidateHash = candidate.href.includes("#") ? `#${candidate.href.split("#")[1]}` : "";
                  return candidateHash !== "" && candidateBaseHref === itemBaseHref && locationHash === candidateHash;
                });

                const baseLinkIsActive =
                  itemHash === "" &&
                  (pathname === itemBaseHref || (itemBaseHref !== "/" && pathname?.startsWith(itemBaseHref))) &&
                  !siblingHashIsActive;

                const isActive = hashLinkIsActive || baseLinkIsActive;
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
