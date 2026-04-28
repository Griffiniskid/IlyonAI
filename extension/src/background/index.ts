// Keep service worker alive
chrome.alarms.create("keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => {});

// Auth state management
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "CHECK_AUTH") {
    chrome.storage.local.get("ilyon_token", (r) => {
      sendResponse({ authenticated: !!r.ilyon_token });
    });
    return true;
  }
  if (msg.type === "SET_TOKEN") {
    chrome.storage.local.set({ ilyon_token: msg.token }, () => {
      sendResponse({ ok: true });
    });
    return true;
  }
  if (msg.type === "CLEAR_TOKEN") {
    chrome.storage.local.remove("ilyon_token", () => {
      sendResponse({ ok: true });
    });
    return true;
  }
});

// Side panel behavior
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });

// Notification on card frames
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "CARD_RECEIVED" && msg.card_type) {
    chrome.notifications?.create({
      type: "basic",
      iconUrl: "icons/icon48.png",
      title: `New ${msg.card_type} card`,
      message: msg.content?.slice(0, 100) || "Agent response received",
    });
  }
});
