"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { PenTool } from "lucide-react";
import {
  signPermit2Typed,
  type Permit2Domain,
  type Permit2PermitSingleMessage,
} from "@/lib/wallets/metamask";

/**
 * Permit2 EIP-712 sign button — embedded in V4/V3 mint step cards.
 *
 * When the user clicks, calls MetaMask's eth_signTypedData_v4 with the
 * Permit2 PermitSingle typed-data, then POSTs the signature back to the
 * plan step so the runtime can include it in the V4
 * modifyLiquidities call.
 */
interface Permit2SigButtonProps {
  planId: string;
  stepId: string;
  chainId: number;
  permitMessage: Permit2PermitSingleMessage;
  onSigned?: (signature: string) => void;
}

export default function Permit2SigButton({
  planId,
  stepId,
  chainId,
  permitMessage,
  onSigned,
}: Permit2SigButtonProps) {
  const [signing, setSigning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [signed, setSigned] = useState(false);

  const onClick = async () => {
    setSigning(true);
    setError(null);
    try {
      const domain: Permit2Domain = {
        name: "Permit2",
        chainId,
        verifyingContract: "0x000000000022D473030F116dDEE9F6B43aC78BA3",
      };
      const signature = await signPermit2Typed(domain, permitMessage);
      // Post back so the runtime can splice it into the unsigned tx.
      try {
        await fetch(`/api/v1/plans/${planId}/steps/${stepId}/permit2`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            signature,
            permit: permitMessage,
          }),
        });
      } catch (e: any) {
        // Non-fatal — the signature is captured locally; user can re-broadcast.
      }
      setSigned(true);
      onSigned?.(signature);
    } catch (e: any) {
      setError(e?.message || "Permit2 signing rejected");
    } finally {
      setSigning(false);
    }
  };

  return (
    <div className="mt-2">
      <Button
        size="sm"
        onClick={onClick}
        disabled={signing || signed}
        className="w-full"
      >
        <PenTool className="h-4 w-4 mr-2" />
        {signed
          ? "Permit2 signed ✓"
          : signing
            ? "Awaiting signature…"
            : "Sign Permit2 allowance"}
      </Button>
      {error ? (
        <div className="mt-1 text-xs text-red-500">{error}</div>
      ) : null}
    </div>
  );
}
