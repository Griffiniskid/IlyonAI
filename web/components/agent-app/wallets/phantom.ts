type EthProvider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  isPhantom?: boolean;
};

type SolanaProvider = {
  isPhantom?: boolean;
  connect: () => Promise<{ publicKey: { toString: () => string } }>;
  disconnect: () => void;
  signMessage?: (message: Uint8Array, display?: "utf8" | "hex") => Promise<{ signature: Uint8Array }>;
};

type PhantomWindow = {
  phantom?: { solana?: SolanaProvider; ethereum?: EthProvider };
  solana?: SolanaProvider;
};

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
  const provider = (window as unknown as PhantomWindow).phantom?.ethereum;

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
      // Fall back to legacy localStorage keys below.
    }
  }

  const solanaAddress = localStorage.getItem("ap_sol_wallet") || "";
  const evmAddress = localStorage.getItem("ap_wallet") || "";

  if (!solanaAddress && !evmAddress) return null;

  return {
    solanaAddress,
    evmAddress,
    evmChainId: evmAddress ? 56 : 101,
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

function base64FromBytes(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...Array.from(bytes)));
}

export async function connectPhantomSolana(): Promise<PhantomSession> {
  const win = window as unknown as PhantomWindow;
  const solana = win.phantom?.solana ?? win.solana;

  if (!solana) {
    throw new Error("Phantom not installed. Please install it from phantom.app");
  }

  const response = await solana.connect();
  const solanaAddress = response.publicKey.toString();
  let evmAddress = "";
  let evmChainId = 101;

  if (win.phantom?.ethereum) {
    try {
      const accounts = await win.phantom.ethereum.request({ method: "eth_requestAccounts" }) as string[];
      evmAddress = accounts[0] ?? "";
      const chainHex = await win.phantom.ethereum.request({ method: "eth_chainId" }) as string;
      evmChainId = parseInt(chainHex, 16);
    } catch (error) {
      console.warn("Could not get EVM address from Phantom:", error);
    }
  }

  let signedMessage = "";
  let signature = "";

  if (typeof solana.signMessage === "function") {
    try {
      signedMessage = `Sign in to Ilyon AI Beta\n\nTimestamp: ${Math.floor(Date.now() / 1000)}`;
      const signed = await solana.signMessage(new TextEncoder().encode(signedMessage), "utf8");
      signature = base64FromBytes(signed.signature);
    } catch (error) {
      console.warn("Phantom signMessage failed, continuing without JWT auth:", error);
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
  } catch {
    // Ignore wallet disconnect errors during local cleanup.
  }

  localStorage.removeItem(PHANTOM_CONTEXT_KEY);
}
