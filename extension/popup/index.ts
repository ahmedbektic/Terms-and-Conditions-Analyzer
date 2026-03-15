import type {
  AnalyzeResultPayload,
  AuthAction,
  AuthActionResultPayload,
  AuthStatePayload,
} from "../lib/contract";
import { requestBackgroundExpected } from "../lib/popup/backgroundClient";

// Popup module stays intentionally thin:
// - render state
// - capture user intents
// - delegate all auth/extraction/analysis work to background

const statusEl = getRequiredElement<HTMLElement>("status");
const hintEl = document.getElementById("hint") as HTMLElement | null;
const loginBtn = getRequiredElement<HTMLButtonElement>("loginBtn");
const logoutBtn = getRequiredElement<HTMLButtonElement>("logoutBtn");
const analyzeBtn = getRequiredElement<HTMLButtonElement>("analyzeBtn");
const outputEl = getRequiredElement<HTMLPreElement>("output");

const STATUS_MESSAGES = {
  loadingSession: "Loading session...",
  startingSignIn: "Starting sign-in...",
  signingOut: "Signing out...",
  analyzingActiveTab: "Analyzing active tab...",
  analysisComplete: "Analysis complete.",
  unexpectedPopupError: "Unexpected popup error.",
} as const;

const ERROR_HINT_RULES: ReadonlyArray<{ includes: string; hint: string }> = [
  {
    includes: "Extension auth is not configured",
    hint: "Set EXTENSION_SUPABASE_URL / EXTENSION_SUPABASE_ANON_KEY and rebuild, or set auth_supabase_url/auth_supabase_anon_key runtime overrides.",
  },
  {
    includes: "Failed to fetch",
    hint: "Check api_base_url runtime override, backend availability, and extension host/CORS config.",
  },
  {
    includes: "No extractable terms text was found",
    hint: "Try a page with visible policy text, or lower extraction_min_length in chrome.storage.local for local testing.",
  },
];

type PopupViewState =
  | "initializing"
  | "unauthenticated"
  | "authenticating"
  | "analysis_ready"
  | "analyzing";

let lastKnownAuthState: AuthStatePayload = {
  authenticated: false,
  accessTokenPresent: false,
  message: "Not signed in.",
};

void bootstrapPopup();

async function bootstrapPopup(): Promise<void> {
  wireUserActions();
  await refreshAuthState();
}

function wireUserActions(): void {
  loginBtn.addEventListener("click", async () => {
    await runAuthAction("sign_in_google", STATUS_MESSAGES.startingSignIn);
  });

  logoutBtn.addEventListener("click", async () => {
    await runAuthAction("sign_out", STATUS_MESSAGES.signingOut);
  });

  analyzeBtn.addEventListener("click", async () => {
    await runAnalysis();
  });
}

/**
 * Popup does not own auth/session state. It always asks background for the
 * current auth state so there is one runtime authority.
 */
async function refreshAuthState(): Promise<void> {
  setViewState("initializing", STATUS_MESSAGES.loadingSession);
  try {
    const result = await requestBackgroundExpected<"auth.state.result">(
      { type: "auth.state.request" },
      "auth.state.result",
    );
    applyAuthState(result.payload);
  } catch (error) {
    const message = toErrorMessage(error);
    setViewState("unauthenticated", message, { isError: true });
  }
}

/**
 * Popup sends intents only; background remains auth/session authority.
 * This wrapper keeps auth-action UI transitions explicit and minimal.
 */
async function runAuthAction(action: AuthAction, loadingMessage: string): Promise<void> {
  setViewState("authenticating", loadingMessage);
  try {
    const result = await requestBackgroundExpected<"auth.action.result">(
      {
        type: "auth.action.request",
        payload: { action },
      },
      "auth.action.result",
    );
    applyAuthActionResult(result.payload);
  } catch (error) {
    const message = toErrorMessage(error);
    applyAuthError(message);
  }
}

function applyAuthActionResult(result: AuthActionResultPayload): void {
  // Background returns refreshed auth state after actions.
  // Rendering that state here keeps popup messaging and UI consistent.
  applyAuthState(result.authState);
}

function applyAuthError(message: string): void {
  // Keep control visibility aligned with the last known authoritative auth
  // payload from background, while still surfacing current action failure.
  const fallbackState = deriveFallbackViewStateFromAuth();
  setViewState(fallbackState, message, { isError: true });
}

async function runAnalysis(): Promise<void> {
  setViewState("analyzing", STATUS_MESSAGES.analyzingActiveTab, { clearOutput: true });
  try {
    const result = await requestBackgroundExpected<"analysis.result">(
      {
        type: "analysis.request",
        payload: { target: "active_tab" },
      },
      "analysis.result",
    );
    applyAnalysisResult(result.payload);
  } catch (error) {
    const message = toErrorMessage(error);
    const fallbackState = deriveFallbackViewStateFromAuth();
    setViewState(fallbackState, message, { isError: true });
  }
}

function applyAnalysisResult(payload: AnalyzeResultPayload): void {
  setViewState("analysis_ready", STATUS_MESSAGES.analysisComplete);
  outputEl.textContent = payload.summary || "No summary was returned.";
}

/**
 * UI transitions are derived directly from background auth payload so popup
 * never becomes the source of truth for session state.
 */
function applyAuthState(payload: AuthStatePayload): void {
  lastKnownAuthState = payload;
  const nextState: PopupViewState = payload.authenticated ? "analysis_ready" : "unauthenticated";
  setViewState(nextState, payload.message);
}

function setViewState(
  state: PopupViewState,
  statusMessage: string,
  options: {
    clearOutput?: boolean;
    isError?: boolean;
  } = {},
): void {
  const shouldClearOutput =
    Boolean(options.clearOutput) ||
    state === "initializing" ||
    state === "unauthenticated" ||
    state === "authenticating";

  if (shouldClearOutput) {
    outputEl.textContent = "";
  }
  renderStatus(statusMessage, Boolean(options.isError));
  renderHint(statusMessage, Boolean(options.isError));
  renderControls(state);
}

function renderStatus(message: string, isError: boolean): void {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function renderHint(statusMessage: string, isError: boolean): void {
  if (!hintEl) {
    return;
  }

  const hint = inferHint(statusMessage, isError);
  hintEl.textContent = hint ?? "";
  hintEl.classList.toggle("hidden", !hint);
}

function renderControls(state: PopupViewState): void {
  const isAuthenticated = state === "analysis_ready" || state === "analyzing";
  const isAuthInFlight = state === "initializing" || state === "authenticating";
  const isAnalysisInFlight = state === "analyzing";

  loginBtn.classList.toggle("hidden", isAuthenticated);
  logoutBtn.classList.toggle("hidden", !isAuthenticated);
  analyzeBtn.classList.toggle("hidden", !isAuthenticated);

  loginBtn.disabled = isAuthInFlight || isAnalysisInFlight;
  logoutBtn.disabled = isAuthInFlight || isAnalysisInFlight;
  analyzeBtn.disabled = isAuthInFlight || isAnalysisInFlight;
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : STATUS_MESSAGES.unexpectedPopupError;
}

/**
 * Keeps popup UX lightweight while still surfacing next-step guidance
 * for common local runtime issues (config, extraction threshold, CORS/network).
 */
function inferHint(statusMessage: string, isError: boolean): string | null {
  if (!isError) {
    return null;
  }

  for (const rule of ERROR_HINT_RULES) {
    if (statusMessage.includes(rule.includes)) {
      return rule.hint;
    }
  }

  return null;
}

function deriveFallbackViewStateFromAuth(): PopupViewState {
  return lastKnownAuthState.authenticated ? "analysis_ready" : "unauthenticated";
}

function getRequiredElement<TElement extends HTMLElement>(id: string): TElement {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Popup template is missing required element: #${id}`);
  }
  return element as TElement;
}
