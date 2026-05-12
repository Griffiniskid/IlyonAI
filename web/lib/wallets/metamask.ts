interface EthereumProvider {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  on: (event: string, callback: (...args: unknown[]) => void) => void;
  removeListener: (event: string, callback: (...args: unknown[]) => void) => void;
  isMetaMask?: boolean;
  isPhantom?: boolean;
  selectedAddress?: string;
}

declare global {
  interface Window {
    ethereum?: EthereumProvider;
  }
}

/** Pick the first EVM provider available: MetaMask (window.ethereum) then
 *  Phantom EVM (window.phantom.ethereum). Returns null when neither exists.
 *  Reads window.phantom via `unknown` cast so we don't conflict with the
 *  Solana-shape declared in lib/wallets/phantom.ts. */
function getEvmProvider(): EthereumProvider | null {
  if (typeof window === "undefined") return null;
  if (window.ethereum) return window.ethereum;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const phantom = (window as any).phantom;
  if (phantom && phantom.ethereum) return phantom.ethereum as EthereumProvider;
  return null;
}

export async function connect(): Promise<string> {
  const eth = getEvmProvider();
  if (!eth) throw new Error("MetaMask / Phantom-EVM not detected");
  const accounts = await eth.request({ method: "eth_requestAccounts" }) as string[];
  return accounts[0];
}

export async function signMessage(message: string): Promise<string> {
  const eth = getEvmProvider();
  if (!eth) throw new Error("No EVM provider");
  const accounts = await eth.request({ method: "eth_requestAccounts" }) as string[];
  const sig = await eth.request({ method: "personal_sign", params: [message, accounts[0]] }) as string;
  return sig;
}

export async function sendTransaction(tx: { to: string; value?: string; data?: string }): Promise<string> {
  const eth = getEvmProvider();
  if (!eth) throw new Error("No EVM provider");
  const hash = await eth.request({ method: "eth_sendTransaction", params: [tx] }) as string;
  return hash;
}

export function onAccountChanged(callback: (address: string | null) => void): () => void {
  const eth = getEvmProvider();
  if (!eth) return () => {};
  const handler = (...args: unknown[]) => callback((args[0] as string[] | undefined)?.[0] ?? null);
  eth.on("accountsChanged", handler);
  return () => eth.removeListener("accountsChanged", handler);
}
