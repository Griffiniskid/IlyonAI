/**
 * Phantom wallet connection - Solana primary, EVM secondary.
 * Stores wallet context in structured form so the app can use Phantom's
 * Solana signer and Phantom's EVM signer independently.
 */

type EthProvider = { request: (a: { method: string; params?: unknown[] }) => Promise<unknown>; isPhantom?: boolean };
type SolanaProvider = {
  connect: (options?: { onlyIfTrusted?: boolean }) => Promise<{ publicKey: { toString: () => string } }>;
  disconnect: () => void;
  signMessage?: (message: Uint8Array, display?: "utf8" | "hex") => Promise<{ signature: Uint8Array }>;
  isPhantom?: boolean;
};
type PhantomWindow = { phantom?: { solana?: SolanaProvider; ethereum?: EthProvider }; ethereum?: EthProvider };

export interface PhantomSession {
  solanaAddress: string;
  evmAddress: string;
  evmChainId: number;
  displayName: string;
  signedMessage?: string;
  signature?: string;
}

export interface StoredPhantomWalletContext {
  solanaAddress: string;
  evmAddress: string;
  evmChainId: number;
}

const PHANTOM_CONTEXT_KEY = "ap_phantom_wallet_context";

export function resolvePhantomEvmProvider(): EthProvider {
  const w = window as unknown as PhantomWindow;
  const provider = w.phantom?.ethereum;
  if (!provider) {
    throw new Error("Phantom EVM wallet not available. Enable Ethereum in Phantom first.");
  }
  return provider;
}

export function getStoredPhantomWalletContext(): StoredPhantomWalletContext | null {
  const raw = localStorage.getItem(PHANTOM_CONTEXT_KEY);
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as Partial<StoredPhantomWalletContext>;
      if (parsed.solanaAddress) {
        return {
          solanaAddress: parsed.solanaAddress,
          evmAddress: parsed.evmAddress ?? "",
          evmChainId: Number(parsed.evmChainId ?? 101),
        };
      }
    } catch {
      // Fall through to legacy storage.
    }
  }

  const solanaRaw = localStorage.getItem("ap_sol_wallet") || "";
  const evmRaw = localStorage.getItem("ap_wallet") || "";
  if (!solanaRaw && !evmRaw) return null;

  if (solanaRaw.includes(",")) {
    const [solanaAddress, evmAddress = ""] = solanaRaw.split(",").map(part => part.trim());
    return {
      solanaAddress,
      evmAddress: evmRaw || evmAddress,
      evmChainId: 56,
    };
  }

  return {
    solanaAddress: solanaRaw,
    evmAddress: evmRaw,
    evmChainId: 56,
  };
}

function persistPhantomWalletContext(context: StoredPhantomWalletContext): void {
  localStorage.setItem(PHANTOM_CONTEXT_KEY, JSON.stringify(context));
  localStorage.setItem("ap_sol_wallet", context.solanaAddress);
  if (context.evmAddress) {
    localStorage.setItem("ap_wallet", context.evmAddress);
  } else {
    localStorage.removeItem("ap_wallet");
  }
}

export async function restorePhantomWalletContext(): Promise<StoredPhantomWalletContext | null> {
  const w = window as unknown as PhantomWindow;
  const solana = w.phantom?.solana;
  if (!solana) return null;

  let solanaAddress = "";
  try {
    const resp = await solana.connect({ onlyIfTrusted: true });
    solanaAddress = resp.publicKey.toString();
  } catch {
    return null;
  }

  let evmAddress = "";
  let evmChainId = 101;
  if (w.phantom?.ethereum) {
    try {
      const accounts = await w.phantom.ethereum.request({ method: "eth_accounts" }) as string[];
      evmAddress = accounts[0] ?? "";
      if (evmAddress) {
        const chainHex = await w.phantom.ethereum.request({ method: "eth_chainId" }) as string;
        evmChainId = parseInt(chainHex, 16);
      }
    } catch (e) {
      console.warn("Could not restore Phantom EVM address:", e);
    }
  }

  const context = { solanaAddress, evmAddress, evmChainId };
  persistPhantomWalletContext(context);
  localStorage.setItem("ap_wallet_type", "phantom");
  return context;
}

export async function connectPhantomSolana(): Promise<PhantomSession> {
  const w = window as unknown as PhantomWindow;

  if (!w.phantom) {
    throw new Error("Phantom not installed. Please install it from phantom.app");
  }
  if (!w.phantom.solana) {
    throw new Error("Phantom Solana wallet not available. Please open Phantom and enable the Solana wallet.");
  }

  const resp = await w.phantom.solana.connect();
  const solanaAddress = resp.publicKey.toString();

  let evmAddress = "";
  let evmChainId = 101;
  if (w.phantom.ethereum) {
    try {
      const accounts = await w.phantom.ethereum.request({ method: "eth_requestAccounts" }) as string[];
      evmAddress = accounts[0] ?? "";
      const chainHex = await w.phantom.ethereum.request({ method: "eth_chainId" }) as string;
      evmChainId = parseInt(chainHex, 16);
    } catch (e) {
      console.warn("Could not get EVM address from Phantom:", e);
    }
  }

  let signedMessage = "";
  let signature = "";
  if (typeof w.phantom.solana.signMessage === "function") {
    try {
      signedMessage = `Sign in to Ilyon AI Beta\n\nTimestamp: ${Math.floor(Date.now() / 1000)}`;
      const encoded = new TextEncoder().encode(signedMessage);
      const signed = await w.phantom.solana.signMessage(encoded, "utf8");
      signature = btoa(String.fromCharCode(...Array.from(signed.signature)));
    } catch (e) {
      console.warn("Phantom signMessage failed, continuing without JWT auth:", e);
      signedMessage = "";
      signature = "";
    }
  }

  persistPhantomWalletContext({ solanaAddress, evmAddress, evmChainId });
  localStorage.setItem("ap_wallet_type", "phantom");
  localStorage.removeItem("ap_token");

  return {
    solanaAddress,
    evmAddress,
    evmChainId,
    displayName: `${solanaAddress.slice(0, 6)}...${solanaAddress.slice(-4)}`,
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
  localStorage.removeItem(PHANTOM_CONTEXT_KEY);
}
