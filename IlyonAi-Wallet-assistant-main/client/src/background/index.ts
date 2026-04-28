/**
 * Chrome Extension — Background Service Worker
 *
 * Runs in the background as a Manifest V3 service worker.
 * Handles alarms, message routing, and long-lived state via chrome.storage.
 */

// ── Lifecycle ────────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === chrome.runtime.OnInstalledReason.INSTALL) {
    console.log("[background] Extension installed");
    // Open side panel by default on action click
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  }
});

// ── Alarms ───────────────────────────────────────────────────────────────────

chrome.alarms.onAlarm.addListener((alarm) => {
  console.log(`[background] Alarm fired: ${alarm.name}`);
  // TODO: handle scheduled tasks (e.g. price polling)
});

// ── Message routing ──────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  console.log("[background] Message received:", message);

  switch (message.type) {
    case "PING":
      sendResponse({ type: "PONG", timestamp: Date.now() });
      break;
    default:
      sendResponse({ error: `Unknown message type: ${message.type}` });
  }

  // Return true to keep the message channel open for async responses
  return true;
});
