/* Architecture note:
 * This is the frontend auth boundary shared by web dashboard today and
 * browser-extension surfaces later. Dashboard logic consumes only these
 * contracts, not provider-specific SDK types.
 */

export interface AuthenticatedSession {
  userId: string;
  accessToken: string;
  email: string | null;
  expiresAt: number | null;
}

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';

export interface AuthSessionState {
  status: AuthStatus;
  session: AuthenticatedSession | null;
  errorMessage: string | null;
}

export type AuthStateChangeReason =
  | 'initial_session'
  | 'signed_in'
  | 'signed_out'
  | 'token_refreshed'
  | 'user_updated'
  | 'password_recovery'
  | 'unknown';

export interface AuthStateChange {
  reason: AuthStateChangeReason;
  session: AuthenticatedSession | null;
}

export interface PasswordCredentials {
  email: string;
  password: string;
}

export interface AuthClient {
  // Reads currently persisted session (if any) on app bootstrap.
  getSession: () => Promise<AuthenticatedSession | null>;
  // Subscribes to provider auth changes and returns an unsubscribe callback.
  onAuthStateChange: (listener: (change: AuthStateChange) => void) => () => void;
  signInWithPassword: (credentials: PasswordCredentials) => Promise<void>;
  signUpWithPassword: (credentials: PasswordCredentials) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
}
