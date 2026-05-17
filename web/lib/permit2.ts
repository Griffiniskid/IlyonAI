import { TypedDataDomain, TypedDataField } from "ethers";

export const PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3";

export interface Permit2PermitSingle {
  details: {token: string; amount: bigint | string; expiration: number; nonce: number;};
  spender: string;
  sigDeadline: number;
}

export function buildPermit2Domain(chainId: number): TypedDataDomain {
  return {name: "Permit2", chainId, verifyingContract: PERMIT2_ADDRESS};
}

export const PERMIT_SINGLE_TYPES: Record<string, TypedDataField[]> = {
  PermitDetails: [
    {name: "token", type: "address"},
    {name: "amount", type: "uint160"},
    {name: "expiration", type: "uint48"},
    {name: "nonce", type: "uint48"},
  ],
  PermitSingle: [
    {name: "details", type: "PermitDetails"},
    {name: "spender", type: "address"},
    {name: "sigDeadline", type: "uint256"},
  ],
};

export async function signPermit2Typed(
  signer: any,
  chainId: number,
  permit: Permit2PermitSingle,
): Promise<string> {
  const domain = buildPermit2Domain(chainId);
  return await signer.signTypedData(domain, PERMIT_SINGLE_TYPES, permit);
}
