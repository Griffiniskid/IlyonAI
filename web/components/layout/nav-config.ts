import {
  Compass,
  LineChart,

  Radar,
  Flame,
  Shield,
  Bell,
  Settings,
  PieChart,
  Droplets,
  Briefcase,
  LucideIcon
} from "lucide-react";

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
};

export type NavGroup = {
  label: string;
  items: NavItem[];
};

export const navGroups: NavGroup[] = [
  {
    label: "Discover",
    items: [
      { label: "Overview", href: "/", icon: Compass },
      { label: "Dashboard", href: "/dashboard", icon: LineChart },
      { label: "Trending", href: "/trending", icon: Flame },
    ],
  },
  {
    label: "Smart Money",
    items: [
      { label: "Hub", href: "/smart-money", icon: Radar },
      { label: "Whales", href: "/whales", icon: Droplets },
      { label: "Entity", href: "/entity", icon: Briefcase },
    ],
  },
  {
    label: "Protect",
    items: [
      { label: "Shield", href: "/shield", icon: Shield },
      { label: "Audits", href: "/audits", icon: Briefcase },
      { label: "Rekt", href: "/rekt", icon: Flame },
      { label: "Alerts", href: "/alerts", icon: Bell },
    ],
  },
  {
    label: "Portfolio",
    items: [
      { label: "Portfolio", href: "/portfolio", icon: PieChart },
    ],
  },
  {
    label: "Settings",
    items: [
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];
