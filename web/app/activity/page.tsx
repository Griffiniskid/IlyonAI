"use client";

import TransactionHistory from "@/components/agent-app/TransactionHistory";

// Transaction history also lives inside the Portfolio tab; this standalone route
// stays for direct links and renders the same component.
export default function ActivityPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6">
      <TransactionHistory />
    </div>
  );
}
