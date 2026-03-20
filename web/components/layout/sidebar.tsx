import { topLevelNavGroups } from "@/components/layout/nav-config";
import Link from "next/link";

export function Sidebar() {
  return (
    <aside className="hidden md:block md:w-64 md:border-r md:border-border/50 md:bg-background/70 md:backdrop-blur" aria-label="Primary">
      <nav className="sticky top-0 flex h-screen flex-col gap-2 p-4">
        {topLevelNavGroups.map((group) => (
          <Link
            key={group.href}
            href={group.href}
            className="rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition hover:bg-secondary hover:text-foreground"
          >
            {group.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
