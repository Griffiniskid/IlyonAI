import React from "react";
import { ChatShell } from "@/components/agent/ChatShell";

export function PopupApp() {
  const [token, setToken] = React.useState<string | null>(null);

  React.useEffect(() => {
    chrome.storage.local.get("ilyon_token", (r) => setToken(r.ilyon_token || null));
  }, []);

  if (!token) {
    return (
      <div className="flex items-center justify-center h-full text-slate-400 text-sm">
        Please log in via the sidepanel
      </div>
    );
  }

  return <ChatShell token={token} />;
}
