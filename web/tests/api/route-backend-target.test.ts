import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { _resolveBackendTarget } from "@/app/api/v1/agent/route";

// Replaces the old route-backend-switch.test.cjs (a node:vm source-extraction hack
// that broke whenever route.ts gained a typed helper). Imports the real exported
// function and exercises the backend-target resolution directly.
const ENV_KEYS = ["AGENT_BACKEND", "SENTINEL_API_TARGET", "ASSISTANT_API_TARGET"] as const;
const saved: Record<string, string | undefined> = {};

describe("_resolveBackendTarget", () => {
  beforeEach(() => {
    for (const k of ENV_KEYS) {
      saved[k] = process.env[k];
      delete process.env[k];
    }
  });
  afterEach(() => {
    for (const k of ENV_KEYS) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  });

  it("defaults to the sentinel backend (8080)", () => {
    expect(_resolveBackendTarget()).toBe("http://localhost:8080");
  });

  it("AGENT_BACKEND=wallet returns ASSISTANT_API_TARGET", () => {
    process.env.AGENT_BACKEND = "wallet";
    process.env.ASSISTANT_API_TARGET = "http://wallet-custom:7000";
    expect(_resolveBackendTarget()).toBe("http://wallet-custom:7000");
  });

  it("AGENT_BACKEND=sentinel returns SENTINEL_API_TARGET", () => {
    process.env.AGENT_BACKEND = "sentinel";
    process.env.SENTINEL_API_TARGET = "http://sentinel-custom:9090";
    expect(_resolveBackendTarget()).toBe("http://sentinel-custom:9090");
  });

  it("wallet backend falls back to http://localhost:8000", () => {
    process.env.AGENT_BACKEND = "wallet";
    expect(_resolveBackendTarget()).toBe("http://localhost:8000");
  });

  it("sentinel backend falls back to http://localhost:8080", () => {
    process.env.AGENT_BACKEND = "sentinel";
    expect(_resolveBackendTarget()).toBe("http://localhost:8080");
  });

  it("honors the explicit `selected` arg when AGENT_BACKEND is unset", () => {
    process.env.ASSISTANT_API_TARGET = "http://wallet:8000";
    expect(_resolveBackendTarget("wallet")).toBe("http://wallet:8000");
  });

  it("AGENT_BACKEND override wins over the `selected` arg", () => {
    process.env.AGENT_BACKEND = "sentinel";
    process.env.SENTINEL_API_TARGET = "http://forced-sentinel:8080";
    expect(_resolveBackendTarget("wallet")).toBe("http://forced-sentinel:8080");
  });
});
