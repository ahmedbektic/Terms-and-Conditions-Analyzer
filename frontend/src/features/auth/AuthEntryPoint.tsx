/* Architecture note:
 * App-level auth gate (minimal route guarding without adding router complexity).
 * This module owns auth-aware wiring (token source + sign-out action) and
 * injects a preconfigured dashboard API client into dashboard feature code.
 * Dashboard components stay focused on report workflows only.
 *
 * High-level screen flow:
 * 1) `loading`: wait for provider session bootstrap
 * 2) `unauthenticated`: render login surface
 * 3) `authenticated`: render dashboard with authenticated API transport
 */

import { useMemo, useState } from 'react';

import { PanelStateMessage } from '../../components/ui/PanelStateMessage';
import { createDashboardApiClient } from '../../lib/api/createDashboardApiClient';
import { DashboardPage } from '../dashboard/DashboardPage';
import { useAuth } from './AuthProvider';
import { LoginScreen } from './components/LoginScreen';

export function AuthEntryPoint() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const {
    isAuthenticated,
    state,
    getAccessToken,
    clearError,
    signInWithPassword,
    signUpWithPassword,
    signInWithGoogle,
    signOut,
  } = useAuth();

  const runSubmittingAction = async (action: () => Promise<void>) => {
    setIsSubmitting(true);
    try {
      await action();
    } finally {
      setIsSubmitting(false);
    }
  };

  const dashboardApiClient = useMemo(
    () => createDashboardApiClient({ getAccessToken }),
    [getAccessToken],
  );

  if (state.status === 'loading') {
    return (
      <main className="auth-shell">
        <section className="auth-card panel">
          <header className="panel-header">
            <h1 className="panel-title auth-title">Checking your session...</h1>
            <p className="panel-description">Loading authentication status.</p>
          </header>
          <PanelStateMessage message="Please wait while your session is validated." compact />
        </section>
      </main>
    );
  }

  if (!isAuthenticated) {
    return (
      <LoginScreen
        errorMessage={state.errorMessage}
        isSubmitting={isSubmitting}
        onClearError={clearError}
        onSignInWithPassword={(credentials) =>
          runSubmittingAction(() => signInWithPassword(credentials))
        }
        onSignUpWithPassword={(credentials) =>
          runSubmittingAction(() => signUpWithPassword(credentials))
        }
        onSignInWithGoogle={() => runSubmittingAction(() => signInWithGoogle())}
      />
    );
  }

  return (
    <DashboardPage
      apiClient={dashboardApiClient}
      contextLabel={state.session?.email ? `Signed in as ${state.session.email}` : null}
      headerAction={
        <button
          type="button"
          className="button-secondary"
          onClick={() => {
            void runSubmittingAction(() => signOut());
          }}
          disabled={isSubmitting}
        >
          Sign out
        </button>
      }
    />
  );
}
