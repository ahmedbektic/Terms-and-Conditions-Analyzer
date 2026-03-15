import { DEFAULT_EXTRACTION_MIN_LENGTH } from "../config";
import type { ExtractedTermsPayload } from "../contract";

// Pure extraction utilities used by the content-script runtime endpoint.

const POLICY_SELECTORS = [
  '[id*="terms"], [class*="terms"]',
  '[id*="privacy"], [class*="privacy"]',
  '[id*="policy"], [class*="policy"]',
  "article",
  "main",
  "section",
];

/**
 * Pure extraction helper used by the content script message handler.
 * Keeping this logic separate makes future extraction improvements easier
 * without touching runtime messaging code.
 */
export function extractTermsFromPage(options: {
  doc: Document;
  locationHref: string;
  title: string;
  minLength: number;
}): ExtractedTermsPayload {
  // Strategy:
  // 1) prefer policy-like containers to reduce unrelated page chrome/noise
  // 2) fallback to full body text when focused containers are too short
  // 3) return empty terms_text when confidence is low (caller decides next step)
  const focusedCandidate = extractFromPolicySelectors(options.doc, options.minLength);
  const bodyCandidate = normalizeWhitespace(options.doc.body?.innerText ?? "");

  const bestText =
    focusedCandidate.length >= options.minLength
      ? focusedCandidate
      : bodyCandidate.length >= options.minLength
        ? bodyCandidate
        : "";

  return {
    terms_text: bestText,
    source_url: options.locationHref || null,
    title: options.title || null,
  };
}

export function resolveExtractionMinLength(requestedMinLength: number | undefined): number {
  if (typeof requestedMinLength !== "number" || requestedMinLength <= 0) {
    return DEFAULT_EXTRACTION_MIN_LENGTH;
  }
  return requestedMinLength;
}

function extractFromPolicySelectors(doc: Document, minLength: number): string {
  // Selector order is intentional: policy-specific matches before generic containers.
  for (const selector of POLICY_SELECTORS) {
    const element = doc.querySelector(selector);
    if (!element) {
      continue;
    }
    const candidate = normalizeWhitespace(element.textContent ?? "");
    if (candidate.length >= minLength) {
      return candidate;
    }
  }
  return "";
}

function normalizeWhitespace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}
