/**
 * Permit2 wallet-capability detection via EIP-5792 wallet_getCapabilities.
 *
 * V7-038: returns true when any chain in the capabilities response advertises
 * permit2.supported = true. Returns false on any error (legacy wallets that do
 * not implement wallet_getCapabilities throw, which is expected).
 */
export async function detectPermit2Support(provider: any): Promise<boolean> {
    try {
        const caps = await provider.request({ method: "wallet_getCapabilities" });
        if (!caps) return false;
        for (const chainCaps of Object.values(caps)) {
            if ((chainCaps as any)?.permit2?.supported) return true;
        }
        return false;
    } catch {
        return false;
    }
}
