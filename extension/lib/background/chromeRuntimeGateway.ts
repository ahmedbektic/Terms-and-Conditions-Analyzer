import type {
  BackgroundToContentMessage,
  ContentToBackgroundResponse,
} from "../contract";
import { normalizeApiBaseUrl } from "../config";

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
  extractionMinLengthStorageKey?: string;
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
    const resolvedMinLength = await resolveExtractionMinLengthOverride(minLength);
    const extractionRequest: BackgroundToContentMessage = {
      type: "extraction.request",
      payload: {
        min_length: resolvedMinLength,
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
    const storedValue = stored[options.apiBaseUrlStorageKey];
    if (typeof storedValue !== "string") {
      return options.defaultApiBaseUrl;
    }
    return normalizeApiBaseUrl(storedValue) ?? options.defaultApiBaseUrl;
  }

  async function resolveExtractionMinLengthOverride(defaultValue: number): Promise<number> {
    const storageKey = options.extractionMinLengthStorageKey;
    if (!storageKey) {
      return defaultValue;
    }

    const stored = await chrome.storage.local.get(storageKey);
    const storedValue = stored[storageKey];
    const normalized = parsePositiveInteger(storedValue);
    if (normalized === null) {
      return defaultValue;
    }

    // Keep a practical ceiling so accidental huge values do not make extraction
    // appear permanently broken on normal policy pages.
    return Math.min(normalized, 10000);
  }
}

function parsePositiveInteger(value: unknown): number | null {
  const numericValue =
    typeof value === "number"
      ? value
      : typeof value === "string"
        ? Number(value)
        : Number.NaN;

  if (!Number.isFinite(numericValue)) {
    return null;
  }

  const integer = Math.floor(numericValue);
  return integer > 0 ? integer : null;
}
