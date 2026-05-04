/** @type {import('next').NextConfig} */
const fs = require("fs");
const path = require("path");

const preferredDistDir = process.env.NEXT_DIST_DIR || ".next-local";
let safeDistDir = preferredDistDir;

try {
  const preferredDistPath = path.join(__dirname, preferredDistDir);
  fs.mkdirSync(preferredDistPath, { recursive: true });
  fs.accessSync(preferredDistPath, fs.constants.W_OK);

  const preferredServerPath = path.join(preferredDistPath, "server");
  if (fs.existsSync(preferredServerPath)) {
    fs.accessSync(preferredServerPath, fs.constants.W_OK);
  }
} catch {
  safeDistDir = ".next";
}

const nextConfig = {
  reactStrictMode: false,
  output: 'standalone',
  distDir: safeDistDir,
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
    ],
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080",
    NEXT_PUBLIC_SOLANA_NETWORK: process.env.NEXT_PUBLIC_SOLANA_NETWORK || "mainnet-beta",
  },
  async rewrites() {
    const apiTarget = process.env.API_REWRITE_TARGET || "http://localhost:8080";
    const walletAssistantTarget = process.env.ASSISTANT_API_TARGET || "http://localhost:8000";
    const agentBackend = process.env.AGENT_BACKEND || "sentinel";
    const agentTarget = agentBackend === "sentinel" ? apiTarget : walletAssistantTarget;
    return [
      { source: "/api/v1/agent-health", destination: `${agentTarget}/health` },
      { source: "/api/v1/agent", destination: `${agentTarget}/api/v1/agent` },
      { source: "/api/v1/chats", destination: `${walletAssistantTarget}/api/v1/chats` },
      { source: "/api/v1/chats/:path*", destination: `${walletAssistantTarget}/api/v1/chats/:path*` },
      { source: "/api/v1/auth/:path*", destination: `${walletAssistantTarget}/api/v1/auth/:path*` },
      { source: "/api/v1/rpc-proxy", destination: `${walletAssistantTarget}/api/v1/rpc-proxy` },
      { source: "/api/v1/bridge-status/:path*", destination: `${walletAssistantTarget}/api/v1/bridge-status/:path*` },
      { source: "/api/portfolio/:path*", destination: `${walletAssistantTarget}/api/portfolio/:path*` },
      { source: "/api/:path*", destination: `${apiTarget}/api/:path*` },
      // Solana Actions / Blinks — Phantom dial-actions and Twitter
      // unfurlers hit these directly on the bare domain.
      { source: "/.well-known/actions.json", destination: `${apiTarget}/.well-known/actions.json` },
      { source: "/actions.json", destination: `${apiTarget}/actions.json` },
      { source: "/actions/:path*", destination: `${apiTarget}/actions/:path*` },
      { source: "/blinks/:path*", destination: `${apiTarget}/blinks/:path*` },
    ];
  },
};

module.exports = nextConfig;
