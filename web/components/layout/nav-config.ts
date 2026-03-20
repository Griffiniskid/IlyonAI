export type NavGroup = {
  label: string;
  href: string;
};

export const topLevelNavGroups: NavGroup[] = [
  { label: "Discover", href: "/defi" },
  { label: "Analyze", href: "/" },
  { label: "Smart Money", href: "/smart-money" },
  { label: "Protect", href: "/shield" },
  { label: "Alerts", href: "/alerts" },
  { label: "Portfolio", href: "/portfolio" },
];
