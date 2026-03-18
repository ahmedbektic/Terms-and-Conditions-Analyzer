import { analyzeExtractedTerms } from "./lib/apiClient";
import {
  DEFAULT_API_BASE_URL,
  DEFAULT_EXTRACTION_MIN_LENGTH,
  STORAGE_KEY_API_BASE_URL,
  STORAGE_KEY_EXTRACTION_MIN_LENGTH,
} from "./lib/config";
import { type PopupToBackgroundResponse } from "./lib/contract";
import { createChromeBackgroundRuntimeGateway } from "./lib/background/chromeRuntimeGateway";
import { createBackgroundAuthSessionStore } from "./lib/background/authSessionStore";
import { createBackgroundRequestDispatcher } from "./lib/background/orchestrator";
import { createExtensionRuntimeAuthClient } from "./lib/runtimeAuthClient";

// Service worker entrypoint:
// wires runtime dependencies and delegates all decision flow to orchestrator.

const backgroundRuntime = createBackgroundRuntime();

// Trigger startup hydration eagerly so the first popup request sees a stable
// background-owned auth snapshot instead of racing initial storage reads.
void backgroundRuntime.authSessionStore.hydrate();

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
  sendResponse(await backgroundRuntime.dispatchPopupRequest(request));
}

/**
 * Runtime wiring stays in one function so startup dependencies are easier to
 * audit and extend without leaking orchestration concerns into entrypoint code.
 */
function createBackgroundRuntime(): {
  authSessionStore: ReturnType<typeof createBackgroundAuthSessionStore>;
  dispatchPopupRequest: ReturnType<typeof createBackgroundRequestDispatcher>;
} {
  // Background owns auth/session state reads so popup/content never become
  // token authorities. This keeps bearer-token handling in one runtime boundary.
  const authClient = createExtensionRuntimeAuthClient();
  const authSessionStore = createBackgroundAuthSessionStore(authClient);
  const chromeGateway = createChromeBackgroundRuntimeGateway({
    defaultApiBaseUrl: DEFAULT_API_BASE_URL,
    apiBaseUrlStorageKey: STORAGE_KEY_API_BASE_URL,
    extractionMinLengthStorageKey: STORAGE_KEY_EXTRACTION_MIN_LENGTH,
  });

  const dispatchPopupRequest = createBackgroundRequestDispatcher({
    authSessionStore,
    extractionMinLength: DEFAULT_EXTRACTION_MIN_LENGTH,
    getActiveTab: chromeGateway.getActiveTab,
    getApiBaseUrl: chromeGateway.getApiBaseUrl,
    requestExtractionFromTab: chromeGateway.requestExtractionFromTab,
    analyzeExtractedTerms,
  });

  return {
    authSessionStore,
    dispatchPopupRequest,
  };
}
