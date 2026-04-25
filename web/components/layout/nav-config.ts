import {
  Compass,
  LineChart,

  Radar,
  Flame,
  Shield,
  Settings,
  PieChart,
  Droplets,
  Briefcase,
  MessagesSquare,
  ArrowLeftRight,
  Sparkles,
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
    ],
  },
  {
    label: "AI Agent",
    items: [
      { label: "Dashboard", href: "/agent/dashboard", icon: Sparkles },
      { label: "Chat", href: "/agent/chat", icon: MessagesSquare },
      { label: "Swap", href: "/agent/swap", icon: ArrowLeftRight },
      { label: "Portfolio", href: "/agent/portfolio", icon: PieChart },
    ],
  },
  {
    label: "Settings",
    items: [
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];
