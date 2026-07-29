import {
  Home,
  MessagesSquare,
  ShieldCheck,
  Settings,
  LucideIcon,
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

// Solana chat product — four surfaces only: a main page, the AI chat, the
// Token Safety checker, and settings. Swap and the old multi-chain sprawl were
// cut. Single source of truth for both the desktop sidebar and mobile nav.
export const navGroups: NavGroup[] = [
  {
    label: "Ilyon",
    items: [
      { label: "Home", href: "/", icon: Home },
      { label: "AI Chat", href: "/agent/chat?tab=chat", icon: MessagesSquare },
      { label: "Token Safety", href: "/token-safety", icon: ShieldCheck },
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];
