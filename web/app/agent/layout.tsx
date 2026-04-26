import type { ReactNode } from "react";
import "./agent-overrides.css";
import MainAppLoader from "@/components/agent-app/MainAppLoader";

export default function AgentLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex-1 flex flex-col min-h-0 bg-background">
      <MainAppLoader />
      {/* Page bodies render nothing — MainApp is the single mounted instance.
          The route segment is read by MainApp's URL→tab bridge to switch tabs. */}
      <div style={{ display: "none" }}>{children}</div>
    </div>
  );
}
