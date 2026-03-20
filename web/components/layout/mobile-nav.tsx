import { topLevelNavGroups } from "@/components/layout/nav-config";
import { Compass, Search, Radar, Shield, Wallet, Circle, Bell } from "lucide-react";
import Link from "next/link";

const mobileIcons: Record<string, React.ElementType> = {
  Discover: Compass,
  Analyze: Search,
  "Smart Money": Radar,
  Protect: Shield,
  Alerts: Bell,
  Portfolio: Wallet,
};

export function MobileNav() {
  return (
    <nav
      aria-label="Primary mobile"
      className="fixed inset-x-0 bottom-0 z-30 flex items-center justify-around border-t border-border/50 bg-background/95 px-2 py-2 backdrop-blur md:hidden"
    >
      {topLevelNavGroups.map((group) => {
        const Icon = mobileIcons[group.label] || Circle;

        return (
          <Link
            key={group.href}
            href={group.href}
            aria-label={group.label}
            className="rounded-md p-2 text-muted-foreground transition hover:text-foreground"
          >
            <Icon className="h-4 w-4" />
          </Link>
        );
      })}
    </nav>
  );
}
