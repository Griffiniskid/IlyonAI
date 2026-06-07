"use client";

import { useEffect, useState } from "react";
import { navGroups } from "@/components/layout/nav-config";
import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export function MobileNav() {
  const [isOpen, setIsOpen] = useState(false);
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

  const isItemActive = (itemHref: string, groupItems: { href: string }[]): boolean => {
    const itemBaseHref = itemHref.split(/[?#]/)[0] || "/";
    const itemHash = itemHref.includes("#") ? `#${itemHref.split("#")[1]}` : "";

    const hashLinkIsActive = itemHash !== "" && pathname === itemBaseHref && locationHash === itemHash;

    const siblingHashIsActive = groupItems.some((candidate) => {
      const candidateBaseHref = candidate.href.split(/[?#]/)[0] || "/";
      const candidateHash = candidate.href.includes("#") ? `#${candidate.href.split("#")[1]}` : "";
      return candidateHash !== "" && candidateBaseHref === itemBaseHref && locationHash === candidateHash;
    });

    const baseLinkIsActive =
      itemHash === "" &&
      (pathname === itemBaseHref || (itemBaseHref !== "/" && pathname?.startsWith(itemBaseHref))) &&
      !siblingHashIsActive;

    return hashLinkIsActive || baseLinkIsActive;
  };

  // Phone tab bar — explicit items (order matters). Overview + Analyze both live in
  // the Discover group and Portfolio in the AI Agent group, so this can't be derived
  // one-per-group. hrefs/icons still come from nav-config so they stay in sync.
  const allItems = navGroups.flatMap((group) => group.items);
  const findItem = (label: string) => allItems.find((item) => item.label === label);
  const coreSpec = [
    { label: "Overview",  from: "Overview" },
    { label: "AI Agent",  from: "Chat" },
    { label: "Portfolio", from: "Portfolio" },
    { label: "Analyze",   from: "Analyze" },
  ];
  const coreLinks = coreSpec
    .map(({ label, from }) => {
      const item = findItem(from);
      return item ? { label, href: item.href, icon: item.icon } : null;
    })
    .filter((link): link is NonNullable<typeof link> => link !== null)
    .map((link) => ({ ...link, isActive: isItemActive(link.href, [{ href: link.href }]) }));

  return (
    <>
      <nav
        aria-label="Primary mobile"
        className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-between gap-1 border-t border-border/50 bg-background/95 px-2 py-3 backdrop-blur md:hidden"
      >
        {coreLinks.map(({ label, href, icon: Icon, isActive }) => {
          return (
            <Link
              key={href}
              href={href}
              aria-label={label}
              className={cn(
                "flex min-w-0 flex-1 flex-col items-center gap-1 rounded-md p-1 transition-colors",
                isActive ? "text-primary" : "text-muted-foreground hover:text-foreground"
              )}
              onClick={() => setIsOpen(false)}
            >
              <Icon className="h-5 w-5" />
              <span className="truncate text-[9px] font-medium leading-none">{label}</span>
            </Link>
          );
        })}
        <button
          onClick={() => setIsOpen(!isOpen)}
          className={cn(
            "flex min-w-0 flex-1 flex-col items-center gap-1 rounded-md p-1 transition-colors",
            isOpen ? "text-primary" : "text-muted-foreground hover:text-foreground"
          )}
          aria-label="Menu"
        >
          {isOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          <span className="truncate text-[9px] font-medium leading-none">Menu</span>
        </button>
      </nav>

      {/* Mobile Sheet Overlay */}
      {isOpen && (
        <div className="fixed inset-0 z-30 bg-background/95 pb-20 pt-4 px-4 backdrop-blur overflow-y-auto md:hidden animate-in fade-in slide-in-from-bottom-4 duration-200">
          <div className="flex flex-col gap-6 pt-12">
            {navGroups.map((group) => (
              <div key={group.label} className="flex flex-col gap-2">
                <h4 className="px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground/70">
                  {group.label}
                </h4>
                <div className="flex flex-col gap-1">
                  {group.items.map((item) => {
                    const isActive = isItemActive(item.href, group.items);
                    const Icon = item.icon;
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        onClick={() => setIsOpen(false)}
                        className={cn(
                          "flex items-center gap-3 rounded-md px-3 py-3 text-sm font-medium transition-colors",
                          isActive
                            ? "bg-primary/10 text-primary"
                            : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                        )}
                      >
                        <Icon className="h-5 w-5" />
                        {item.label}
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
