/* Architecture note:
 * AuthProvider is the single app-level owner of auth session state.
 * Components should consume auth through `useAuth`, not directly through
 * Supabase APIs, so provider internals remain replaceable and testable.
 */

import { createContext, type ReactNode, useContext } from 'react';

import type { AuthClient } from '../../lib/auth/contracts';
import { useAuthSession, type UseAuthSessionResult } from './hooks/useAuthSession';

const AuthContext = createContext<UseAuthSessionResult | null>(null);

interface AuthProviderProps {
  children: ReactNode;
  // Optional injection seam used by tests and future non-browser auth adapters.
  authClient?: AuthClient;
}

export function AuthProvider({ children, authClient }: AuthProviderProps) {
  const auth = useAuthSession(authClient);
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}

export function useAuth(): UseAuthSessionResult {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider.');
  }
  return context;
}
