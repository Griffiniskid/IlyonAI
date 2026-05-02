"use client";
import { DemoChatFrame } from "@/components/agent/DemoChatFrame";

export default function DemoPage() {
  return (
    <main className="min-h-screen bg-background">
      <DemoChatFrame token={null} />
    </main>
  );
}
