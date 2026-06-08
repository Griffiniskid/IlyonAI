// Force dynamic rendering so the HTML is never statically cached (s-maxage=1y).
// Static caching pinned an old HTML→CSS-hash mapping in browsers/CDN, so layout
// fixes never reached users until the year-long cache expired. no-store fixes it.
export const dynamic = "force-dynamic";

export default function AgentChatPage() {
  return null;
}
