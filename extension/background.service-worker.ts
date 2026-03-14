// extension/background.service-worker.ts
// Background service worker – sole authority for auth, session, and API communication.
// It hosts a Supabase client and orchestrates all requests from the popup/content script.
//
// Architecture overview:
//   • Auth logic (token, Supabase client) is encapsulated in this file only.
//   • The API client is imported and used in an async `handleAnalysis` helper.
//   • All message handling is routed through a single `onMessage` function.
//   • State changes (token) are propagated to all listeners via the built‑in `chrome.runtime.onMessage` system.
//
// Future enhancements could extract a dedicated AuthManager or ApiRouter, but for now
// keeping everything in a single concise file keeps the extension small.

import { ExtensionMessage, AuthStatePayload, AnalysisRequestPayload, ErrorPayload, ExtensionMessagePayload } from "./lib/contract";
import { createClient as createApiClient, BackendApiConfig } from "./lib/apiClient";
import { createClient as createSupabaseClient, SupabaseClient } from "@supabase/supabase-js";

// @ts-ignore
const chrome: any = globalThis.chrome as any;

// Environment‑based configuration – values should be injected by the build system.
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const SUPABASE_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "https://api.yourdomain.com";

// Supabase client – instantiated once and shared within the worker.
const supabase: SupabaseClient = createSupabaseClient(SUPABASE_URL, SUPABASE_KEY);
const apiClient = createApiClient({ baseUrl: API_BASE_URL });

// Current JWT token for this user. Updated via auth state changes.
let currentToken: string | null = null;

// Helper to handle analysis request.
async function handleAnalysis(req: AnalysisRequestPayload): Promise<any> {
  if (!currentToken) {
    throw new Error("Unauthenticated: no token available");
  }
  return apiClient.analyze(req.text, currentToken);
}

// Listen for auth state changes and keep the token in sync.
supabase.auth.onAuthStateChange((_, session) => {
  currentToken = session?.access_token ?? null;
});

// Initialise token on first run.
(async () => {
  const { data: { session } } = await supabase.auth.getSession();
  currentToken = session?.access_token ?? null;
})();

// The message dispatcher.
chrome.runtime.onMessage.addListener((request: ExtensionMessagePayload, _sender, sendResponse) => {
  const { type, payload } = request;
  try {
    switch (type) {
      case ExtensionMessage.GET_AUTH_STATE:
        sendResponse({ token: currentToken });
        break;
      case ExtensionMessage.SIGN_IN:
        // TODO: trigger Supabase sign‑in via modal.
        sendResponse({ status: "unimplemented" });
        break;
      case ExtensionMessage.SIGN_OUT:
        supabase.auth.signOut();
        currentToken = null;
        sendResponse({ status: "logged_out" });
        break;
      case ExtensionMessage.ANALYZE_TEXT:
        const req = payload as AnalysisRequestPayload;
        handleAnalysis(req)
          .then((res) => sendResponse(res))
          .catch((err) => sendResponse({ error: err.message }));
        break;
      default:
        sendResponse({ error: `Unknown message type: ${type}` });
    }
  } catch (e: any) {
    sendResponse({ error: e.message ?? "Unknown error" });
  }
  return true;
});



// Initialise token on first run.
syncToken();

chrome.runtime.onMessage.addListener((request: ExtensionMessagePayload, sender, sendResponse) => {
  const { type, payload } = request;
  switch (type) {
    case ExtensionMessage.GET_AUTH_STATE:
      const auth: AuthStatePayload = { token: currentToken };
      sendResponse(auth);
      break;
    case ExtensionMessage.SIGN_IN:
      // TODO: Trigger real sign‑in flow. For now, just signal unimplemented.
      sendResponse({ status: "unimplemented" });
      break;
    case ExtensionMessage.SIGN_OUT:
      supabase.auth.signOut();
      currentToken = null;
      sendResponse({ status: "logged_out" });
      break;
    case ExtensionMessage.ANALYZE_TEXT:
      const req = payload as AnalysisRequestPayload;
      if (!currentToken) {
        sendResponse({ error: "Unauthenticated request" });
        break;
      }
      // Call the backend API via the pure client.
      apiClient.analyze(req.text, currentToken).then((res) => {
        sendResponse(res);
      }).catch((err) => {
        sendResponse({ error: err.message });
      });
      break;
    default:
      const err: ErrorPayload = { error: `Unknown message type: ${type}` };
      sendResponse(err);
  }
  // Indicate that we will reply asynchronously.
  return true;
});
