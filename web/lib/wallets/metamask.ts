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

/** Pick the REAL MetaMask EVM provider. When several wallets are installed,
 *  Phantom (if set as the default wallet) hijacks `window.ethereum`, so a
 *  "Connect with MetaMask" click would talk to Phantom's EVM — which doesn't
 *  support chains like BSC and throws "Unsupported network". EIP-5749 exposes
 *  all injected providers under `window.ethereum.providers`; prefer the
 *  MetaMask one there. Falls back to window.ethereum, then Phantom EVM. */
function getEvmProvider(): EthereumProvider | null {
  if (typeof window === "undefined") return null;
  const eth = window.ethereum as
    | (EthereumProvider & { providers?: EthereumProvider[] })
    | undefined;
  if (eth?.providers?.length) {
    const mm = eth.providers.find((p) => p.isMetaMask && !p.isPhantom);
    if (mm) return mm;
    const anyEvm = eth.providers.find((p) => !p.isPhantom);
    if (anyEvm) return anyEvm;
  }
  if (eth?.isMetaMask && !eth.isPhantom) return eth;
  if (eth) return eth;
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

/** Coerce an EVM quantity to a canonical 0x-hex string. eth_sendTransaction
 *  rejects decimal quantities ("0") with "Missing or invalid parameters" —
 *  some backends emit decimal value/gas, so normalize defensively here. */
function toHexQty(v?: string): string | undefined {
  if (v === undefined || v === null) return undefined;
  const s = String(v).trim();
  if (s === "") return undefined;
  if (s.startsWith("0x") || s.startsWith("0X")) return "0x" + (s.slice(2).replace(/^0+/, "") || "0");
  if (/^\d+$/.test(s)) return "0x" + BigInt(s).toString(16);
  return s;
}

// chainId → wallet_addEthereumChain params, for chains MetaMask may not know.
const ADD_CHAIN: Record<number, Record<string, unknown>> = {
  56: { chainId: "0x38", chainName: "BNB Smart Chain", nativeCurrency: { name: "BNB", symbol: "BNB", decimals: 18 }, rpcUrls: ["https://bsc-dataseed.binance.org"], blockExplorerUrls: ["https://bscscan.com"] },
  8453: { chainId: "0x2105", chainName: "Base", nativeCurrency: { name: "ETH", symbol: "ETH", decimals: 18 }, rpcUrls: ["https://mainnet.base.org"], blockExplorerUrls: ["https://basescan.org"] },
  42161: { chainId: "0xa4b1", chainName: "Arbitrum One", nativeCurrency: { name: "ETH", symbol: "ETH", decimals: 18 }, rpcUrls: ["https://arb1.arbitrum.io/rpc"], blockExplorerUrls: ["https://arbiscan.io"] },
  10: { chainId: "0xa", chainName: "OP Mainnet", nativeCurrency: { name: "ETH", symbol: "ETH", decimals: 18 }, rpcUrls: ["https://mainnet.optimism.io"], blockExplorerUrls: ["https://optimistic.etherscan.io"] },
  137: { chainId: "0x89", chainName: "Polygon", nativeCurrency: { name: "POL", symbol: "POL", decimals: 18 }, rpcUrls: ["https://polygon-rpc.com"], blockExplorerUrls: ["https://polygonscan.com"] },
  43114: { chainId: "0xa86a", chainName: "Avalanche C-Chain", nativeCurrency: { name: "AVAX", symbol: "AVAX", decimals: 18 }, rpcUrls: ["https://api.avax.network/ext/bc/C/rpc"], blockExplorerUrls: ["https://snowtrace.io"] },
};

/** Ensure the wallet is on `chainId` before signing — a tx signed on the wrong
 *  chain executes on the wrong chain. Switches (adding the chain if unknown). */
export async function ensureChain(chainId: number): Promise<void> {
  const eth = getEvmProvider();
  if (!eth || !chainId) return;
  const current = await getChainId();
  if (current === chainId) return;
  const hexId = "0x" + chainId.toString(16);
  try {
    await eth.request({ method: "wallet_switchEthereumChain", params: [{ chainId: hexId }] });
  } catch (err) {
    // 4902 = chain not added to the wallet → add it, then switch.
    const code = (err as { code?: number })?.code;
    if (code === 4902 && ADD_CHAIN[chainId]) {
      await eth.request({ method: "wallet_addEthereumChain", params: [ADD_CHAIN[chainId]] });
      await eth.request({ method: "wallet_switchEthereumChain", params: [{ chainId: hexId }] });
    } else {
      throw err;
    }
  }
}

export async function sendTransaction(tx: { to: string; value?: string; data?: string; from?: string; gas?: string; chainId?: number }): Promise<string> {
  const eth = getEvmProvider();
  if (!eth) throw new Error("No EVM provider");
  if (tx.chainId) await ensureChain(tx.chainId);
  let from = tx.from;
  if (!from) {
    const accounts = (await eth.request({ method: "eth_requestAccounts" })) as string[];
    from = accounts[0];
  }
  const params: Record<string, string> = { to: tx.to, from };
  const value = toHexQty(tx.value);
  const gas = toHexQty(tx.gas);
  if (value !== undefined) params.value = value;
  if (tx.data !== undefined) params.data = tx.data;
  if (gas !== undefined) params.gas = gas;
  const hash = (await eth.request({
    method: "eth_sendTransaction",
    params: [params],
  })) as string;
  return hash;
}

/** Read the wallet's currently selected chain id as a decimal number. */
export async function getChainId(): Promise<number> {
  const eth = getEvmProvider();
  if (!eth) throw new Error("No EVM provider");
  const hex = (await eth.request({ method: "eth_chainId" })) as string;
  return parseInt(hex, 16);
}

interface EthTxReceipt {
  status?: string | null;     // "0x1" success, "0x0" reverted
  blockNumber?: string | null;
  transactionHash?: string;
}

/**
 * Poll eth_getTransactionReceipt every `intervalMs` until non-null or
 * timeout. Returns the receipt object. Throws if the receipt status is
 * 0x0 (reverted) or the poll times out.
 *
 * Used by Eip7702OptInPanel + SessionKeyPanel to confirm the broadcast
 * before registering the tx hash with the backend audit table.
 */
export async function waitForReceipt(
  txHash: string,
  { intervalMs = 2500, timeoutMs = 180_000 }: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<EthTxReceipt> {
  const eth = getEvmProvider();
  if (!eth) throw new Error("No EVM provider");
  const start = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const r = (await eth.request({
      method: "eth_getTransactionReceipt",
      params: [txHash],
    })) as EthTxReceipt | null;
    if (r && r.blockNumber) {
      if (r.status === "0x0") {
        throw new Error(`tx reverted on-chain: ${txHash}`);
      }
      return r;
    }
    if (Date.now() - start > timeoutMs) {
      throw new Error(`receipt poll timed out after ${timeoutMs}ms: ${txHash}`);
    }
    await new Promise((res) => setTimeout(res, intervalMs));
  }
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
