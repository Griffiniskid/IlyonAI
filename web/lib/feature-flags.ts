/**
 * Feature flags for controlling "coming soon" placeholders.
 *
 * Set NEXT_PUBLIC_COMING_SOON=false in .env.local to disable all plugs.
 */
export const COMING_SOON = process.env.NEXT_PUBLIC_COMING_SOON !== "false";

/** Frontend feature flags — read from NEXT_PUBLIC_ env vars or hardcoded. */

export const FEATURE_FLAGS = {
  agentChat: process.env.NEXT_PUBLIC_FEATURE_AGENT_V2 === "true",
  tokensBar: process.env.NEXT_PUBLIC_FEATURE_TOKENS_BAR === "true",
  chromeExt: process.env.NEXT_PUBLIC_FEATURE_CHROME_EXT === "true",
} as const;

export function isFeatureEnabled(flag: keyof typeof FEATURE_FLAGS): boolean {
  return FEATURE_FLAGS[flag] ?? false;
}
