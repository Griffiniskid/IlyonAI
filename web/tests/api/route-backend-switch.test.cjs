const assert = require("node:assert");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { Script } = require("node:vm");

// Read the route.ts source
const routeSource = readFileSync(
  join(process.cwd(), "app/api/v1/agent/route.ts"),
  "utf8"
);

function extractAndRunFunction(env) {
  const originalEnv = { ...process.env };
  Object.keys(env).forEach((key) => {
    if (env[key] === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = env[key];
    }
  });

  try {
    // Extract just the _resolveBackendTarget function and its dependencies
    // We need to handle the TS import and convert to JS
    const jsSource = routeSource
      .replace(/import\s+{[^}]+}\s+from\s+"[^"]+";?\n?/g, "")
      .replace(/export\s+const\s+/g, "const ")
      .replace(/export\s+async\s+function/g, "async function")
      .replace(/export\s+function/g, "function")
      .replace(/:\s*NextRequest\b/g, "")
      .replace(/:\s*Promise\u003cResponse\u003e/g, "")
      .replace(/:\s*Headers/g, "")
      .replace(/\bNextRequest\b/g, "Object")
      .replace(/AbortSignal\.timeout/g, "(() => ({ signal: {} }))()")
      .replace(/\):\s*string\s*{/g, ") {");

    // Create a script that exports the function
    const script = new Script(`
      ${jsSource}
      _resolveBackendTarget;
    `);

    const context = {
      process,
      console,
      fetch: () => {},
      Response: Object,
      Headers: class Headers {
        constructor() { this._headers = {}; }
        set(k, v) { this._headers[k] = v; }
        get(k) { return this._headers[k]; }
      },
    };

    const fn = script.runInNewContext(context);
    const result = fn();
    return result;
  } finally {
    // Restore env
    Object.keys(process.env).forEach((key) => delete process.env[key]);
    Object.assign(process.env, originalEnv);
  }
}

function test(name, fn) {
  try {
    fn();
    console.log(`  PASS: ${name}`);
  } catch (err) {
    console.error(`  FAIL: ${name}`);
    console.error(`    ${err.message}`);
    process.exitCode = 1;
  }
}

console.log("route-backend-switch.test.cjs");

test("exports _resolveBackendTarget function in source", () => {
  assert.ok(
    routeSource.includes("export function _resolveBackendTarget") ||
    routeSource.includes("export async function _resolveBackendTarget") ||
    routeSource.includes("export const _resolveBackendTarget"),
    "route.ts should export _resolveBackendTarget"
  );
});

test("_resolveBackendTarget reads AGENT_BACKEND env var", () => {
  assert.ok(
    routeSource.includes("AGENT_BACKEND"),
    "should reference AGENT_BACKEND"
  );
});

test("default backend target is sentinel (port 8080)", () => {
  const result = extractAndRunFunction({});
  assert.strictEqual(
    result,
    "http://localhost:8080",
    "default should be sentinel backend"
  );
});

test("wallet backend returns ASSISTANT_API_TARGET", () => {
  const result = extractAndRunFunction({
    AGENT_BACKEND: "wallet",
    ASSISTANT_API_TARGET: "http://wallet-custom:7000",
  });
  assert.strictEqual(
    result,
    "http://wallet-custom:7000",
    "should return ASSISTANT_API_TARGET"
  );
});

test("sentinel backend returns SENTINEL_API_TARGET", () => {
  const result = extractAndRunFunction({
    AGENT_BACKEND: "sentinel",
    SENTINEL_API_TARGET: "http://sentinel-custom:9090",
  });
  assert.strictEqual(
    result,
    "http://sentinel-custom:9090",
    "should return SENTINEL_API_TARGET"
  );
});

test("wallet backend uses default ASSISTANT_API_TARGET", () => {
  const result = extractAndRunFunction({ AGENT_BACKEND: "wallet" });
  assert.strictEqual(
    result,
    "http://localhost:8000",
    "should default to http://localhost:8000"
  );
});

test("sentinel backend uses default SENTINEL_API_TARGET", () => {
  const result = extractAndRunFunction({ AGENT_BACKEND: "sentinel" });
  assert.strictEqual(
    result,
    "http://localhost:8080",
    "should default to http://localhost:8080"
  );
});

test("POST handler uses resolved backend target", () => {
  // Check that POST calls _resolveBackendTarget or uses the target variable
  assert.ok(
    routeSource.includes("_resolveBackendTarget()") ||
    routeSource.match(/const\s+\w+\s*=\s*_resolveBackendTarget/),
    "POST should use _resolveBackendTarget"
  );
});

console.log("\nDone.");
