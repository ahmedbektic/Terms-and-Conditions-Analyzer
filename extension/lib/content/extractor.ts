import { DEFAULT_EXTRACTION_MIN_LENGTH } from "../config";
import type { ExtractedTermsPayload } from "../contract";

/**
 * Extraction-only content helpers for the content-script boundary.
 *
 * Responsibilities:
 * - identify likely terms/policy containers in the current DOM
 * - remove obvious page-chrome noise from candidates
 * - normalize extracted text into stable plain text payloads
 *
 * Non-responsibilities:
 * - auth/session logic
 * - backend/network calls
 * - summarization or analysis orchestration
 */

const POLICY_HINT_SELECTORS = [
  '[id*="terms" i], [class*="terms" i], [data-testid*="terms" i]',
  '[id*="condition" i], [class*="condition" i], [data-testid*="condition" i]',
  '[id*="privacy" i], [class*="privacy" i], [data-testid*="privacy" i]',
  '[id*="policy" i], [class*="policy" i], [data-testid*="policy" i]',
  '[id*="legal" i], [class*="legal" i], [data-testid*="legal" i]',
  '[id*="agreement" i], [class*="agreement" i], [data-testid*="agreement" i]',
  "article",
  "main",
];

const GENERIC_CONTENT_SELECTORS = [
  '[role="main"]',
  ".content",
  ".article",
  ".post",
  "section",
];

const NOISE_SELECTORS = [
  "script",
  "style",
  "noscript",
  "svg",
  "canvas",
  "form",
  "button",
  "input",
  "textarea",
  "select",
  "nav",
  "header",
  "footer",
  "aside",
  '[role="navigation"]',
  '[aria-hidden="true"]',
  ".cookie-banner",
  ".newsletter",
  ".subscribe",
  ".social",
  ".breadcrumbs",
];

const POLICY_KEYWORDS = [
  "terms",
  "conditions",
  "agreement",
  "privacy",
  "policy",
  "arbitration",
  "liability",
  "termination",
  "governing law",
];

// Avoid scoring tiny heading-only matches as full extraction candidates.
const MIN_FOCUSED_CANDIDATE_LENGTH = 120;

/**
 * Pure extraction helper used by the content script message handler.
 * Keeping this logic separate makes future extraction improvements easier
 * without touching runtime messaging code.
 *
 * Extension points for future stories:
 * - per-domain selector packs
 * - de-duplication and boilerplate stripping
 * - confidence scoring emitted alongside extracted text
 */
export function extractTermsFromPage(options: {
  doc: Document;
  locationHref: string;
  title: string;
  minLength: number;
}): ExtractedTermsPayload {
  // Strategy:
  // 1) evaluate focused candidates from policy/generic containers
  // 2) choose best-scoring candidate that meets minLength
  // 3) fallback to noise-pruned body extraction when focused candidates are weak
  // 4) return empty terms_text when confidence is low (caller decides next step)
  const focusedCandidate = extractBestFocusedCandidate(options.doc, options.minLength);
  const bodyCandidate = extractFromBody(options.doc);

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

interface TextCandidate {
  text: string;
  score: number;
}

function extractBestFocusedCandidate(doc: Document, minLength: number): string {
  const candidates: TextCandidate[] = [];
  const seenNodes = new Set<Element>();
  const selectorSets = [POLICY_HINT_SELECTORS, GENERIC_CONTENT_SELECTORS];

  for (const selectors of selectorSets) {
    for (const selector of selectors) {
      const elements = doc.querySelectorAll(selector);
      // Use index-based iteration so this works when DOM iterable typings are absent.
      for (let index = 0; index < elements.length; index += 1) {
        const element = elements.item(index);
        if (!element || seenNodes.has(element)) {
          continue;
        }
        seenNodes.add(element);

        const candidateText = extractElementTextWithoutNoise(element);
        if (candidateText.length < MIN_FOCUSED_CANDIDATE_LENGTH) {
          continue;
        }

        candidates.push({
          text: candidateText,
          score: scoreCandidateText(candidateText),
        });
      }
    }
  }

  if (candidates.length === 0) {
    return "";
  }

  candidates.sort((left, right) => right.score - left.score);
  const bestCandidate = candidates[0];
  return bestCandidate.text.length >= minLength ? bestCandidate.text : "";
}

function extractFromBody(doc: Document): string {
  const body = doc.body;
  if (!body) {
    return "";
  }
  return extractElementTextWithoutNoise(body);
}

function extractElementTextWithoutNoise(element: Element): string {
  // Clone before pruning so extraction never mutates live page DOM.
  const clone = element.cloneNode(true);
  if (!(clone instanceof Element)) {
    return "";
  }

  for (const selector of NOISE_SELECTORS) {
    const noiseNodes = clone.querySelectorAll(selector);
    for (let index = 0; index < noiseNodes.length; index += 1) {
      const node = noiseNodes.item(index);
      if (node) {
        node.remove();
      }
    }
  }

  return normalizeExtractedText(clone.textContent ?? "");
}

function scoreCandidateText(value: string): number {
  const lowerValue = value.toLowerCase();
  let keywordHits = 0;

  for (const keyword of POLICY_KEYWORDS) {
    if (lowerValue.includes(keyword)) {
      keywordHits += 1;
    }
  }

  // Keep scoring simple and deterministic:
  // - reward longer, policy-keyword-rich text
  // - this remains easy to replace with richer extraction scoring later
  return value.length + keywordHits * 600;
}

function normalizeExtractedText(value: string): string {
  if (!value) {
    return "";
  }

  const normalizedSpacing = value.replace(/\u00A0/g, " ").replace(/\r/g, "\n");
  const normalizedLines = normalizedSpacing
    .split("\n")
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean);

  if (normalizedLines.length === 0) {
    return "";
  }

  const deduplicatedLines: string[] = [];
  for (const line of normalizedLines) {
    if (deduplicatedLines[deduplicatedLines.length - 1] === line) {
      continue;
    }
    deduplicatedLines.push(line);
  }

  return deduplicatedLines.join("\n");
}
