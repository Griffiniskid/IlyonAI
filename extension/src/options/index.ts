const textarea = document.getElementById("hosts") as HTMLTextAreaElement;
const saveBtn = document.getElementById("save") as HTMLButtonElement;

const defaults = "dexscreener.com\ngeckoterminal.com\ndefillama.com\napp.uniswap.org\nraydium.io";

chrome.storage.local.get("allowed_hosts", (r) => {
  textarea.value = r.allowed_hosts || defaults;
});

saveBtn.onclick = () => {
  chrome.storage.local.set({ allowed_hosts: textarea.value });
  saveBtn.textContent = "Saved!";
  setTimeout(() => { saveBtn.textContent = "Save"; }, 1500);
};
