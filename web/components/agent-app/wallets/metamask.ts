const API_BASE = "/api/v1";
const BNB_CHAIN_HEX = "0x38";

export type EthProvider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
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

export function resolveMetaMaskProvider(): EthProvider {
  const ethereum = (window as unknown as { ethereum?: EthProvider }).ethereum;

  if (!ethereum) {
    throw new Error("MetaMask not installed. Please install it from metamask.io");
  }

  if (ethereum.providers?.length) {
    const provider = ethereum.providers.find(candidate => candidate.isMetaMask && !candidate.isPhantom)
      ?? ethereum.providers.find(candidate => candidate.isMetaMask);
    if (provider) return provider;
  }

  if (ethereum.isPhantom) {
    throw new Error("MetaMask not found. Phantom is intercepting window.ethereum - please select MetaMask.");
  }

  return ethereum;
}

async function switchToDefaultChain(provider: EthProvider): Promise<void> {
  try {
    await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId: BNB_CHAIN_HEX }] });
  } catch (error: unknown) {
    if ((error as { code?: number }).code !== 4902) return;

    await provider.request({
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
}

function toHexMessage(message: string): string {
  return "0x" + Array.from(new TextEncoder().encode(message), byte => byte.toString(16).padStart(2, "0")).join("");
}

export async function connectMetaMask(): Promise<MetaMaskSession> {
  const provider = resolveMetaMaskProvider();
  const accounts = await provider.request({ method: "eth_requestAccounts" }) as string[];
  const address = accounts[0];

  if (!address) {
    throw new Error("No MetaMask account selected.");
  }

  await switchToDefaultChain(provider);

  const chainHex = await provider.request({ method: "eth_chainId" }) as string;
  const chainId = parseInt(chainHex, 16);
  const message = `Sign in to Ilyon AI Beta\n\nTimestamp: ${Math.floor(Date.now() / 1000)}`;
  const signature = await provider.request({
    method: "personal_sign",
    params: [toHexMessage(message), address],
  }) as string;

  const response = await fetch(`${API_BASE}/auth/metamask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address, message, signature }),
  });
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail || "MetaMask authentication failed");
  }

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
