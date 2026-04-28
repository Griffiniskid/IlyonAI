import { createRequire } from "module";
import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const nextConfig = require("../../next.config.js");

describe("Next rewrites", () => {
  it("keeps main auth on the API backend and exposes assistant auth separately", async () => {
    process.env.API_REWRITE_TARGET = "http://api:8080";
    process.env.ASSISTANT_API_TARGET = "http://assistant-api:8000";

    const rewrites = await nextConfig.rewrites();

    expect(rewrites).toContainEqual({
      source: "/api/v1/assistant-auth/:path*",
      destination: "http://assistant-api:8000/api/v1/auth/:path*",
    });
    expect(rewrites).not.toContainEqual({
      source: "/api/v1/auth/:path*",
      destination: "http://assistant-api:8000/api/v1/auth/:path*",
    });
    expect(rewrites.at(-1)).toEqual({
      source: "/api/:path*",
      destination: "http://api:8080/api/:path*",
    });
  });
});
