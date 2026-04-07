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
    NEXT_PUBLIC_COMING_SOON: process.env.NEXT_PUBLIC_COMING_SOON || "true",
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
