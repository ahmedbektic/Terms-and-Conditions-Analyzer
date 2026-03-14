// extension/contentScript.ts
// Content script – extracts Terms & Conditions / Privacy Policy style text.
// It replies via the ExtensionMessage protocol with a structured payload.
// No auth, no network, no rendering. Pure extraction layer.

import { ExtensionMessage, AnalysisRequestPayload, ExtensionMessagePayload } from "./lib/contract";

// @ts-ignore
const chrome: any = globalThis.chrome as any;

/**
 * Heuristic extraction strategy.
 * 1. Try to find obvious policy anchors: elements containing "terms", "privacy", "policy" in their class, id, or tag name.
 * 2. If no anchors, fall back to the body’s text content.
 * 3. Trim and collapse whitespace; reject results shorter than 200 characters as likely not a policy.
 */
function extractPolicyText(): AnalysisRequestPayload {
  // 1. Search for elements with policy‑related attributes or tags.
  const selectors = [
    '[id*="terms"], [class*="terms"]',
    '[id*="privacy"], [class*="privacy"]',
    '[id*="policy"], [class*="policy"]',
    'article, section, div[data-policy="true"]'
  ];

  let candidateText = "";
  for (const selector of selectors) {
    const el = document.querySelector(selector);
    if (el) {
      candidateText = (el.textContent ?? "").trim();
      if (candidateText.length >= 200) break;
    }
  }

  // 2. Fallback to body if not found or too short.
  if (!candidateText || candidateText.length < 200) {
    candidateText = document.body.innerText.replace(/\s+/g, " ")?.trim() ?? "";
  }

  // 3. Final fallback: if still short, set empty.
  if (!candidateText || candidateText.length < 200) {
    candidateText = "";
  }

  return { text: candidateText };
}

chrome.runtime.onMessage.addListener((request: ExtensionMessagePayload) => {
  if (request.type === ExtensionMessage.EXTRACT_PAGE_TEXT) {
    const payload = extractPolicyText();
    chrome.runtime.sendMessage({ type: ExtensionMessage.ANALYZE_TEXT, payload });
  }
});

