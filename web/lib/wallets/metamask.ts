interface EthereumProvider {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  on: (event: string, callback: (...args: unknown[]) => void) => void;
  removeListener: (event: string, callback: (...args: unknown[]) => void) => void;
  isMetaMask?: boolean;
  selectedAddress?: string;
}

declare global {
  interface Window {
    ethereum?: EthereumProvider;
  }
}

export async function connect(): Promise<string> {
  if (!window.ethereum?.isMetaMask) throw new Error("MetaMask not detected");
  const accounts = await window.ethereum.request({ method: "eth_requestAccounts" }) as string[];
  return accounts[0];
}

export async function signMessage(message: string): Promise<string> {
  if (!window.ethereum) throw new Error("No provider");
  const accounts = await window.ethereum.request({ method: "eth_requestAccounts" }) as string[];
  const sig = await window.ethereum.request({ method: "personal_sign", params: [message, accounts[0]] }) as string;
  return sig;
}

export async function sendTransaction(tx: { to: string; value?: string; data?: string }): Promise<string> {
  if (!window.ethereum) throw new Error("No provider");
  const hash = await window.ethereum.request({ method: "eth_sendTransaction", params: [tx] }) as string;
  return hash;
}

export function onAccountChanged(callback: (address: string | null) => void): () => void {
  const handler = (...args: unknown[]) => callback((args[0] as string[] | undefined)?.[0] ?? null);
  window.ethereum?.on("accountsChanged", handler);
  return () => window.ethereum?.removeListener("accountsChanged", handler);
}
