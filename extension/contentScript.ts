import {
  type ExtractionRequestMessage,
  type ContentToBackgroundResponse,
  errorResponse,
  isExtractionRequestMessage,
} from "./lib/contract";
import { extractTermsFromPage, resolveExtractionMinLength } from "./lib/content/extractor";

// Content-script entrypoint for extraction requests from background only.

/**
 * Content script is extraction-only by contract:
 * - accepts extraction requests from background
 * - returns extracted text payload
 * - does not perform auth, backend calls, or UI rendering
 */
chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (!isExtractionRequestMessage(request)) {
    return false;
  }

  sendResponse(buildExtractionResponse(request));

  return true;
});

function buildExtractionResponse(request: ExtractionRequestMessage): ContentToBackgroundResponse {
  try {
    // Caller can tune threshold per request; we keep a safe default fallback
    // when the field is absent or invalid.
    const minLength = resolveExtractionMinLength(request.payload?.min_length);
    const extracted = extractTermsFromPage({
      doc: document,
      locationHref: window.location.href,
      title: document.title,
      minLength,
    });

    return {
      ok: true,
      type: "extraction.result",
      payload: extracted,
    };
  } catch (error) {
    return errorResponse(
      "extraction",
      error instanceof Error ? error.message : "Terms extraction failed in content script.",
    );
  }
}
