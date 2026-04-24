"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { DemoChatFrame } from "@/components/agent/DemoChatFrame";
import { useMultiWallet } from "@/components/providers/WalletProvider";

function ChatPageContent() {
  const { solAddress, evmAddress } = useMultiWallet();
  const wallet = solAddress || evmAddress || undefined;
  const searchParams = useSearchParams();
  const prompt = searchParams.get("prompt");

  return (
    <div className="flex min-h-[calc(100vh-10rem)] flex-col">
      <DemoChatFrame token={null} wallet={wallet} initialPrompt={prompt || undefined} />
    </div>
  );
}

export default function AgentChatPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-[calc(100vh-4rem)] items-center justify-center">Loading...</div>
      }
    >
      <ChatPageContent />
    </Suspense>
  );
}
