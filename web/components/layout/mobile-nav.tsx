"use client";

import { useState } from "react";
import { navGroups } from "@/components/layout/nav-config";
import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export function MobileNav() {
  const [isOpen, setIsOpen] = useState(false);
  const pathname = usePathname();

  return (
    <>
      <nav
        aria-label="Primary mobile"
        className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-between border-t border-border/50 bg-background/95 px-6 py-3 backdrop-blur md:hidden"
      >
        {/* Render bottom bar with main items - 1 from each group ideally, or just a menu button */}
        {navGroups.slice(0, 4).map((group) => {
          const firstItem = group.items[0];
          const Icon = firstItem.icon;
          const isActive = pathname === firstItem.href;
          return (
            <Link
              key={firstItem.href}
              href={firstItem.href}
              aria-label={group.label}
              className={cn(
                "flex flex-col items-center gap-1 rounded-md p-1 transition-colors",
                isActive ? "text-primary" : "text-muted-foreground hover:text-foreground"
              )}
              onClick={() => setIsOpen(false)}
            >
              <Icon className="h-5 w-5" />
              <span className="text-[10px] font-medium">{group.label}</span>
            </Link>
          );
        })}
        <button
          onClick={() => setIsOpen(!isOpen)}
          className={cn(
            "flex flex-col items-center gap-1 rounded-md p-1 transition-colors",
            isOpen ? "text-primary" : "text-muted-foreground hover:text-foreground"
          )}
          aria-label="Menu"
        >
          {isOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          <span className="text-[10px] font-medium">Menu</span>
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
                    const isActive = pathname === item.href;
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
