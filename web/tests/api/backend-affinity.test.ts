import { describe, expect, it } from "vitest";
import { _isAmbiguousFollowup, _isReasoningQuestion, _isUnstakeCommand, _selectBackendTarget } from "@/app/api/v1/agent/route";

describe("_isAmbiguousFollowup", () => {
  it("flags short affirmations / continuations (need prior context)", () => {
    for (const q of [
      "yes do that", "yes", "yeah", "ok", "okay", "sure", "go ahead",
      "do that", "do it", "the first one", "that one", "continue", "proceed",
    ]) {
      expect(_isAmbiguousFollowup(q), q).toBe(true);
    }
  });

  it("does NOT flag messages with an actionable DeFi signal", () => {
    for (const q of [
      "stake 1 SOL", "swap 1 sol to usdc", "what is the best yield",
      "analyze this token", "check my balance", "bridge 1 eth to base",
      "tell me about jito staking", "is this safe",
    ]) {
      expect(_isAmbiguousFollowup(q), q).toBe(false);
    }
  });

  it("does NOT flag a pasted token address", () => {
    expect(_isAmbiguousFollowup("0x1234567890abcdef1234567890abcdef12345678")).toBe(false);
    expect(_isAmbiguousFollowup("262o7xFCzVWxxVZmjPCBMCKtunieXARcZoyGmrkvpump")).toBe(false);
  });
});

describe("_selectBackendTarget base routing unchanged", () => {
  it("stake -> wallet, bare follow-up -> sentinel default", () => {
    expect(_selectBackendTarget(JSON.stringify({ query: "stake 1 SOL" }))).toBe("wallet");
    expect(_selectBackendTarget(JSON.stringify({ query: "yes do that" }))).toBe("sentinel");
  });
});

describe("_isReasoningQuestion -> reasoned by the LLM (sentinel)", () => {
  it("flags analytical / advice / what-if questions", () => {
    for (const q of [
      "is it worth staking 0.01 SOL if the fees eat the rewards?",
      "should I stake or just hold?",
      "what happens to my jitoSOL if SOL crashes 50%?",
      "if I stake 1 SOL how much will I have in 2 years?",
      "which is better, jito or marinade?",
      "can I lose money staking with jito?",
      "what's the catch with 5% APY?",
      "explain liquid staking like I'm five",
      // position / "what we did" follow-ups must reason with history, not dump links
      "where can i check my staking position?",
      "No im saying about my position that we just did",
      "how do i see my stake",
    ]) {
      expect(_isReasoningQuestion(q), q).toBe(true);
    }
  });

  it("does NOT flag execution commands, lookups, or 'where can i stake' (links)", () => {
    for (const q of [
      "stake 1 SOL", "swap 1 sol to usdc", "what is sol price", "my balance",
      "best sol pool", "bridge 1 eth to base",
      "where can i stake SOL",   // a request for staking links — keep on the links path
      "check my balance",        // a lookup, not a reasoning question
    ]) {
      expect(_isReasoningQuestion(q), q).toBe(false);
    }
  });

  it("routes a reasoning question to the sentinel even when it contains 'stake'", () => {
    expect(_selectBackendTarget(JSON.stringify({ query: "is it worth staking 0.01 SOL if fees eat rewards" }))).toBe("sentinel");
    expect(_selectBackendTarget(JSON.stringify({ query: "if I stake 1 SOL how much in 2 years" }))).toBe("sentinel");
    // plain command still goes to the execution backend
    expect(_selectBackendTarget(JSON.stringify({ query: "stake 1 SOL" }))).toBe("wallet");
  });
});

describe("unstake routing", () => {
  it("imperative unstake commands -> wallet (execute), despite 'my position/jitoSOL'", () => {
    for (const q of [
      "unstake my jitoSOL",
      "unstake all my jitoSOL",
      "unstake 0.5 mSOL",
      "unstake everything",
      "unstake my position",
      "un-stake my stETH",
      "redeem my stETH",
      "withdraw my jitoSOL stake",
    ]) {
      expect(_isUnstakeCommand(q), q).toBe(true);
      expect(_selectBackendTarget(JSON.stringify({ query: q })), q).toBe("wallet");
    }
  });

  it("questions ABOUT unstaking -> sentinel (reason, do not execute)", () => {
    for (const q of [
      "should I unstake my jitoSOL?",
      "is it worth unstaking now?",
      "how much will I get if I unstake my jitoSOL?",
      "when can I unstake?",
      "why would I unstake my stETH?",
    ]) {
      expect(_isUnstakeCommand(q), q).toBe(false);
      expect(_selectBackendTarget(JSON.stringify({ query: q })), q).toBe("sentinel");
    }
  });

  it("does not over-trigger on plain withdrawals / unrelated text", () => {
    expect(_isUnstakeCommand("withdraw 100 USDC to my bank"), "plain withdraw").toBe(false);
    expect(_isUnstakeCommand("swap 1 sol to usdc"), "swap").toBe(false);
  });

  it("a short 'unstake' is not treated as a context-free follow-up", () => {
    expect(_isAmbiguousFollowup("unstake my jitoSOL")).toBe(false);
    expect(_isAmbiguousFollowup("redeem my stETH")).toBe(false);
  });
});
