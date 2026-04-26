/**
 * Phantom wallet connection — Solana primary, EVM secondary.
 * Fetches both addresses and combines them as "solAddr,evmAddr".
 * The combined string is stored in localStorage and passed to the backend.
 */

type EthProvider = { request: (a: { method: string; params?: unknown[] }) => Promise<unknown>; isPhantom?: boolean };
type SolanaProvider = {
  connect: () => Promise<{ publicKey: { toString: () => string } }>;
  disconnect: () => void;
  signMessage?: (message: Uint8Array, display?: "utf8" | "hex") => Promise<{ signature: Uint8Array }>;
};
type PhantomWindow = { phantom?: { solana?: SolanaProvider; ethereum?: EthProvider }; ethereum?: EthProvider };

export interface PhantomSession {
  solanaAddress: string;
  evmAddress: string;      // empty string if unavailable
  combinedAddress: string; // "solAddr,evmAddr" or just "solAddr"
  displayName: string;     // based on Solana address only
  signedMessage?: string;
  signature?: string;
}

export async function connectPhantomSolana(): Promise<PhantomSession> {
  const w = window as unknown as PhantomWindow;

  if (!w.phantom) {
    throw new Error("Phantom not installed. Please install it from phantom.app");
  }
  if (!w.phantom.solana) {
    throw new Error("Phantom Solana wallet not available. Please open Phantom and enable the Solana wallet.");
  }

  // 1. Solana address
  const resp = await w.phantom.solana.connect();
  const solanaAddress = resp.publicKey.toString();

  // 2. EVM address — strictly from window.phantom.ethereum, never window.ethereum
  //    (avoids hijacking MetaMask's provider when both wallets are installed)
  let evmAddress = "";
  if (w.phantom.ethereum) {
    try {
      const accounts = await w.phantom.ethereum.request({ method: "eth_requestAccounts" }) as string[];
      evmAddress = accounts[0] ?? "";
    } catch (e) {
      console.warn("Could not get EVM address from Phantom:", e);
    }
  }

  // 3. Combined address — sent to backend for dual-chain scanning
  const combinedAddress = evmAddress ? `${solanaAddress},${evmAddress}` : solanaAddress;

  // 4. Optional Phantom sign-in payload (for backend auth)
  let signedMessage = "";
  let signature = "";
  if (typeof w.phantom.solana.signMessage === "function") {
    try {
      signedMessage = `Sign in to Agent Platform\n\nTimestamp: ${Math.floor(Date.now() / 1000)}`;
      const encoded = new TextEncoder().encode(signedMessage);
      const signed = await w.phantom.solana.signMessage(encoded, "utf8");
      signature = btoa(String.fromCharCode(...signed.signature));
    } catch (e) {
      console.warn("Phantom signMessage failed, continuing without JWT auth:", e);
      signedMessage = "";
      signature = "";
    }
  }

  // Persist
  localStorage.setItem("ap_sol_wallet", combinedAddress);
  localStorage.setItem("ap_wallet_type", "phantom");
  localStorage.removeItem("ap_wallet");
  localStorage.removeItem("ap_token");

  return {
    solanaAddress,
    evmAddress,
    combinedAddress,
    displayName: `${solanaAddress.slice(0, 6)}…${solanaAddress.slice(-4)}`,
    signedMessage,
    signature,
  };
}

export function disconnectPhantomSolana(): void {
  try {
    (window as unknown as PhantomWindow).phantom?.solana?.disconnect();
  } catch (_) {
    // ignore
  }
}
