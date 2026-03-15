/**
 * Extension messaging protocol.
 *
 * Ownership rules:
 * - Popup is a thin UI surface and talks only to background.
 * - Content script is extraction-only and talks only to background.
 * - Background is the orchestration authority for auth, extraction routing,
 *   and backend analysis calls.
 */

export type ErrorArea = "auth" | "extraction" | "analysis" | "protocol";

export interface ErrorPayload {
  area: ErrorArea;
  message: string;
}

export interface ProtocolErrorResponse {
  ok: false;
  type: "error";
  payload: ErrorPayload;
}

export function errorResponse(
  area: ErrorArea,
  message: string,
): ProtocolErrorResponse {
  return {
    ok: false,
    type: "error",
    payload: { area, message },
  };
}

export interface AuthStatePayload {
  authenticated: boolean;
  accessTokenPresent: boolean;
  message: string;
}

export type AuthAction = "sign_in_google" | "sign_out";

export interface AuthActionResultPayload {
  action: AuthAction;
  authState: AuthStatePayload;
}

export interface ExtractedTermsPayload {
  terms_text: string;
  source_url: string | null;
  title: string | null;
}

export interface AnalyzeResultPayload {
  report_id: string;
  summary: string;
}

// Popup -> Background (auth state / auth actions / analysis trigger)
export interface AuthStateRequestMessage {
  type: "auth.state.request";
}

export interface AuthActionRequestMessage {
  type: "auth.action.request";
  payload: {
    action: AuthAction;
  };
}

export interface AnalysisRequestMessage {
  type: "analysis.request";
  payload: {
    target: "active_tab";
  };
}

export type PopupToBackgroundMessage =
  | AuthStateRequestMessage
  | AuthActionRequestMessage
  | AnalysisRequestMessage;

export interface AuthStateResultMessage {
  ok: true;
  type: "auth.state.result";
  payload: AuthStatePayload;
}

export interface AuthActionResultMessage {
  ok: true;
  type: "auth.action.result";
  payload: AuthActionResultPayload;
}

export interface AnalysisResultMessage {
  ok: true;
  type: "analysis.result";
  payload: AnalyzeResultPayload;
}

export type PopupToBackgroundResponse =
  | AuthStateResultMessage
  | AuthActionResultMessage
  | AnalysisResultMessage
  | ProtocolErrorResponse;

// Background -> Content (extraction only)
export interface ExtractionRequestMessage {
  type: "extraction.request";
  payload: {
    min_length: number;
  };
}

export type BackgroundToContentMessage = ExtractionRequestMessage;

export interface ExtractionResultMessage {
  ok: true;
  type: "extraction.result";
  payload: ExtractedTermsPayload;
}

export type ContentToBackgroundResponse =
  | ExtractionResultMessage
  | ProtocolErrorResponse;

/**
 * Runtime guards centralize protocol validation so each extension surface
 * (popup/background/content) does not drift on message-shape assumptions.
 * These are intentionally strict and validate both `type` and required payload
 * fields for accepted request messages.
 */
export function isPopupToBackgroundMessage(
  value: unknown,
): value is PopupToBackgroundMessage {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const message = value as {
    type?: unknown;
    payload?: { action?: unknown; target?: unknown };
  };

  if (message.type === "auth.state.request") {
    return true;
  }

  if (message.type === "auth.action.request") {
    return (
      message.payload?.action === "sign_in_google" ||
      message.payload?.action === "sign_out"
    );
  }

  if (message.type === "analysis.request") {
    return message.payload?.target === "active_tab";
  }

  return false;
}

export function isExtractionRequestMessage(
  value: unknown,
): value is ExtractionRequestMessage {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const message = value as { type?: unknown };
  return message.type === "extraction.request";
}

export function isExtractionResultMessage(
  value: ContentToBackgroundResponse,
): value is ExtractionResultMessage {
  return value.ok && value.type === "extraction.result";
}
