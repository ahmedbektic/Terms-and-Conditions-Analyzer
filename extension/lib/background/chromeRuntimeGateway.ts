import type {
  BackgroundToContentMessage,
  ContentToBackgroundResponse,
} from "../contract";

// Chrome runtime adapter used by the background orchestrator.
// Keeping this separate avoids scattering direct `chrome.*` calls in flow code.

export interface ChromeBackgroundRuntimeGateway {
  getActiveTab: () => Promise<chrome.tabs.Tab>;
  requestExtractionFromTab: (
    tabId: number,
    minLength: number,
  ) => Promise<ContentToBackgroundResponse | undefined>;
  getApiBaseUrl: () => Promise<string>;
}

export interface ChromeBackgroundRuntimeGatewayOptions {
  defaultApiBaseUrl: string;
  apiBaseUrlStorageKey: string;
}

/**
 * Isolates direct Chrome extension APIs behind a small gateway so background
 * orchestration can stay focused on flow decisions, not runtime plumbing.
 */
export function createChromeBackgroundRuntimeGateway(
  options: ChromeBackgroundRuntimeGatewayOptions,
): ChromeBackgroundRuntimeGateway {
  return {
    getActiveTab,
    requestExtractionFromTab,
    getApiBaseUrl,
  };

  async function getActiveTab(): Promise<chrome.tabs.Tab> {
    const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    const tab = tabs[0];
    if (!tab) {
      throw new Error("No active browser tab was found.");
    }
    return tab;
  }

  async function requestExtractionFromTab(
    tabId: number,
    minLength: number,
  ): Promise<ContentToBackgroundResponse | undefined> {
    const extractionRequest: BackgroundToContentMessage = {
      type: "extraction.request",
      payload: {
        min_length: minLength,
      },
    };

    return (await chrome.tabs.sendMessage(
      tabId,
      extractionRequest,
    )) as ContentToBackgroundResponse | undefined;
  }

  async function getApiBaseUrl(): Promise<string> {
    // Local override enables extension-only environment switching without
    // forking backend contracts or request payloads.
    const stored = await chrome.storage.local.get(options.apiBaseUrlStorageKey);
    const value = stored[options.apiBaseUrlStorageKey];
    if (typeof value !== "string") {
      return options.defaultApiBaseUrl;
    }
    const baseUrl = value.trim();
    return baseUrl || options.defaultApiBaseUrl;
  }
}
