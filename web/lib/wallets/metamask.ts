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

/**
 * EIP-712 typed-data signing — used for Permit2 PermitSingle / PermitBatch
 * authorizations against Uniswap V4 PositionManager.
 *
 * Caller supplies the canonical Permit2 domain + types + message; this
 * helper hits eth_signTypedData_v4 on the active wallet and returns the
 * 65-byte ECDSA signature hex.
 */
export interface Permit2Domain {
  name: "Permit2";
  chainId: number;
  verifyingContract: string;  // canonical Permit2: 0x000000000022D473030F116dDEE9F6B43aC78BA3
}

export interface Permit2PermitSingleMessage {
  details: {
    token: string;
    amount: string;       // uint160 max for "infinite within this scope"
    expiration: string;   // uint48
    nonce: string;        // uint48
  };
  spender: string;        // V4 PositionManager address
  sigDeadline: string;    // uint256
}

const PERMIT2_TYPES = {
  PermitSingle: [
    { name: "details", type: "PermitDetails" },
    { name: "spender", type: "address" },
    { name: "sigDeadline", type: "uint256" },
  ],
  PermitDetails: [
    { name: "token", type: "address" },
    { name: "amount", type: "uint160" },
    { name: "expiration", type: "uint48" },
    { name: "nonce", type: "uint48" },
  ],
};

export async function signPermit2Typed(
  domain: Permit2Domain,
  message: Permit2PermitSingleMessage,
): Promise<string> {
  const eth = getEvmProvider();
  if (!eth) throw new Error("No EVM provider");
  const accounts = await eth.request({ method: "eth_requestAccounts" }) as string[];
  const owner = accounts[0];
  const payload = JSON.stringify({
    types: {
      EIP712Domain: [
        { name: "name", type: "string" },
        { name: "chainId", type: "uint256" },
        { name: "verifyingContract", type: "address" },
      ],
      ...PERMIT2_TYPES,
    },
    primaryType: "PermitSingle",
    domain,
    message,
  });
  const sig = await eth.request({
    method: "eth_signTypedData_v4",
    params: [owner, payload],
  }) as string;
  return sig;
}

export function onAccountChanged(callback: (address: string | null) => void): () => void {
  const eth = getEvmProvider();
  if (!eth) return () => {};
  const handler = (...args: unknown[]) => callback((args[0] as string[] | undefined)?.[0] ?? null);
  eth.on("accountsChanged", handler);
  return () => eth.removeListener("accountsChanged", handler);
}
