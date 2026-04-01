/* Architecture note:
 * This module is the provider adapter seam for Supabase Auth. The auth hook
 * depends on the `AuthClient` contract so provider internals stay isolated.
 * Extension work can reuse the same `AuthClient` contract with a different
 * adapter implementation if runtime constraints differ.
 */

import {
  createClient,
  type AuthChangeEvent,
  type Session,
  type SupabaseClient,
} from '@supabase/supabase-js';

import type {
  AuthClient,
  AuthStateChange,
  AuthStateChangeReason,
  AuthenticatedSession,
  PasswordCredentials,
} from './contracts';
import {
  AUTH_PROVIDER_GOOGLE,
  normalizeProviderSignInError,
} from './providerErrors';
import {
  AuthAttemptThrottle,
  PASSWORD_SIGN_IN_ATTEMPT_POLICY,
  PASSWORD_SIGN_UP_ATTEMPT_POLICY,
  createBrowserLocalStorageThrottleStore,
  normalizeAuthAttemptIdentifier,
} from '../security/authAttemptThrottle';
import { sanitizePasswordCredentials } from '../security/inputValidation';

function readEnvValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function getSupabaseUrl(): string {
  return readEnvValue(import.meta.env.VITE_SUPABASE_URL);
}

function getSupabaseAnonKey(): string {
  return readEnvValue(import.meta.env.VITE_SUPABASE_ANON_KEY);
}

export function isSupabaseConfigured(): boolean {
  return Boolean(getSupabaseUrl() && getSupabaseAnonKey());
}

/**
 * Guard rail client used when required Supabase env vars are missing.
 * It keeps failure messages explicit and centralized.
 */
class MissingSupabaseConfigurationClient implements AuthClient {
  async getSession(): Promise<AuthenticatedSession | null> {
    throw this.buildConfigurationError();
  }

  onAuthStateChange(_listener: (change: AuthStateChange) => void): () => void {
    return () => {
      // No subscription is available without a configured SDK client.
    };
  }

  async signInWithPassword(_credentials: PasswordCredentials): Promise<void> {
    throw this.buildConfigurationError();
  }

  async signUpWithPassword(_credentials: PasswordCredentials): Promise<void> {
    throw this.buildConfigurationError();
  }

  async signInWithGoogle(): Promise<void> {
    throw this.buildConfigurationError();
  }

  async signOut(): Promise<void> {
    throw this.buildConfigurationError();
  }

  private buildConfigurationError(): Error {
    return new Error(
      'Supabase auth is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.',
    );
  }
}

/**
 * Production adapter for Supabase browser auth flows.
 */
class SupabaseBrowserAuthClient implements AuthClient {
  private readonly supabaseClient: SupabaseClient;
  private readonly signInAttemptThrottle: AuthAttemptThrottle;
  private readonly signUpAttemptThrottle: AuthAttemptThrottle;

  constructor(supabaseClient: SupabaseClient) {
    this.supabaseClient = supabaseClient;
    const throttleStore = createBrowserLocalStorageThrottleStore();
    this.signInAttemptThrottle = new AuthAttemptThrottle({
      policy: PASSWORD_SIGN_IN_ATTEMPT_POLICY,
      store: throttleStore,
      keyPrefix: 'web_auth_attempts',
    });
    this.signUpAttemptThrottle = new AuthAttemptThrottle({
      policy: PASSWORD_SIGN_UP_ATTEMPT_POLICY,
      store: throttleStore,
      keyPrefix: 'web_auth_attempts',
    });
  }

  async getSession(): Promise<AuthenticatedSession | null> {
    const { data, error } = await this.supabaseClient.auth.getSession();
    if (error) {
      throw new Error(error.message);
    }
    return mapSupabaseSession(data.session);
  }

  onAuthStateChange(listener: (change: AuthStateChange) => void): () => void {
    const {
      data: { subscription },
    } = this.supabaseClient.auth.onAuthStateChange((event, session) => {
      listener({
        reason: mapSupabaseEvent(event),
        session: mapSupabaseSession(session),
      });
    });

    return () => {
      subscription.unsubscribe();
    };
  }

  async signInWithPassword(credentials: PasswordCredentials): Promise<void> {
    const normalizedCredentials = sanitizePasswordCredentials(credentials);
    const normalizedEmail = normalizeAuthAttemptIdentifier(normalizedCredentials.email);
    await this.signInAttemptThrottle.registerAttempt(normalizedEmail);
    const { error } = await this.supabaseClient.auth.signInWithPassword({
      email: normalizedCredentials.email,
      password: normalizedCredentials.password,
    });
    if (error) {
      throw new Error(error.message);
    }
    await this.signInAttemptThrottle.clear(normalizedEmail);
  }

  async signUpWithPassword(credentials: PasswordCredentials): Promise<void> {
    const normalizedCredentials = sanitizePasswordCredentials(credentials);
    await this.signUpAttemptThrottle.registerAttempt(
      normalizeAuthAttemptIdentifier(normalizedCredentials.email),
    );
    const { error } = await this.supabaseClient.auth.signUp({
      email: normalizedCredentials.email,
      password: normalizedCredentials.password,
    });
    if (error) {
      throw new Error(error.message);
    }
  }

  async signInWithGoogle(): Promise<void> {
    const redirectTo =
      typeof window !== 'undefined' && window.location?.origin
        ? window.location.origin
        : undefined;
    const { error } = await this.supabaseClient.auth.signInWithOAuth({
      provider: AUTH_PROVIDER_GOOGLE,
      options: redirectTo ? { redirectTo } : undefined,
    });
    if (error) {
      // Shared normalization keeps auth setup failures readable and consistent
      // with extension runtime adapter messages.
      const normalized = normalizeProviderSignInError(error, AUTH_PROVIDER_GOOGLE);
      throw new Error(normalized.message);
    }
  }

  async signOut(): Promise<void> {
    const { error } = await this.supabaseClient.auth.signOut();
    if (error) {
      throw new Error(error.message);
    }
  }
}

let cachedClient: AuthClient | null = null;

export function getAuthClient(): AuthClient {
  // Singleton keeps one browser SDK instance and one auth event subscription
  // source across component renders.
  if (!cachedClient) {
    cachedClient = buildAuthClient();
  }
  return cachedClient;
}

function buildAuthClient(): AuthClient {
  if (!isSupabaseConfigured()) {
    return new MissingSupabaseConfigurationClient();
  }

  const supabaseClient = createClient(getSupabaseUrl(), getSupabaseAnonKey(), {
    auth: {
      // Session persistence + refresh support covers "persist during active usage".
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  });

  return new SupabaseBrowserAuthClient(supabaseClient);
}

function mapSupabaseSession(session: Session | null): AuthenticatedSession | null {
  if (!session || !session.user) {
    return null;
  }
  return {
    userId: session.user.id,
    accessToken: session.access_token,
    email: session.user.email ?? null,
    expiresAt: session.expires_at ?? null,
  };
}

function mapSupabaseEvent(event: AuthChangeEvent): AuthStateChangeReason {
  // Mapping is explicit so the rest of the app never depends on SDK event names.
  switch (event) {
    case 'INITIAL_SESSION':
      return 'initial_session';
    case 'SIGNED_IN':
      return 'signed_in';
    case 'SIGNED_OUT':
      return 'signed_out';
    case 'TOKEN_REFRESHED':
      return 'token_refreshed';
    case 'USER_UPDATED':
      return 'user_updated';
    case 'PASSWORD_RECOVERY':
      return 'password_recovery';
    default:
      return 'unknown';
  }
}
