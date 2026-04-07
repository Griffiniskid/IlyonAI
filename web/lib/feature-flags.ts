/**
 * Feature flags for controlling "coming soon" placeholders.
 *
 * Set NEXT_PUBLIC_COMING_SOON=false in .env.local to disable all plugs.
 */
export const COMING_SOON = process.env.NEXT_PUBLIC_COMING_SOON !== "false";
