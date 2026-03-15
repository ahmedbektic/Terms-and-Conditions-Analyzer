import type {
  AuthStateChangeReason,
  AuthenticatedSession,
} from "../../../frontend/src/lib/auth/contracts";
import type {
  PersistedSessionShape,
  SupabaseSignUpPayload,
  SupabaseTokenPayload,
} from "./types";

export function extractSignUpTokenPayload(
  payload: SupabaseSignUpPayload,
): SupabaseTokenPayload | null {
  if (payload.session && isTokenPayloadLike(payload.session)) {
    return payload.session;
  }
  if (isTokenPayloadLike(payload)) {
    return payload;
  }
  return null;
}

export function toAuthenticatedSessionFromTokenPayload(
  payload: SupabaseTokenPayload,
): AuthenticatedSession {
  const accessToken = payload.access_token.trim();
  if (!accessToken) {
    throw new Error("Supabase auth response did not include an access token.");
  }

  const claims = decodeJwtClaims(accessToken);
  const userId =
    readString(payload.user?.id) ||
    (typeof claims?.sub === "string" ? claims.sub.trim() : "");
  if (!userId) {
    throw new Error("Unable to resolve user id from auth token.");
  }

  const emailFromPayload = payload.user?.email;
  const emailFromClaims = typeof claims?.email === "string" ? claims.email : null;
  const expiresAt =
    payload.expires_at ??
    inferExpiresAtFromExpiresIn(payload.expires_in) ??
    parseNumericUnknown(claims?.exp);

  return {
    userId,
    accessToken,
    email: typeof emailFromPayload === "string" ? emailFromPayload : emailFromClaims,
    expiresAt,
  };
}

export function toAuthenticatedSession(value: unknown): AuthenticatedSession | null {
  if (!isPersistedSessionLike(value)) {
    return null;
  }
  return {
    userId: value.userId,
    accessToken: value.accessToken,
    email: value.email ?? null,
    expiresAt: value.expiresAt ?? null,
  };
}

export function inferChangeReason(
  previousSession: AuthenticatedSession | null,
  nextSession: AuthenticatedSession | null,
): AuthStateChangeReason {
  if (!previousSession && nextSession) {
    return "signed_in";
  }
  if (previousSession && !nextSession) {
    return "signed_out";
  }
  if (previousSession && nextSession) {
    if (previousSession.accessToken !== nextSession.accessToken) {
      return "token_refreshed";
    }
    return "user_updated";
  }
  return "unknown";
}

export function isExpired(expiresAt: number | null): boolean {
  if (typeof expiresAt !== "number") {
    return false;
  }
  return expiresAt <= Math.floor(Date.now() / 1000);
}

function isTokenPayloadLike(value: unknown): value is SupabaseTokenPayload {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const tokenPayload = value as { access_token?: unknown };
  return typeof tokenPayload.access_token === "string" && tokenPayload.access_token.trim().length > 0;
}

function decodeJwtClaims(accessToken: string): Record<string, unknown> | null {
  const tokenParts = accessToken.split(".");
  if (tokenParts.length !== 3) {
    return null;
  }

  const rawPayload = tokenParts[1];
  if (!rawPayload) {
    return null;
  }

  try {
    const padded = addBase64Padding(rawPayload.replace(/-/g, "+").replace(/_/g, "/"));
    const decoded = atob(padded);
    return JSON.parse(decoded) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function addBase64Padding(value: string): string {
  const remainder = value.length % 4;
  if (remainder === 0) {
    return value;
  }
  return `${value}${"=".repeat(4 - remainder)}`;
}

function inferExpiresAtFromExpiresIn(expiresIn: number | null | undefined): number | null {
  if (typeof expiresIn !== "number" || !Number.isFinite(expiresIn) || expiresIn <= 0) {
    return null;
  }
  return Math.floor(Date.now() / 1000) + Math.floor(expiresIn);
}

function parseNumericUnknown(rawValue: unknown): number | null {
  if (typeof rawValue !== "number" || !Number.isFinite(rawValue)) {
    return null;
  }
  return Math.floor(rawValue);
}

function isPersistedSessionLike(value: unknown): value is PersistedSessionShape {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const maybeSession = value as Record<string, unknown>;
  return (
    typeof maybeSession.userId === "string" &&
    maybeSession.userId.trim().length > 0 &&
    typeof maybeSession.accessToken === "string" &&
    maybeSession.accessToken.trim().length > 0
  );
}

function readString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}
