import type { AnalyzeExtractedTerms } from "../apiClient";
import type { BackgroundAuthSessionStore } from "./authSessionStore";
import type { AuthenticatedSession } from "../../../frontend/src/lib/auth/contracts";
import {
  type AnalyzeResultPayload,
  type AuthAction,
  type AuthActionResultPayload,
  type ContentToBackgroundResponse,
  errorResponse,
  type ExtractedTermsPayload,
  isExtractionResultMessage,
  isPopupToBackgroundMessage,
  type PopupToBackgroundMessage,
  type PopupToBackgroundResponse,
} from "../contract";

/**
 * Background orchestration core for SCRUM-9.
 *
 * This module contains decision flow only:
 * - validate popup protocol
 * - coordinate auth actions and session-aware analysis
 * - map failures to typed error envelopes
 *
 * Direct Chrome API calls are intentionally injected from a runtime gateway.
 */
export interface BackgroundOrchestratorDependencies {
  authSessionStore: BackgroundAuthSessionStore;
  extractionMinLength: number;
  getActiveTab: () => Promise<chrome.tabs.Tab>;
  getApiBaseUrl: () => Promise<string>;
  requestExtractionFromTab: (
    tabId: number,
    minLength: number,
  ) => Promise<ContentToBackgroundResponse | undefined>;
  analyzeExtractedTerms: AnalyzeExtractedTerms;
}

/**
 * Creates the single popup-request dispatcher used by background runtime.
 *
 * Dependency injection keeps Chrome runtime APIs and transport adapters outside
 * the core flow logic, which makes boundaries explicit and future refactors
 * safer (for example, adding new analysis sources beyond active-tab extraction).
 */
export function createBackgroundRequestDispatcher(
  deps: BackgroundOrchestratorDependencies,
): (request: unknown) => Promise<PopupToBackgroundResponse> {
  return async (request: unknown) => {
    if (!isPopupToBackgroundMessage(request)) {
      return errorResponse("protocol", "Invalid popup request payload.");
    }

    try {
      switch (request.type) {
        case "auth.state.request":
          return {
            ok: true,
            type: "auth.state.result",
            payload: await deps.authSessionStore.getAuthStatePayload(),
          };
        case "auth.action.request":
          return {
            ok: true,
            type: "auth.action.result",
            payload: await runAuthAction(deps.authSessionStore, request.payload.action),
          };
        case "analysis.request":
          return {
            ok: true,
            type: "analysis.result",
            payload: await analyzeActiveTab(deps),
          };
        default:
          return errorResponse("protocol", "Unsupported popup request type.");
      }
    } catch (error) {
      return errorResponse(inferErrorArea(request.type), toErrorMessage(error));
    }
  };
}

async function runAuthAction(
  authSessionStore: BackgroundAuthSessionStore,
  action: AuthAction,
): Promise<AuthActionResultPayload> {
  return {
    action,
    authState: await authSessionStore.runAuthAction(action),
  };
}

async function analyzeActiveTab(
  deps: BackgroundOrchestratorDependencies,
): Promise<AnalyzeResultPayload> {
  const activeTab = await deps.getActiveTab();
  if (!activeTab.id) {
    throw new Error("No active tab is available.");
  }

  const extracted = await extractTermsForAnalysis(
    deps.requestExtractionFromTab,
    activeTab.id,
    deps.extractionMinLength,
  );

  if (!extracted.terms_text.trim()) {
    throw new Error("No extractable terms text was found on the active page.");
  }

  const session = await requireAuthenticatedSession(deps.authSessionStore);

  const report = await deps.analyzeExtractedTerms({
    baseUrl: await deps.getApiBaseUrl(),
    session,
    extracted,
  });

  return {
    report_id: report.id,
    summary: report.summary,
  };
}

async function extractTermsForAnalysis(
  requestExtractionFromTab: BackgroundOrchestratorDependencies["requestExtractionFromTab"],
  tabId: number,
  minLength: number,
): Promise<ExtractedTermsPayload> {
  // The content script may fail independently; keep the failure surface explicit
  // here so popup gets one consistent error envelope from background.
  const response = await requestExtractionFromTab(tabId, minLength);
  if (!response) {
    throw new Error("Content script did not return an extraction response.");
  }
  if (!response.ok) {
    throw new Error(`[${response.payload.area}] ${response.payload.message}`);
  }
  if (!isExtractionResultMessage(response)) {
    throw new Error("Content script returned an unexpected message type.");
  }
  return response.payload;
}

function inferErrorArea(
  requestType: PopupToBackgroundMessage["type"],
): "auth" | "analysis" | "protocol" {
  if (requestType === "auth.state.request" || requestType === "auth.action.request") {
    return "auth";
  }
  if (requestType === "analysis.request") {
    return "analysis";
  }
  return "protocol";
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown extension runtime error.";
}

async function requireAuthenticatedSession(
  authSessionStore: BackgroundAuthSessionStore,
): Promise<AuthenticatedSession> {
  const session = await authSessionStore.getSession();
  if (!session?.accessToken) {
    throw new Error("You are not signed in yet. Use extension login before running analysis.");
  }
  return session;
}
