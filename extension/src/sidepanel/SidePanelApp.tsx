import React from "react";
import { ChatShell } from "@/components/agent/ChatShell";

export function SidePanelApp() {
  const [token, setToken] = React.useState<string | null>(null);

  React.useEffect(() => {
    chrome.storage.local.get("ilyon_token", (r) => setToken(r.ilyon_token || null));
  }, []);

  return <ChatShell token={token} />;
}
