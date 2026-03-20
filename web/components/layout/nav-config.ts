import {
  Compass,
  LineChart,
  Activity,
  Radar,
  Flame,
  Wallet,
  Shield,
  Bell,
  Settings,
  PieChart,
  Search,
  Droplets,
  Zap,
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
      { label: "Trending", href: "/trending", icon: Flame },
      { label: "DeFi", href: "/defi", icon: Activity },
    ],
  },
  {
    label: "Analyze",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LineChart },
      { label: "Token Search", href: "/token/search", icon: Search },
    ],
  },
  {
    label: "Smart Money",
    items: [
      { label: "Hub", href: "/smart-money", icon: Radar },
      { label: "Whales", href: "/whales", icon: Droplets },
      { label: "Flows", href: "/flows", icon: Zap },
    ],
  },
  {
    label: "Protect",
    items: [
      { label: "Shield", href: "/shield", icon: Shield },
      { label: "Alerts", href: "/alerts", icon: Bell },
    ],
  },
  {
    label: "Portfolio",
    items: [
      { label: "Overview", href: "/portfolio", icon: PieChart },
      { label: "Wallet", href: "/wallet", icon: Wallet },
    ],
  },
  {
    label: "Settings",
    items: [
      { label: "Preferences", href: "/settings", icon: Settings },
    ],
  },
];
