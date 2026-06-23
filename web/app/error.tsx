"use client";

import React, { useEffect } from "react";

// Root segment-level error boundary. Catches render/runtime errors in any page
// under app/ and shows a graceful fallback instead of Next's generic
// "Application error: a client-side exception has occurred" white screen.
// `error?.message` (optional chaining) guards against a null / non-Error value
// being thrown — the exact case that produced the prod "Cannot read properties
// of null (reading 'message')" crash.
export default function AppError({
  error,
  reset,
}: {
  error: (Error & { digest?: string }) | null;
  reset: () => void;
}) {
  useEffect(() => {
    if (error) console.error(error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 px-4 text-center">
      <h2 className="text-xl font-semibold text-white">Something went wrong</h2>
      <p className="text-white/50 max-w-md">
        {error?.message || "An unexpected error occurred while loading this page."}
      </p>
      <button
        onClick={() => reset()}
        className="px-4 py-2 rounded-lg bg-emerald-600 text-black font-semibold hover:bg-emerald-500 transition-colors"
      >
        Try again
      </button>
    </div>
  );
}
