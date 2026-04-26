/**
 * MetaMask wallet connection + JWT authentication.
 * Default chain: BNB Smart Chain (56).
 *
 * Uses EIP-1193 multi-provider detection to find the real MetaMask even when
 * Phantom (or another wallet) has hijacked window.ethereum.
 */

const API_BASE = "/api/v1";
const BNB_CHAIN_HEX = "0x38"; // 56

type EthProvider = {
  request: (a: { method: string; params?: unknown[] }) => Promise<unknown>;
  isMetaMask?: boolean;
  isPhantom?: boolean;
  providers?: EthProvider[];
};

export interface MetaMaskSession {
  user: {
    id: number;
    display_name: string;
    wallet_address?: string;
    email?: string;
    token: string;
  };
  address: string;
  chainId: number;
}

async function switchToBNB(eth: EthProvider): Promise<void> {
  try {
    await eth.request({ method: "wallet_switchEthereumChain", params: [{ chainId: BNB_CHAIN_HEX }] });
  } catch (err: unknown) {
    if ((err as { code?: number }).code === 4902) {
      await eth.request({
        method: "wallet_addEthereumChain",
        params: [{
          chainId: BNB_CHAIN_HEX,
          chainName: "BNB Smart Chain",
          nativeCurrency: { name: "BNB", symbol: "BNB", decimals: 18 },
          rpcUrls: ["https://bsc-dataseed.binance.org"],
          blockExplorerUrls: ["https://bscscan.com"],
        }],
      });
    }
    // If switch fails for another reason, continue anyway
  }
}

export function resolveMetaMaskProvider(): EthProvider {
  const win = window as unknown as { ethereum?: EthProvider };
  const eth = win.ethereum;

  if (!eth) {
    throw new Error("MetaMask not installed. Please install it from metamask.io");
  }

  // EIP-1193: when multiple wallets are present, the browser collects them in providers[]
  if (eth.providers?.length) {
    const mm = eth.providers.find(p => p.isMetaMask && !p.isPhantom);
    if (mm) return mm;
    // Fall back to first MetaMask-flagged provider
    const anyMM = eth.providers.find(p => p.isMetaMask);
    if (anyMM) return anyMM;
  }

  // Single provider — if it's Phantom at all (even claiming isMetaMask), reject it.
  // Modern Phantom sets both isPhantom=true and isMetaMask=true for EVM compatibility,
  // so checking only !isMetaMask is not enough.
  if (eth.isPhantom) {
    throw new Error("MetaMask not found. Phantom is intercepting window.ethereum — please install MetaMask.");
  }

  return eth;
}

export async function connectMetaMask(): Promise<MetaMaskSession> {
  const eth = resolveMetaMaskProvider();

  // Request accounts
  const accounts = await eth.request({ method: "eth_requestAccounts" }) as string[];
  const address = accounts[0];

  // Switch to BNB Chain by default
  await switchToBNB(eth);

  const chainHex = await eth.request({ method: "eth_chainId" }) as string;
  const chainId = parseInt(chainHex, 16);

  // Sign auth message (hex-encoded for MetaMask compatibility)
  const ts = Math.floor(Date.now() / 1000);
  const message = `Sign in to Ilyon AI Beta\n\nTimestamp: ${ts}`;
  const msgHex = "0x" + Array.from(new TextEncoder().encode(message), b => b.toString(16).padStart(2, "0")).join("");
  const signature = await eth.request({ method: "personal_sign", params: [msgHex, address] }) as string;

  // JWT auth
  const res = await fetch(`${API_BASE}/auth/metamask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address, message, signature }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Authentication failed");

  // Persist session
  localStorage.setItem("ap_token", data.token);
  localStorage.setItem("ap_wallet", address);
  localStorage.setItem("ap_wallet_type", "metamask");
  localStorage.removeItem("ap_sol_wallet");
  localStorage.removeItem("ap_phantom_wallet_context");

  return {
    user: { ...data.user, token: data.token },
    address,
    chainId,
  };
}
