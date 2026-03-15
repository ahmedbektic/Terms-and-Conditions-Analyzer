import { analyzeExtractedTerms } from "./lib/apiClient";
import {
  DEFAULT_API_BASE_URL,
  DEFAULT_EXTRACTION_MIN_LENGTH,
  STORAGE_KEY_API_BASE_URL,
} from "./lib/config";
import { type PopupToBackgroundResponse } from "./lib/contract";
import { createChromeBackgroundRuntimeGateway } from "./lib/background/chromeRuntimeGateway";
import { createBackgroundRequestDispatcher } from "./lib/background/orchestrator";
import { createExtensionRuntimeAuthClient } from "./lib/runtimeAuthClient";

// Service worker entrypoint:
// wires runtime dependencies and delegates all decision flow to orchestrator.

// Background owns auth/session state reads so popup/content never become
// token authorities. This keeps bearer-token handling in one runtime boundary.
const authClient = createExtensionRuntimeAuthClient();
const chromeGateway = createChromeBackgroundRuntimeGateway({
  defaultApiBaseUrl: DEFAULT_API_BASE_URL,
  apiBaseUrlStorageKey: STORAGE_KEY_API_BASE_URL,
});
const dispatchPopupRequest = createBackgroundRequestDispatcher({
  authClient,
  extractionMinLength: DEFAULT_EXTRACTION_MIN_LENGTH,
  getActiveTab: chromeGateway.getActiveTab,
  getApiBaseUrl: chromeGateway.getApiBaseUrl,
  requestExtractionFromTab: chromeGateway.requestExtractionFromTab,
  analyzeExtractedTerms,
});

/**
 * Background is the only orchestration authority.
 * It receives popup requests, fetches extraction from content scripts, and
 * submits analysis to the shared dashboard API client seam.
 */
chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  void handleRuntimeMessage(request, sendResponse);
  return true;
});

async function handleRuntimeMessage(
  request: unknown,
  sendResponse: (response: PopupToBackgroundResponse) => void,
): Promise<void> {
  sendResponse(await dispatchPopupRequest(request));
}
