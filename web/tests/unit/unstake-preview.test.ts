import { describe, it, expect } from "vitest";
import { parseSwapPreview } from "@/components/agent-app/MainApp";

// Mirrors the real _build_unstake_tx SOL output (Jupiter route, has swapTransaction).
const solUnstakeJson = JSON.stringify({
  status: "ok",
  action: "unstake",
  is_unstake: true,
  liquid: true,
  staking_protocol: "Jito",
  swapTransaction: "AQ==",
  in_symbol: "JitoSOL",
  out_symbol: "SOL",
  from_token_symbol: "JitoSOL",
  to_token_symbol: "SOL",
  ui_in_amount: 0.05,
  ui_out_amount: 0.0557,
  out_amount: "55700000",
  route_summary: "Unstake JitoSOL → SOL",
  unstake_note: "Liquid unstake — your JitoSOL is swapped back to SOL instantly via Jupiter.",
});

// Mirrors the real _build_unstake_tx EVM output (Enso route, evm_action_proposal).
const evmUnstakeJson = JSON.stringify({
  status: "ok",
  type: "evm_action_proposal",
  action: "unstake",
  is_unstake: true,
  liquid: true,
  staking_protocol: "Lido",
  tx: { to: "0x1111111111111111111111111111111111111111", data: "0xabcdef", value: "0" },
  from_token_symbol: "stETH",
  to_token_symbol: "ETH",
  amount_in_display: 0.01,
  dst_amount_display: 0.0099,
  route_summary: "Unstake stETH → ETH",
  unstake_note: "Liquid unstake — your stETH is swapped back to ETH via Enso routing.",
});

describe("parseSwapPreview — unstake", () => {
  it("parses a SOL unstake (LST -> SOL) as an unstake preview, not a swap/stake", () => {
    const p = parseSwapPreview(solUnstakeJson);
    expect(p).not.toBeNull();
    expect(p?.isUnstake).toBe(true);
    expect(p?.isStake).toBeFalsy();
    expect(p?.actionType).toBe("unstake");
    expect(p?.fromToken).toBe("JitoSOL");
    expect(p?.fromAmount).toBe("0.05");
    expect(p?.toToken).toBe("SOL");
    expect(p?.toAmount).toBe("0.0557");
    expect(p?.liquid).toBe(true);
    expect(p?.swapTransaction).toBe("AQ==");
    expect(p?.unstakeNote).toContain("instantly");
  });

  it("parses an EVM unstake (stETH -> ETH) as an unstake preview", () => {
    const p = parseSwapPreview(evmUnstakeJson);
    expect(p).not.toBeNull();
    expect(p?.isUnstake).toBe(true);
    expect(p?.actionType).toBe("unstake");
    expect(p?.fromToken).toBe("stETH");
    expect(p?.fromAmount).toBe("0.01");
    expect(p?.toToken).toBe("ETH");
    expect(p?.toAmount).toBe("0.0099");
    expect(p?.rawTx).toBeTruthy();
  });
});
