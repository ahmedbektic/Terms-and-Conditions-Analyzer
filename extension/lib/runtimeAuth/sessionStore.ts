import type {
  AuthStateChange,
  AuthenticatedSession,
} from "../../../frontend/src/lib/auth/contracts";
import { inferChangeReason, toAuthenticatedSession, toAuthenticatedSessionFromTokenPayload } from "./sessionCodec";
import type { SupabaseTokenPayload } from "./types";

const AUTH_SESSION_STORAGE_KEY = "auth_session";
const AUTH_REFRESH_TOKEN_STORAGE_KEY = "auth_refresh_token";

export async function readStoredSession(): Promise<AuthenticatedSession | null> {
  const stored = await chrome.storage.local.get(AUTH_SESSION_STORAGE_KEY);
  return toAuthenticatedSession(stored[AUTH_SESSION_STORAGE_KEY]);
}

export async function persistSessionFromTokenPayload(
  payload: SupabaseTokenPayload,
): Promise<void> {
  const session = toAuthenticatedSessionFromTokenPayload(payload);
  await chrome.storage.local.set({
    [AUTH_SESSION_STORAGE_KEY]: session,
    [AUTH_REFRESH_TOKEN_STORAGE_KEY]: payload.refresh_token ?? null,
  });
}

export async function clearStoredSession(): Promise<void> {
  await chrome.storage.local.remove([AUTH_SESSION_STORAGE_KEY, AUTH_REFRESH_TOKEN_STORAGE_KEY]);
}

export function onStoredSessionChange(listener: (change: AuthStateChange) => void): () => void {
  const handleAuthSessionStorageChange = (
    changes: Record<string, chrome.storage.StorageChange>,
    areaName: string,
  ) => {
    if (areaName !== "local" || !(AUTH_SESSION_STORAGE_KEY in changes)) {
      return;
    }

    const authSessionChange = changes[AUTH_SESSION_STORAGE_KEY];
    const previousSession = toAuthenticatedSession(authSessionChange.oldValue);
    const nextSession = toAuthenticatedSession(authSessionChange.newValue);

    listener({
      reason: inferChangeReason(previousSession, nextSession),
      session: nextSession,
    });
  };

  chrome.storage.onChanged.addListener(handleAuthSessionStorageChange);
  return () => {
    chrome.storage.onChanged.removeListener(handleAuthSessionStorageChange);
  };
}
