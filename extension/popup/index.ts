// extension/popup/index.ts
// Refactor the script to use the hidden class for UI states and reduce indirection.

import { ExtensionMessage, AuthStatePayload, ExtensionMessagePayload } from "../lib/contract";

// @ts-ignore
const chrome: any = globalThis.chrome as any;

const statusEl = document.getElementById("status") as HTMLElement;
const loginBtn = document.getElementById("loginBtn") as HTMLButtonElement;
const analyzeBtn = document.getElementById("analyzeBtn") as HTMLButtonElement;
const output = document.getElementById("output") as HTMLPreElement;

function setStatus(msg: string) {
  statusEl.textContent = msg;
}

// --- 1. Initial auth check on popup load ---------------------------------
chrome.runtime.sendMessage({ type: ExtensionMessage.GET_AUTH_STATE }, (auth: AuthStatePayload) => {
  if (auth.token) {
    setStatus("Signed in – ready to analyze.");
    analyzeBtn.classList.remove("hidden");
  } else {
    setStatus("Not signed in.");
    loginBtn.classList.remove("hidden");
  }
});

// --- 2. Sign‑in trigger ----------------------------------------------
loginBtn.addEventListener("click", () => {
  setStatus("Signing in…");
  chrome.runtime.sendMessage({ type: ExtensionMessage.SIGN_IN }, () => {
    setStatus("Login flow not yet implemented.");
  });
});

// --- 3. Analyze trigger -----------------------------------------------
analyzeBtn.addEventListener("click", async () => {
  setStatus("Extracting…");
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab || !tab.id) {
    setStatus("No active tab.");
    return;
  }

  // Ask content script for text.
  chrome.tabs.sendMessage(tab.id, { type: ExtensionMessage.EXTRACT_PAGE_TEXT });

  // Listener waits for content script → background → analysis reply.
  const listener = (msg: ExtensionMessagePayload) => {
    if (msg.type === ExtensionMessage.ANALYZE_TEXT) {
      const { text } = msg.payload as { text: string };
      // Background will handle analysis; forward text.
      chrome.runtime.sendMessage({ type: ExtensionMessage.ANALYZE_TEXT, payload: { text } }, (response: any) => {
        if (response && response.error) {
          setStatus(`Analysis error: ${response.error}`);
          output.textContent = '';
          return;
        }
        setStatus("Done.");
        output.textContent = response?.summary ?? "No summary returned.";
      });
      chrome.runtime.onMessage.removeListener(listener);
    }
  };
  chrome.runtime.onMessage.addListener(listener);
});

