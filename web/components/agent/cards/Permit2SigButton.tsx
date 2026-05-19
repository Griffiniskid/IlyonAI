"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { PenTool } from "lucide-react";
import type {
  Permit2Domain,
  Permit2PermitSingleMessage,
} from "@/lib/wallets/metamask";
import { useWalletSigning } from "@/hooks/useWalletSigning";

/**
 * Permit2 EIP-712 sign button — embedded in V4/V3 mint step cards.
 *
 * Routes through `useWalletSigning` (V7-045) so the 30s freshness gate
 * and calldata-hash bind run before the wallet popup opens. After
 * signing, POSTs the signature back to the plan step so the runtime
 * can include it in the V4 modifyLiquidities call.
 */
interface Permit2SigButtonProps {
  planId: string;
  stepId: string;
  chainId: number;
  permitMessage: Permit2PermitSingleMessage;
  /** SHA-256 hex of canonical Permit2 payload, stamped at sim time. */
  simulatedCalldataHash: string;
  /** POSIX seconds when the backend simulated the artifact. */
  simulatedAt: number;
  onSigned?: (signature: string) => void;
}

export default function Permit2SigButton({
  planId,
  stepId,
  chainId,
  permitMessage,
  simulatedCalldataHash,
  simulatedAt,
  onSigned,
}: Permit2SigButtonProps) {
  const { sign, isPending } = useWalletSigning();
  const [error, setError] = useState<string | null>(null);
  const [signed, setSigned] = useState(false);

  const onClick = async () => {
    setError(null);
    try {
      const domain: Permit2Domain = {
        name: "Permit2",
        chainId,
        verifyingContract: "0x000000000022D473030F116dDEE9F6B43aC78BA3",
      };
      const result = await sign({
        mode: "evm_typed_data",
        domain,
        message: permitMessage,
        simTimestamp: simulatedAt,
        expectedCalldataHash: simulatedCalldataHash,
      });
      const signature = result.signature ?? "";
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
      } catch {
        // Non-fatal — the signature is captured locally; user can re-broadcast.
      }
      setSigned(true);
      onSigned?.(signature);
    } catch (e: unknown) {
      const msg =
        e instanceof Error ? e.message : "Permit2 signing rejected";
      setError(msg);
    }
  };

  return (
    <div className="mt-2">
      <Button
        size="sm"
        onClick={onClick}
        disabled={isPending || signed}
        className="w-full"
      >
        <PenTool className="h-4 w-4 mr-2" />
        {signed
          ? "Permit2 signed"
          : isPending
            ? "Awaiting signature…"
            : "Sign Permit2 allowance"}
      </Button>
      {error ? (
        <div className="mt-1 text-xs text-red-500">{error}</div>
      ) : null}
    </div>
  );
}
