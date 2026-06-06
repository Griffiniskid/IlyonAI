import { describe, it, expect } from "vitest";
import { parseSwapPreview } from "@/components/agent-app/MainApp";

const stakeJson = JSON.stringify({
  status: "ok",
  type: "solana_swap_proposal",
  chain_type: "solana",
  action: "stake",
  is_stake: true,
  staking_protocol: "Jito",
  receipt_token_symbol: "jitoSOL",
  swapTransaction: "AQ==",
  out_amount: "778324562",
  ui_out_amount: 0.77833,
  ui_in_amount: 1,
  in_symbol: "SOL",
  out_symbol: "jitoSOL",
  from_token_symbol: "SOL",
  to_token_symbol: "Jito JitoSOL",
  route_summary: "Stake via Jito JitoSOL",
  liquid: true,
  unstake_note: "Liquid stake — unstake anytime.",
  apy: 5.18,
  est_yearly_yield_sol: 0.000518,
});

describe("parseSwapPreview — stake", () => {
  it("parses a SOL stake into a stake preview (not a plain swap)", () => {
    const p = parseSwapPreview(stakeJson);
    expect(p).not.toBeNull();
    expect(p?.isStake).toBe(true);
    expect(p?.actionType).toBe("stake");
    expect(p?.fromAmount).toBe("1");
    expect(p?.fromToken).toBe("SOL");
    expect(p?.receiptToken).toBe("jitoSOL");
    expect(p?.liquid).toBe(true);
    expect(p?.swapTransaction).toBe("AQ==");
    expect(p?.apy).toBe(5.18);
    expect(p?.estYearly).toBe(0.000518);
  });
});
