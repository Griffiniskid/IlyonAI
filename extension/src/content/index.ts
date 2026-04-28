// Floating button injected on allowed host patterns
const ALLOWED_PATTERNS = [
  "dexscreener.com",
  "geckoterminal.com",
  "defillama.com",
  "app.uniswap.org",
  "raydium.io",
];

const host = window.location.hostname;
const allowed = ALLOWED_PATTERNS.some(p => host.includes(p));

if (allowed) {
  const btn = document.createElement("div");
  btn.id = "ilyon-sentinel-btn";
  btn.innerHTML = "\u{1F6E1}️";
  Object.assign(btn.style, {
    position: "fixed", bottom: "20px", right: "20px", zIndex: "99999",
    width: "48px", height: "48px", borderRadius: "50%",
    background: "#1e40af", cursor: "pointer", display: "flex",
    alignItems: "center", justifyContent: "center", fontSize: "24px",
    boxShadow: "0 4px 12px rgba(0,0,0,0.3)", transition: "transform 0.2s",
  });
  btn.onmouseenter = () => { btn.style.transform = "scale(1.1)"; };
  btn.onmouseleave = () => { btn.style.transform = "scale(1)"; };
  btn.onclick = () => { chrome.sidePanel.open(); };
  document.body.appendChild(btn);
}
