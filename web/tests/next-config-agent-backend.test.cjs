const assert = require("assert");

async function loadRewrites(agentBackend) {
  delete require.cache[require.resolve("../next.config.js")];
  process.env.AGENT_BACKEND = agentBackend;
  process.env.API_REWRITE_TARGET = "http://sentinel:8080";
  process.env.ASSISTANT_API_TARGET = "http://wallet:8000";
  const config = require("../next.config.js");
  return config.rewrites();
}

(async () => {
  const sentinel = await loadRewrites("sentinel");
  const sentinelAgent = sentinel.find((r) => r.source === "/api/v1/agent");
  assert.strictEqual(sentinelAgent.destination, "http://sentinel:8080/api/v1/agent");

  const wallet = await loadRewrites("wallet");
  const walletAgent = wallet.find((r) => r.source === "/api/v1/agent");
  assert.strictEqual(walletAgent.destination, "http://wallet:8000/api/v1/agent");
})();
