import {
  Compass,
  LineChart,
  Scan,
  Radar,
  Flame,
  Shield,
  Settings,
  PieChart,
  Droplets,
  Briefcase,
  MessagesSquare,
  ArrowLeftRight,
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
      { label: "Analyze", href: "/analyze", icon: Scan },
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
      { label: "Chat", href: "/agent/chat?tab=chat", icon: MessagesSquare },
      { label: "Swap", href: "/agent/swap?tab=swap", icon: ArrowLeftRight },
      { label: "Portfolio", href: "/agent/portfolio?tab=portfolio", icon: PieChart },
    ],
  },
  {
    label: "AI Agent",
    items: [
      { label: "Chat", href: "/agent/chat", icon: MessagesSquare },
      { label: "Swap", href: "/agent/swap", icon: ArrowLeftRight },
    ],
  },
  {
    label: "Settings",
    items: [
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];
