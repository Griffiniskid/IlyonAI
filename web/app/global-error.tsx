"use client";

import React from "react";

// Global error boundary — the last line of defense. Catches errors thrown in
// the root layout itself (which app/error.tsx cannot) and must render its own
// <html>/<body>. `error?.message` guards against a null/non-Error value, the
// case that crashed Next's own minified error sink in production.
export default function GlobalError({
  error,
  reset,
}: {
  error: (Error & { digest?: string }) | null;
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 16,
          background: "#0a0a0a",
          color: "#fff",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <h2 style={{ fontSize: 20, fontWeight: 600 }}>Something went wrong</h2>
        <p style={{ color: "#9ca3af", maxWidth: 420, textAlign: "center" }}>
          {error?.message || "An unexpected error occurred. Please try again."}
        </p>
        <button
          onClick={() => reset()}
          style={{ padding: "8px 16px", borderRadius: 8, background: "#059669", color: "#000", fontWeight: 600, cursor: "pointer", border: "none" }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
