import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],

  // Multiple entry points for the extension
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,

    rollupOptions: {
      input: {
        // Main web app (single page with full UI)
        index: resolve(__dirname, "index.html"),
        // Chrome extension: popup
        popup: resolve(__dirname, "popup.html"),
        // Chrome extension: side panel
        sidepanel: resolve(__dirname, "sidepanel.html"),
        // Background service worker
        background: resolve(__dirname, "src/background/index.ts"),
      },

      output: {
        // Deterministic filenames — Chrome extensions need stable chunk names
        entryFileNames: (chunkInfo) => {
          // Keep background SW at a flat path so manifest can reference it
          if (chunkInfo.name === "background") {
            return "src/background/index.js";
          }
          return "assets/[name].js";
        },
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name].[ext]",

        // Manual chunk splitting to keep vendor code separate
        manualChunks: (id) => {
          if (id.includes("node_modules/react") || id.includes("node_modules/react-dom")) {
            return "vendor-react";
          }
          if (id.includes("node_modules/")) {
            return "vendor";
          }
        },
      },
    },
  },

  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },

  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
