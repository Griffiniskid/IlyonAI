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
    const assistantTarget = process.env.ASSISTANT_API_TARGET || "http://localhost:8000";
    return [
      { source: "/api/v1/agent-health", destination: `${assistantTarget}/health` },
      { source: "/api/v1/agent", destination: `${assistantTarget}/api/v1/agent` },
      { source: "/api/v1/chats", destination: `${assistantTarget}/api/v1/chats` },
      { source: "/api/v1/chats/:path*", destination: `${assistantTarget}/api/v1/chats/:path*` },
      { source: "/api/v1/auth/:path*", destination: `${assistantTarget}/api/v1/auth/:path*` },
      { source: "/api/v1/rpc-proxy", destination: `${assistantTarget}/api/v1/rpc-proxy` },
      { source: "/api/v1/bridge-status/:path*", destination: `${assistantTarget}/api/v1/bridge-status/:path*` },
      { source: "/api/portfolio/:path*", destination: `${assistantTarget}/api/portfolio/:path*` },
      { source: "/api/:path*", destination: `${apiTarget}/api/:path*` },
    ];
  },
};

module.exports = nextConfig;
