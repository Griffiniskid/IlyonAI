interface PhantomProvider {
  connect: () => Promise<{ publicKey: { toString: () => string } }>;
  disconnect: () => Promise<void>;
  signMessage: (message: Uint8Array) => Promise<{ signature: Uint8Array }>;
  isConnected: boolean;
  publicKey?: { toString: () => string };
}

declare global {
  interface Window {
    phantom?: { solana: PhantomProvider };
  }
}

export async function connect(): Promise<string> {
  const provider = window.phantom?.solana;
  if (!provider) throw new Error("Phantom not detected");
  const resp = await provider.connect();
  return resp.publicKey.toString();
}

export async function signMessage(message: string): Promise<Uint8Array> {
  const provider = window.phantom?.solana;
  if (!provider) throw new Error("Phantom not detected");
  const encoded = new TextEncoder().encode(message);
  const { signature } = await provider.signMessage(encoded);
  return signature;
}

export function isConnected(): boolean {
  return window.phantom?.solana?.isConnected ?? false;
}
