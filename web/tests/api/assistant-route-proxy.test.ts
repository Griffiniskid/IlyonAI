import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { _resolveBackendTarget, _selectBackendTarget } from "@/app/api/v1/agent/route";

describe("assistant route proxy", () => {
  it("uses an explicit node route handler instead of only Next rewrites", () => {
    const route = readFileSync(join(process.cwd(), "app/api/v1/agent/route.ts"), "utf8");

    expect(route).toContain('runtime = "nodejs"');
    expect(route).toContain("ASSISTANT_API_TARGET");
    expect(route).toContain("/api/v1/agent");
    expect(route).toContain("AbortSignal.timeout");
  });

  it("routes swap and bridge execution intents to the wallet assistant", () => {
    expect(_selectBackendTarget(JSON.stringify({ query: "swap 0.2 SOL to USDC" }))).toBe("wallet");
    expect(_selectBackendTarget(JSON.stringify({ query: "bridge 10 USDC from Base to Solana" }))).toBe("wallet");
    expect(_selectBackendTarget(JSON.stringify({ query: "swap USDC to SOL then bridge to Arbitrum" }))).toBe("wallet");
    expect(_selectBackendTarget(JSON.stringify({ query: "stake 2 ETH on Lido" }))).toBe("wallet");
    expect(_selectBackendTarget(JSON.stringify({ query: "stake 2 ETH for yield on Lido" }))).toBe("wallet");
    expect(_selectBackendTarget(JSON.stringify({ query: "bridge USDC to Arbitrum for staking yield" }))).toBe("wallet");
  });

  it("keeps Sentinel allocation and methodology intents on Sentinel", () => {
    expect(_selectBackendTarget(JSON.stringify({ query: "allocate 10000 USDC across best yield" }))).toBe("sentinel");
    expect(_selectBackendTarget(JSON.stringify({ query: "how does Sentinel scoring work" }))).toBe("sentinel");
  });

  it("keeps pool and yield strategy research on Sentinel instead of the wallet regex path", () => {
    expect(_selectBackendTarget(JSON.stringify({ query: "show medium/high risk pools around 100% APY" }))).toBe("sentinel");
    expect(_selectBackendTarget(JSON.stringify({ query: "deposit 100 USDC into the best USDC/ETH pool" }))).toBe("sentinel");
    expect(_selectBackendTarget(JSON.stringify({ query: "research Solana farms targeting 60% APY, then execute it" }))).toBe("sentinel");
    expect(_selectBackendTarget(JSON.stringify({ query: "find vaults on Base with high yield" }))).toBe("sentinel");
  });

  it("uses hybrid routing unless AGENT_BACKEND explicitly forces a backend", () => {
    const old = process.env.AGENT_BACKEND;
    delete process.env.AGENT_BACKEND;
    expect(_resolveBackendTarget("wallet")).toContain("localhost:8000");
    expect(_resolveBackendTarget("sentinel")).toContain("localhost:8080");
    process.env.AGENT_BACKEND = "hybrid";
    expect(_resolveBackendTarget("wallet")).toContain("localhost:8000");
    process.env.AGENT_BACKEND = old;
  });

  it("does not force Sentinel in the default compose environment", () => {
    const compose = readFileSync(join(process.cwd(), "..", "docker-compose.yml"), "utf8");

    expect(compose).not.toMatch(/AGENT_BACKEND:\s*sentinel/);
    expect(compose).toMatch(/AGENT_BACKEND:\s*\$\{AGENT_BACKEND:-hybrid\}/);
  });

  it("respects AGENT_BACKEND force override", () => {
    const old = process.env.AGENT_BACKEND;
    process.env.AGENT_BACKEND = "wallet";
    expect(_resolveBackendTarget("sentinel")).toContain("localhost:8000");
    process.env.AGENT_BACKEND = "sentinel";
    expect(_resolveBackendTarget("wallet")).toContain("localhost:8080");
    process.env.AGENT_BACKEND = old;
  });
});
