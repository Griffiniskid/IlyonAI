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

  useEffect(() => {
    window.dispatchEvent(new Event("ilyon-tab-change"));
  }, [pathname, tabParam]);

  return <MainApp />;
}
