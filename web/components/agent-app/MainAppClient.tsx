"use client";

import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";

const MainApp = dynamic(() => import("@/lib/agent-app/MainApp"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[calc(100vh-4rem)] items-center justify-center text-sm text-muted-foreground">
      Loading agent…
    </div>
  ),
});

export default function MainAppClient() {
  const pathname = usePathname();
  return <MainApp key={pathname} />;
}
