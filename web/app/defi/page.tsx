import React from "react";
import DiscoverClient from "./_components/discover-client";

export const metadata = {
  title: "DeFi Discover",
  description: "Discover new DeFi opportunities",
};

export default function DefiDiscoverPage() {
  return (
    <main className="container mx-auto py-8">
      <DiscoverClient />
    </main>
  );
}
