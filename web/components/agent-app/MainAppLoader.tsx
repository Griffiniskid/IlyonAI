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
  // Resolve the tab from the route. Prefer the /agent/<tab> PATH segment — usePathname
  // updates reliably on client navigation, whereas useSearchParams can return a stale
  // value mid-transition (the cause of "the button sometimes doesn't switch tabs").
  const pathTab = pathname?.split("/agent/")[1]?.split(/[/?]/)[0];
  const routeTab =
    pathTab === "chat" || pathTab === "portfolio" || pathTab === "dashboard"
      ? pathTab
      : tabParam;

  useEffect(() => {
    // Kept for any legacy listeners; the reliable path is the routeTab prop below.
    window.dispatchEvent(new Event("ilyon-tab-change"));
  }, [pathname, tabParam]);

  return <MainApp routeTab={routeTab} />;
}
