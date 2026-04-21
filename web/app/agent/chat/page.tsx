"use client";
import { ChatShell } from "@/components/agent/ChatShell";
import { useWallet } from "@solana/wallet-adapter-react";

export default function AgentChatPage() {
  const { publicKey } = useWallet();
  const wallet = publicKey?.toBase58();
  // TODO: get token from auth when W4 is wired
  const token = typeof window !== "undefined" ? localStorage.getItem("ilyon_token") : null;

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      <ChatShell token={token} wallet={wallet} />
    </div>
  );
}
