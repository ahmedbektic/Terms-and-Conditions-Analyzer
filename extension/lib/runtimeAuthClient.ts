import type {
  AuthClient,
  AuthStateChange,
  AuthStateChangeReason,
  AuthenticatedSession,
  PasswordCredentials,
} from "../../frontend/src/lib/auth/contracts";
import {
  AUTH_PROVIDER_GOOGLE,
  normalizeProviderSignInError,
} from "../../frontend/src/lib/auth/providerErrors";

// Extension auth/session storage keys.
const AUTH_SESSION_STORAGE_KEY = "auth_session";
const AUTH_REFRESH_TOKEN_STORAGE_KEY = "auth_refresh_token";
const AUTH_SUPABASE_URL_STORAGE_KEY = "auth_supabase_url";
const AUTH_SUPABASE_ANON_KEY_STORAGE_KEY = "auth_supabase_anon_key";

interface SupabaseAuthConfig {
  supabaseUrl: string;
  anonKey: string;
}

interface SupabaseAuthUser {
  id: string;
  email: string | null;
}

interface SupabaseTokenPayload {
  access_token: string;
  refresh_token?: string | null;
  expires_in?: number | null;
  expires_at?: number | null;
  user?: {
    id?: string;
    email?: string | null;
  } | null;
}

interface SupabaseSignUpPayload {
  session?: SupabaseTokenPayload | null;
  access_token?: string;
  refresh_token?: string | null;
  expires_in?: number | null;
  expires_at?: number | null;
  user?: {
    id?: string;
    email?: string | null;
  } | null;
}

/**
 * Runtime auth adapter for extension surfaces.
 *
 * Design boundary:
 * - Implements shared `AuthClient` contract used by background orchestration.
 * - Keeps Supabase-specific REST/OAuth behavior isolated to this module.
 * - Persists only normalized session shape consumed by shared app seams.
 */
export class ExtensionRuntimeAuthClient implements AuthClient {
  async getSession(): Promise<AuthenticatedSession | null> {
    const stored = await chrome.storage.local.get(AUTH_SESSION_STORAGE_KEY);
    const session = toAuthenticatedSession(stored[AUTH_SESSION_STORAGE_KEY]);
    if (!session) {
      return null;
    }

    if (isExpired(session.expiresAt)) {
      // Expired sessions are cleared eagerly to keep auth state deterministic.
      await clearStoredSession();
      return null;
    }

    return session;
  }

  onAuthStateChange(listener: (change: AuthStateChange) => void): () => void {
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

  async signInWithPassword(credentials: PasswordCredentials): Promise<void> {
    const config = await resolveSupabaseAuthConfig();
    const email = credentials.email.trim();
    const password = credentials.password;
    if (!email || !password) {
      throw new Error("Email and password are required.");
    }

    const tokenPayload = await requestSupabaseJson<SupabaseTokenPayload>({
      config,
      method: "POST",
      endpoint: "/auth/v1/token?grant_type=password",
      body: { email, password },
      accessToken: null,
    });

    await persistSessionFromTokenPayload(tokenPayload);
  }

  async signUpWithPassword(credentials: PasswordCredentials): Promise<void> {
    const config = await resolveSupabaseAuthConfig();
    const email = credentials.email.trim();
    const password = credentials.password;
    if (!email || !password) {
      throw new Error("Email and password are required.");
    }

    const signUpPayload = await requestSupabaseJson<SupabaseSignUpPayload>({
      config,
      method: "POST",
      endpoint: "/auth/v1/signup",
      body: { email, password },
      accessToken: null,
    });

    const tokenPayload = extractSignUpTokenPayload(signUpPayload);
    if (!tokenPayload) {
      // Supabase may require email verification before issuing a session.
      throw new Error(
        "Sign-up completed but no active session was returned. Verify email, then sign in.",
      );
    }

    await persistSessionFromTokenPayload(tokenPayload);
  }

  async signInWithGoogle(): Promise<void> {
    try {
      const config = await resolveSupabaseAuthConfig();
      const callbackUrl = await launchGoogleOAuthFlow(config.supabaseUrl);
      const tokenPayload = parseOAuthCallbackTokenPayload(callbackUrl);

      // Google OAuth callback includes access token; fetch user profile to avoid
      // coupling session identity strictly to token-claim parsing.
      const user = await fetchSupabaseUser(config, tokenPayload.access_token);
      await persistSessionFromTokenPayload({
        ...tokenPayload,
        user: {
          id: user.id,
          email: user.email,
        },
      });
    } catch (error) {
      // Keep Google auth failures aligned with web login messaging so
      // provider setup/debug instructions stay client-agnostic.
      const normalized = normalizeProviderSignInError(error, AUTH_PROVIDER_GOOGLE);
      throw new Error(normalized.message);
    }
  }

  async signOut(): Promise<void> {
    // Sign-out is best-effort on provider side; local session should always be
    // cleared even if network/logout endpoint fails.
    try {
      const [config, session] = await Promise.all([
        resolveSupabaseAuthConfig().catch(() => null),
        this.getSession(),
      ]);
      if (config && session?.accessToken) {
        await requestSupabaseJson<unknown>({
          config,
          method: "POST",
          endpoint: "/auth/v1/logout",
          body: {},
          accessToken: session.accessToken,
        });
      }
    } catch {
      // Ignore provider logout errors; local sign-out still proceeds below.
    }

    await clearStoredSession();
  }
}

export function createExtensionRuntimeAuthClient(): AuthClient {
  return new ExtensionRuntimeAuthClient();
}

async function resolveSupabaseAuthConfig(): Promise<SupabaseAuthConfig> {
  const stored = await chrome.storage.local.get([
    AUTH_SUPABASE_URL_STORAGE_KEY,
    AUTH_SUPABASE_ANON_KEY_STORAGE_KEY,
  ]);

  const buildTimeConfig = readBuildTimeSupabaseConfig();
  const supabaseUrl = normalizeSupabaseUrl(
    readString(stored[AUTH_SUPABASE_URL_STORAGE_KEY]) || buildTimeConfig.supabaseUrl,
  );
  const anonKey =
    readString(stored[AUTH_SUPABASE_ANON_KEY_STORAGE_KEY]) || buildTimeConfig.anonKey;

  if (!supabaseUrl || !anonKey) {
    throw new Error(
      "Extension auth is not configured. Set EXTENSION_SUPABASE_URL and EXTENSION_SUPABASE_ANON_KEY at build time, or store auth_supabase_url/auth_supabase_anon_key in chrome.storage.local.",
    );
  }

  return {
    supabaseUrl,
    anonKey,
  };
}

function readBuildTimeSupabaseConfig(): SupabaseAuthConfig {
  return {
    supabaseUrl: normalizeSupabaseUrl(
      readString(
        (globalThis as unknown as { __EXTENSION_SUPABASE_URL__?: unknown })
          .__EXTENSION_SUPABASE_URL__,
      ),
    ),
    anonKey: readString(
      (globalThis as unknown as { __EXTENSION_SUPABASE_ANON_KEY__?: unknown })
        .__EXTENSION_SUPABASE_ANON_KEY__,
    ),
  };
}

function normalizeSupabaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

function readString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

async function launchGoogleOAuthFlow(supabaseUrl: string): Promise<string> {
  const redirectUrl = chrome.identity.getRedirectURL("supabase-auth");
  const authorizeUrl = new URL(`${supabaseUrl}/auth/v1/authorize`);
  authorizeUrl.searchParams.set("provider", AUTH_PROVIDER_GOOGLE);
  authorizeUrl.searchParams.set("redirect_to", redirectUrl);
  authorizeUrl.searchParams.set("response_type", "token");
  authorizeUrl.searchParams.set("flow_type", "implicit");

  return new Promise((resolve, reject) => {
    chrome.identity.launchWebAuthFlow(
      {
        url: authorizeUrl.toString(),
        interactive: true,
      },
      (callbackUrl) => {
        if (chrome.runtime.lastError) {
          reject(
            new Error(
              chrome.runtime.lastError.message ??
                "Google sign-in failed without an explicit Chrome runtime error.",
            ),
          );
          return;
        }

        if (!callbackUrl) {
          reject(new Error("Google sign-in did not return an OAuth callback URL."));
          return;
        }

        resolve(callbackUrl);
      },
    );
  });
}

function parseOAuthCallbackTokenPayload(callbackUrl: string): SupabaseTokenPayload {
  const url = new URL(callbackUrl);
  const hashParams = new URLSearchParams(url.hash.startsWith("#") ? url.hash.slice(1) : "");

  const oauthError = hashParams.get("error");
  if (oauthError) {
    const detail = hashParams.get("error_description") ?? oauthError;
    throw new Error(`Google sign-in failed: ${detail}`);
  }

  const accessToken = hashParams.get("access_token");
  if (!accessToken || !accessToken.trim()) {
    throw new Error("Google sign-in did not return an access token.");
  }

  return {
    access_token: accessToken.trim(),
    refresh_token: hashParams.get("refresh_token"),
    expires_in: parseNumericClaim(hashParams.get("expires_in")),
    expires_at: parseNumericClaim(hashParams.get("expires_at")),
  };
}

async function fetchSupabaseUser(
  config: SupabaseAuthConfig,
  accessToken: string,
): Promise<SupabaseAuthUser> {
  const payload = await requestSupabaseJson<{ id?: unknown; email?: unknown }>({
    config,
    method: "GET",
    endpoint: "/auth/v1/user",
    body: undefined,
    accessToken,
  });

  const userId = typeof payload.id === "string" ? payload.id.trim() : "";
  if (!userId) {
    throw new Error("Supabase user profile response is missing a valid user id.");
  }

  return {
    id: userId,
    email: typeof payload.email === "string" ? payload.email : null,
  };
}

async function persistSessionFromTokenPayload(payload: SupabaseTokenPayload): Promise<void> {
  const session = toAuthenticatedSessionFromTokenPayload(payload);
  await chrome.storage.local.set({
    [AUTH_SESSION_STORAGE_KEY]: session,
    [AUTH_REFRESH_TOKEN_STORAGE_KEY]: payload.refresh_token ?? null,
  });
}

function extractSignUpTokenPayload(payload: SupabaseSignUpPayload): SupabaseTokenPayload | null {
  if (payload.session && isTokenPayloadLike(payload.session)) {
    return payload.session;
  }
  if (isTokenPayloadLike(payload)) {
    return payload;
  }
  return null;
}

function isTokenPayloadLike(value: unknown): value is SupabaseTokenPayload {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const tokenPayload = value as { access_token?: unknown };
  return typeof tokenPayload.access_token === "string" && tokenPayload.access_token.trim().length > 0;
}

function toAuthenticatedSessionFromTokenPayload(payload: SupabaseTokenPayload): AuthenticatedSession {
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

function parseNumericClaim(rawValue: string | null): number | null {
  if (!rawValue) {
    return null;
  }
  const numeric = Number(rawValue);
  if (!Number.isFinite(numeric)) {
    return null;
  }
  return Math.floor(numeric);
}

function parseNumericUnknown(rawValue: unknown): number | null {
  if (typeof rawValue !== "number" || !Number.isFinite(rawValue)) {
    return null;
  }
  return Math.floor(rawValue);
}

interface SupabaseRequestOptions {
  config: SupabaseAuthConfig;
  method: "GET" | "POST";
  endpoint: string;
  body: Record<string, unknown> | undefined;
  accessToken: string | null;
}

async function requestSupabaseJson<T>(options: SupabaseRequestOptions): Promise<T> {
  const headers = new Headers({
    apikey: options.config.anonKey,
  });

  if (options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (options.accessToken) {
    headers.set("Authorization", `Bearer ${options.accessToken}`);
  }

  const response = await fetch(`${options.config.supabaseUrl}${options.endpoint}`, {
    method: options.method,
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  const rawText = await response.text();
  const payload = safeParseJson(rawText);

  if (!response.ok) {
    throw new Error(extractSupabaseErrorMessage(payload, response.status));
  }

  return payload as T;
}

function safeParseJson(text: string): unknown {
  if (!text.trim()) {
    return {};
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return {};
  }
}

function extractSupabaseErrorMessage(payload: unknown, statusCode: number): string {
  if (typeof payload === "object" && payload !== null) {
    const withMessage = payload as {
      error_description?: unknown;
      msg?: unknown;
      message?: unknown;
      error?: unknown;
    };

    const messageCandidate =
      withMessage.error_description ??
      withMessage.msg ??
      withMessage.message ??
      withMessage.error;

    if (typeof messageCandidate === "string" && messageCandidate.trim()) {
      return messageCandidate;
    }
  }

  return `Supabase auth request failed with status ${statusCode}.`;
}

async function clearStoredSession(): Promise<void> {
  await chrome.storage.local.remove([AUTH_SESSION_STORAGE_KEY, AUTH_REFRESH_TOKEN_STORAGE_KEY]);
}

function isExpired(expiresAt: number | null): boolean {
  if (typeof expiresAt !== "number") {
    return false;
  }
  return expiresAt <= Math.floor(Date.now() / 1000);
}

function inferChangeReason(
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

function toAuthenticatedSession(value: unknown): AuthenticatedSession | null {
  if (!isSessionLike(value)) {
    return null;
  }
  return {
    userId: value.userId,
    accessToken: value.accessToken,
    email: value.email ?? null,
    expiresAt: value.expiresAt ?? null,
  };
}

function isSessionLike(
  value: unknown,
): value is {
  userId: string;
  accessToken: string;
  email?: string | null;
  expiresAt?: number | null;
} {
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
