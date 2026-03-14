/* Architecture note:
 * This hook orchestrates auth state for app-level screens and provides
 * transport-neutral session/token access for dashboard API calls.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type {
  AuthClient,
  AuthStateChange,
  AuthenticatedSession,
  AuthSessionState,
  PasswordCredentials,
} from '../../../lib/auth/contracts';
import { getAuthClient } from '../../../lib/auth/supabaseClient';

export interface UseAuthSessionResult {
  isAuthenticated: boolean;
  state: AuthSessionState;
  getAccessToken: () => string | null;
  clearError: () => void;
  signInWithPassword: (credentials: PasswordCredentials) => Promise<void>;
  signUpWithPassword: (credentials: PasswordCredentials) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
}

/**
 * Convert provider session into UI auth state.
 * Keeping this mapping isolated helps when auth providers diverge between
 * web and future extension runtimes.
 */
function toSessionState(session: AuthenticatedSession | null): AuthSessionState {
  return {
    status: session ? 'authenticated' : 'unauthenticated',
    session,
    errorMessage: null,
  };
}

/**
 * App-level auth state machine consumed by `AuthEntryPoint`.
 *
 * Responsibilities:
 * - bootstrap initial persisted session
 * - subscribe to provider auth events
 * - expose transport-neutral auth actions and access-token getter
 *
 * Non-responsibilities:
 * - direct dashboard data fetching
 * - provider-specific SDK calls outside the `AuthClient` contract
 */
export function useAuthSession(authClient: AuthClient = getAuthClient()): UseAuthSessionResult {
  // Sign-out should not be shown as an auth error; token-expiry sign-outs should.
  const suppressNextSignedOutMessageRef = useRef(false);
  const sessionRef = useRef<AuthenticatedSession | null>(null);
  const [state, setState] = useState<AuthSessionState>({
    status: 'loading',
    session: null,
    errorMessage: null,
  });

  useEffect(() => {
    let isActive = true;

    const loadInitialSession = async () => {
      try {
        const session = await authClient.getSession();
        if (!isActive) {
          return;
        }
        setState(toSessionState(session));
      } catch (error) {
        if (!isActive) {
          return;
        }
        setState({
          status: 'unauthenticated',
          session: null,
          errorMessage:
            error instanceof Error ? error.message : 'Unable to load auth session state.',
        });
      }
    };

    void loadInitialSession();
    const unsubscribe = authClient.onAuthStateChange((change) => {
      if (!isActive) {
        return;
      }
      setState((previousState) =>
        resolveStateFromChange(
          change,
          previousState,
          suppressNextSignedOutMessageRef.current,
        ),
      );
      if (change.reason === 'signed_out') {
        suppressNextSignedOutMessageRef.current = false;
      }
    });

    return () => {
      isActive = false;
      unsubscribe();
    };
  }, [authClient]);

  const clearError = useCallback(() => {
    setState((previous) => ({ ...previous, errorMessage: null }));
  }, []);

  // Keep latest session available to a stable token getter.
  sessionRef.current = state.session;

  // Stable callback keeps downstream API client wiring from re-instantiating
  // on every auth-state update while still reading the latest session token.
  const getAccessToken = useCallback(() => sessionRef.current?.accessToken ?? null, []);

  // Shared action wrapper keeps auth action error handling consistent.
  const performAction = useCallback(
    async (action: () => Promise<void>) => {
      try {
        await action();
        setState((previous) => ({ ...previous, errorMessage: null }));
      } catch (error) {
        setState((previous) => ({
          ...previous,
          errorMessage: error instanceof Error ? error.message : 'Authentication action failed.',
        }));
      }
    },
    [],
  );

  const signInWithPassword = useCallback(
    async (credentials: PasswordCredentials) => {
      await performAction(() => authClient.signInWithPassword(credentials));
    },
    [authClient, performAction],
  );

  const signUpWithPassword = useCallback(
    async (credentials: PasswordCredentials) => {
      await performAction(() => authClient.signUpWithPassword(credentials));
    },
    [authClient, performAction],
  );

  const signInWithGoogle = useCallback(async () => {
    await performAction(() => authClient.signInWithGoogle());
  }, [authClient, performAction]);

  const signOut = useCallback(async () => {
    suppressNextSignedOutMessageRef.current = true;
    await performAction(() => authClient.signOut());
  }, [authClient, performAction]);

  return {
    isAuthenticated: state.status === 'authenticated',
    state,
    getAccessToken,
    clearError,
    signInWithPassword,
    signUpWithPassword,
    signInWithGoogle,
    signOut,
  };
}

function resolveStateFromChange(
  change: AuthStateChange,
  previousState: AuthSessionState,
  suppressSignedOutMessage: boolean,
): AuthSessionState {
  const nextState = toSessionState(change.session);

  // If a signed-in user is later signed out (manual sign-out, token expiry,
  // revoked session, etc.), make the transition explicit for the login screen.
  if (
    change.reason === 'signed_out' &&
    previousState.status === 'authenticated' &&
    !suppressSignedOutMessage
  ) {
    return {
      ...nextState,
      errorMessage: 'Your session has ended. Please sign in again.',
    };
  }

  return nextState;
}
