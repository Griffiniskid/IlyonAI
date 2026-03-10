import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind CSS classes with clsx
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a number as USD currency
 */
export function formatUSD(value: number): string {
  if (value >= 1_000_000_000) {
    return `$${(value / 1_000_000_000).toFixed(2)}B`;
  }
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(2)}K`;
  }
  if (value >= 1) {
    return `$${value.toFixed(2)}`;
  }
  if (value >= 0.0001) {
    return `$${value.toFixed(4)}`;
  }
  return `$${value.toFixed(8)}`;
}

/**
 * Format a number with compact notation (with $ prefix)
 */
export function formatCompact(value: number): string {
  if (value >= 1_000_000_000) {
    return `$${(value / 1_000_000_000).toFixed(2)}B`;
  }
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(2)}K`;
  }
  return `$${value.toFixed(2)}`;
}

/**
 * Format a percentage change
 */
export function formatPercentage(value: number): string {
  const prefix = value >= 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}%`;
}

/**
 * Format token age in human-readable form
 */
export function formatAge(hours: number): string {
  if (hours < 1) {
    const minutes = Math.round(hours * 60);
    return `${minutes}m`;
  }
  if (hours < 24) {
    return `${hours.toFixed(1)}h`;
  }
  const days = hours / 24;
  if (days < 30) {
    return `${days.toFixed(1)}d`;
  }
  const months = days / 30;
  return `${months.toFixed(1)}mo`;
}

/**
 * Truncate an address for display
 */
export function truncateAddress(address: string, chars: number = 4): string {
  if (!address) return "";
  return `${address.slice(0, chars)}...${address.slice(-chars)}`;
}

/**
 * Get color class based on score
 */
export function getScoreColor(score: number): string {
  if (score >= 80) return "text-emerald-400";
  if (score >= 60) return "text-yellow-400";
  if (score >= 40) return "text-orange-400";
  if (score >= 20) return "text-red-400";
  return "text-red-600";
}

/**
 * Get background color class based on score
 */
export function getScoreBgColor(score: number): string {
  if (score >= 80) return "bg-emerald-500";
  if (score >= 60) return "bg-yellow-500";
  if (score >= 40) return "bg-orange-500";
  if (score >= 20) return "bg-red-500";
  return "bg-red-600";
}

/**
 * Get verdict color class
 */
export function getVerdictColor(verdict: string): string {
  switch (verdict?.toUpperCase()) {
    case "SAFE":
      return "text-emerald-400";
    case "CAUTION":
      return "text-yellow-400";
    case "RISKY":
      return "text-orange-400";
    case "DANGEROUS":
      return "text-red-400";
    case "SCAM":
      return "text-red-600";
    default:
      return "text-muted-foreground";
  }
}

/**
 * Get badge classes based on verdict
 */
export function getVerdictBadgeClasses(verdict: string): string {
  switch (verdict?.toUpperCase()) {
    case "SAFE":
      return "badge-safe";
    case "CAUTION":
      return "badge-caution";
    case "RISKY":
      return "badge-risky";
    case "DANGEROUS":
    case "SCAM":
      return "badge-danger";
    default:
      return "bg-muted text-muted-foreground";
  }
}

/**
 * Validate EVM address format
 */
export function isValidEvmAddress(address: string): boolean {
  if (!address) return false;
  return /^0x[a-fA-F0-9]{40}$/.test(address);
}

/**
 * Validate Solana address format
 */
export function isValidSolanaAddress(address: string): boolean {
  if (!address) return false;
  // Base58 pattern for Solana addresses (32-44 chars)
  const base58Regex = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;
  return base58Regex.test(address);
}

/**
 * Get the explorer URL for an EVM address
 */
export function getEvmExplorerAddressUrl(chain: string, address: string): string | null {
  const explorers: Record<string, string> = {
    ethereum: "https://etherscan.io/address",
    base: "https://basescan.org/address",
    arbitrum: "https://arbiscan.io/address",
    bsc: "https://bscscan.com/address",
    polygon: "https://polygonscan.com/address",
    optimism: "https://optimistic.etherscan.io/address",
    avalanche: "https://snowtrace.io/address",
  };

  const baseUrl = explorers[chain.toLowerCase()];
  return baseUrl ? `${baseUrl}/${address}` : null;
}

/**
 * Copy text to clipboard
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/**
 * Format a date relative to now
 */
export function formatRelativeTime(date: string | Date): string {
  const now = new Date();
  const then = new Date(date);
  const seconds = Math.floor((now.getTime() - then.getTime()) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return then.toLocaleDateString();
}
