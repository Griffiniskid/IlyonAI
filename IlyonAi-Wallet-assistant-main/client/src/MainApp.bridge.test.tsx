import { describe, expect, it } from "vitest";

import { parseSwapPreview } from "./MainApp";


describe("parseSwapPreview bridge handling", () => {
  it("parses Solana bridge proposals as bridges instead of swaps", () => {
    const payload = JSON.stringify({
      status: "ok",
      type: "bridge_proposal",
      chain_type: "solana",
      from_token_symbol: "SOL",
      to_token_symbol: "BNB",
      amount_in_display: 0.23259,
      requested_amount_display: 0.2,
      dst_amount_display: 0.03496,
      route_summary: "deBridge DLN",
      estimated_fill_time_seconds: 12,
      estimated_fee_display: "~0.024162 SOL",
      source_execution_summary: "SOL on Solana is first converted into ~18.075884 USDC before the cross-chain fill.",
      src_chain_name: "Solana",
      dst_chain_name: "BNB Smart Chain",
      order_id: "0xbridge-order",
      warnings: [
        "Phantom may show a temporary source-chain swap into USDC before bridging. Final destination asset remains BNB on BNB Smart Chain.",
      ],
      tx: {
        serialized: "AQID",
        chain_id: 101,
      },
    });

    const preview = parseSwapPreview(payload);

    expect(preview).not.toBeNull();
    expect(preview?.isBridge).toBe(true);
    expect(preview?.actionType).toBe("bridge");
    expect(preview?.isSolanaSwap).toBe(true);
    expect(preview?.fromToken).toBe("SOL");
    expect(preview?.toToken).toBe("BNB");
    expect(preview?.bridgeRequestedAmount).toBe("0.2");
    expect(preview?.sourceExecutionSummary).toContain("USDC");
    expect(preview?.swapTransaction).toBe("AQID");
    expect(preview?.route).toBe("deBridge DLN");
  });
});
