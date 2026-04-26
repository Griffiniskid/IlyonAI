"use client";

import { useEffect } from "react";
import dynamic from "next/dynamic";
import { usePathname, useSearchParams } from "next/navigation";

const MainApp = dynamic(() => import("./MainApp"), {
  ssr: false,
  loading: () => null,
});

export default function MainAppLoader() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");

  // On every Next.js client-side navigation, fire the bridge event MainApp listens for.
  // MainApp's useEffect re-reads window.location.search and updates its activeTab state.
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.dispatchEvent(new Event("ilyon-tab-change"));
  }, [pathname, tabParam]);

  return <MainApp />;
}
