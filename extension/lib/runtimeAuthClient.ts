import type {
  AuthClient,
  AuthenticatedSession,
  PasswordCredentials,
} from "../../frontend/src/lib/auth/contracts";
import {
  AUTH_PROVIDER_GOOGLE,
  normalizeProviderSignInError,
} from "../../frontend/src/lib/auth/providerErrors";
import { resolveSupabaseAuthConfig } from "./runtimeAuth/config";
import { launchGooglePkceOAuthFlow } from "./runtimeAuth/oauthGoogle";
import { extractSignUpTokenPayload, isExpired } from "./runtimeAuth/sessionCodec";
import {
  clearStoredSession,
  onStoredSessionChange,
  persistSessionFromTokenPayload,
  readStoredSession,
} from "./runtimeAuth/sessionStore";
import { requestSupabaseJson } from "./runtimeAuth/supabaseHttp";
import type {
  NormalizedCredentials,
  SupabaseSignUpPayload,
  SupabaseTokenPayload,
} from "./runtimeAuth/types";

/**
 * Runtime auth adapter for extension surfaces.
 *
 * Design boundary:
 * - Implements shared `AuthClient` contract used by background orchestration.
 * - Keeps Supabase-specific REST/OAuth behavior isolated to this module.
 * - Persists only normalized session shape consumed by shared app seams.
 *
 * TODO(scrum-auth-refresh):
 * Token refresh automation remains intentionally deferred. Implement in a
 * dedicated story when either condition is required in runtime:
 * - `getSession()` finds expired access token with a persisted refresh token
 * - authenticated backend calls return 401 and should trigger one refresh retry
 */
export class ExtensionRuntimeAuthClient implements AuthClient {
  async getSession(): Promise<AuthenticatedSession | null> {
    const session = await readStoredSession();
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

  onAuthStateChange(listener: Parameters<AuthClient["onAuthStateChange"]>[0]): () => void {
    return onStoredSessionChange(listener);
  }

  async signInWithPassword(credentials: PasswordCredentials): Promise<void> {
    const config = await resolveSupabaseAuthConfig();
    const normalizedCredentials = normalizeCredentials(credentials);

    const tokenPayload = await requestSupabaseJson<SupabaseTokenPayload>({
      config,
      method: "POST",
      endpoint: "/auth/v1/token?grant_type=password",
      body: normalizedCredentials,
      accessToken: null,
    });

    await persistSessionFromTokenPayload(tokenPayload);
  }

  async signUpWithPassword(credentials: PasswordCredentials): Promise<void> {
    const config = await resolveSupabaseAuthConfig();
    const normalizedCredentials = normalizeCredentials(credentials);

    const signUpPayload = await requestSupabaseJson<SupabaseSignUpPayload>({
      config,
      method: "POST",
      endpoint: "/auth/v1/signup",
      body: normalizedCredentials,
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
      // Extension runtime uses PKCE code flow for Google OAuth:
      // callback returns an auth code and background exchanges it for session
      // via Supabase token endpoint.
      const oauthFlow = await launchGooglePkceOAuthFlow(config.supabaseUrl);
      const tokenPayload = await requestSupabaseJson<SupabaseTokenPayload>({
        config,
        method: "POST",
        endpoint: "/auth/v1/token?grant_type=pkce",
        body: {
          auth_code: oauthFlow.authCode,
          code_verifier: oauthFlow.codeVerifier,
        },
        accessToken: null,
      });

      await persistSessionFromTokenPayload(tokenPayload);
    } catch (error) {
      // Keep Google auth failures aligned with web login messaging so
      // provider setup/debug instructions stay client-agnostic.
      const normalized = normalizeProviderSignInError(error, AUTH_PROVIDER_GOOGLE);
      throw new Error(toActionableGoogleSignInMessage(normalized.message, normalized.rawMessage));
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
          config: {
            supabaseUrl: config.supabaseUrl,
            anonKey: config.anonKey,
          },
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

function normalizeCredentials(credentials: PasswordCredentials): NormalizedCredentials {
  const email = credentials.email.trim();
  const password = credentials.password;
  if (!email || !password) {
    throw new Error("Email and password are required.");
  }

  return { email, password };
}

function toActionableGoogleSignInMessage(normalizedMessage: string, rawMessage: string): string {
  if (/authorization page could not be loaded/i.test(rawMessage)) {
    return "Google sign-in failed. Authorization page could not be loaded. Verify auth_supabase_url/EXTENSION_SUPABASE_URL is your project root URL (https://<project-ref>.supabase.co, not /auth/v1), then retry.";
  }
  if (/bad_oauth_callback|oauth state parameter missing/i.test(rawMessage)) {
    return "Google sign-in failed because Supabase rejected the OAuth callback. Verify extension redirect allow-list and use PKCE callback URL exactly: https://<extension-id>.chromiumapp.org/supabase-auth.";
  }
  return normalizedMessage;
}
