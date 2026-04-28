import { Suspense, type ReactNode } from "react";
import "./agent-overrides.css";
import MainAppLoader from "@/components/agent-app/MainAppLoader";

export default function AgentLayout({ children }: { children: ReactNode }) {
  return (
    <div data-agent-route className="flex-1 h-full flex flex-col min-h-0 overflow-hidden bg-background">
      <Suspense fallback={null}>
        <MainAppLoader />
      </Suspense>
      {/* Page bodies render nothing — MainApp is the single mounted instance.
          The route segment is read by MainApp's URL→tab bridge to switch tabs. */}
      <div style={{ display: "none" }}>{children}</div>
    </div>
  );
}
