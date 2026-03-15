import type {
  AnalyzeResultPayload,
  AuthActionResultPayload,
  AuthStatePayload,
} from "../lib/contract";
import { requestBackgroundExpected } from "../lib/popup/backgroundClient";

// Popup module stays intentionally thin:
// - render state
// - capture user intents
// - delegate all auth/extraction/analysis work to background

const statusEl = getRequiredElement<HTMLElement>("status");
const loginBtn = getRequiredElement<HTMLButtonElement>("loginBtn");
const analyzeBtn = getRequiredElement<HTMLButtonElement>("analyzeBtn");
const outputEl = getRequiredElement<HTMLPreElement>("output");

void bootstrapPopup();

async function bootstrapPopup(): Promise<void> {
  wireUserActions();
  await refreshAuthState();
}

function wireUserActions(): void {
  loginBtn.addEventListener("click", async () => {
    await runUiTask({
      loadingMessage: "Starting sign-in...",
      onRun: async () => {
        const result = await requestBackgroundExpected<"auth.action.result">(
          {
            type: "auth.action.request",
            payload: { action: "sign_in_google" },
          },
          "auth.action.result",
        );
        applyAuthActionResult(result.payload);
      },
    });
  });

  analyzeBtn.addEventListener("click", async () => {
    await runUiTask({
      loadingMessage: "Analyzing active tab...",
      clearOutput: true,
      onRun: async () => {
        const result = await requestBackgroundExpected<"analysis.result">(
          {
            type: "analysis.request",
            payload: { target: "active_tab" },
          },
          "analysis.result",
        );
        applyAnalysisResult(result.payload);
      },
    });
  });
}

/**
 * Popup does not own auth/session state. It always asks background for the
 * current auth state so there is one runtime authority.
 */
async function refreshAuthState(): Promise<void> {
  await runUiTask({
    loadingMessage: "Loading session...",
    onRun: async () => {
      const result = await requestBackgroundExpected<"auth.state.result">(
        { type: "auth.state.request" },
        "auth.state.result",
      );
      applyAuthState(result.payload);
    },
  });
}

/**
 * Centralized UI transition helper:
 * - sets loading UI
 * - executes one background request flow
 * - routes any protocol/runtime failures to one error rendering path
 */
async function runUiTask(options: {
  loadingMessage: string;
  clearOutput?: boolean;
  onRun: () => Promise<void>;
}): Promise<void> {
  setBusy(true, options.loadingMessage);
  if (options.clearOutput) {
    outputEl.textContent = "";
  }

  try {
    await options.onRun();
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unexpected popup error.";
    setStatus(message);
  } finally {
    setBusy(false);
  }
}

function applyAuthActionResult(result: AuthActionResultPayload): void {
  // Background returns refreshed auth state after actions.
  // Rendering that state here keeps popup messaging and UI consistent.
  applyAuthState(result.authState);
}

function applyAnalysisResult(payload: AnalyzeResultPayload): void {
  setStatus("Analysis complete.");
  outputEl.textContent = payload.summary || "No summary was returned.";
}

/**
 * UI transitions are derived directly from background auth payload so popup
 * never becomes the source of truth for session state.
 */
function applyAuthState(payload: AuthStatePayload): void {
  setStatus(payload.message);
  if (payload.authenticated) {
    loginBtn.classList.add("hidden");
    analyzeBtn.classList.remove("hidden");
    return;
  }
  loginBtn.classList.remove("hidden");
  analyzeBtn.classList.add("hidden");
}

function setBusy(isBusy: boolean, loadingMessage?: string): void {
  loginBtn.disabled = isBusy;
  analyzeBtn.disabled = isBusy;
  if (isBusy && loadingMessage) {
    setStatus(loadingMessage);
  }
}

function setStatus(message: string): void {
  statusEl.textContent = message;
}

function getRequiredElement<TElement extends HTMLElement>(id: string): TElement {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Popup template is missing required element: #${id}`);
  }
  return element as TElement;
}
