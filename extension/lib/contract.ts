// extension/lib/contract.ts
// Shared messaging contract used by popup, background, and content script.
// It defines all message types, payload shapes, and common error format.

/**
 * Message types used across the extension.
 * These names describe a *request* from one module to another.
 */
export enum ExtensionMessage {
  /**
   * Retrieve current authentication state.
   * Payload: none. Response: AuthStatePayload.
   */
  GET_AUTH_STATE = "GET_AUTH_STATE",

  /**
   * Request the background to start the sign‑in flow.
   * Payload: none. Response: { status: string }.
   */
  SIGN_IN = "SIGN_IN",

  /**
   * Request the background to sign out.
   * Payload: none. Response: { status: string }.
   */
  SIGN_OUT = "SIGN_OUT",

  /**
   * Command a content script to extract the visible page text.
   * Payload: none.
   */
  EXTRACT_PAGE_TEXT = "EXTRACT_PAGE_TEXT",

  /**
   * Send the extracted page text to the background for analysis.
   * Payload: AnalysisRequestPayload.
   */
  ANALYZE_TEXT = "ANALYZE_TEXT",
}

/**
 * Payload returned when asking for authentication state.
 */
export interface AuthStatePayload {
  /**
   * JWT token if the user is signed in, otherwise null.
   */
  token: string | null;
}

/**
 * Request shape sent to the background for analysis.
 */
export interface AnalysisRequestPayload {
  /**
   * Raw extracted page text.
   */
  text: string;
}

/**
 * Response shape returned by the backend after analysis.
 */
export interface AnalysisResponsePayload {
  /**
   * Summarized text.
   */
  summary: string;
  /**
   * Backend report ID.
   */
  reportId: string;
}

/**
 * Generic error shape used for any message failure.
 */
export interface ErrorPayload {
  /**
   * Human‑readable error message.
   */
  error: string;
}

/**
 * Generic message structure used in Chrome runtime messaging.
 */
export interface ExtensionMessagePayload<T = unknown> {
  type: ExtensionMessage;
  payload?: T;
}
