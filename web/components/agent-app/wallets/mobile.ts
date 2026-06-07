/**
 * Mobile wallet-connect helpers.
 *
 * On a normal mobile browser (Safari/Chrome) no wallet provider is injected —
 * Phantom/MetaMask only inject `window.phantom` / `window.ethereum` inside their
 * OWN in-app browser. So "Connect" on mobile must deep-link the dApp INTO the
 * wallet's browser, where the provider exists and the normal connect flow runs.
 */

export function isMobileBrowser(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  if (/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(ua)) return true;
  // iPadOS 13+ reports as "Macintosh" but is touch-capable.
  if (/Macintosh/.test(ua) && typeof document !== "undefined" && "ontouchend" in document) return true;
  return false;
}

/** True inside a wallet's in-app browser (any EVM/Solana provider is injected). */
export function hasInjectedWalletProvider(): boolean {
  if (typeof window === "undefined") return false;
  const w = window as unknown as { phantom?: { solana?: unknown }; solana?: unknown; ethereum?: unknown };
  return !!(w.phantom?.solana || w.solana || w.ethereum);
}

/**
 * Open the current dApp page inside Phantom's in-app browser via the universal
 * link. If Phantom isn't installed, the link routes to the app store.
 */
export function openInPhantomBrowser(): void {
  const url = window.location.href;
  const ref = window.location.origin;
  window.location.href = `https://phantom.app/ul/browse/${encodeURIComponent(url)}?ref=${encodeURIComponent(ref)}`;
}

/**
 * Open the current dApp page inside MetaMask's in-app browser. MetaMask's
 * deep-link expects host+path WITHOUT the protocol.
 */
export function openInMetaMaskBrowser(): void {
  const target = `${window.location.host}${window.location.pathname}${window.location.search}`;
  window.location.href = `https://metamask.app.link/dapp/${target}`;
}
