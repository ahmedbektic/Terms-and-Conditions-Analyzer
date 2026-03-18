import { FormEvent, useState } from 'react';

import type { PasswordCredentials } from '../../../lib/auth/contracts';

type AuthMode = 'sign_in' | 'sign_up';

// Centralized mode copy keeps auth CTA wording consistent across UI states.
const AUTH_MODE_COPY: Record<
  AuthMode,
  {
    title: string;
    submitLabel: string;
    modeDescription: string;
    passwordAutocomplete: 'current-password' | 'new-password';
    toggleLabel: string;
  }
> = {
  sign_in: {
    title: 'Sign in to Terms and Conditions Analyzer',
    submitLabel: 'Sign in',
    modeDescription: 'Use your account credentials to access saved reports and tracking history.',
    passwordAutocomplete: 'current-password',
    toggleLabel: 'Need an account?',
  },
  sign_up: {
    title: 'Create your Terms and Conditions Analyzer account',
    submitLabel: 'Create account',
    modeDescription: 'Create an account to start saving reports and monitoring policy changes.',
    passwordAutocomplete: 'new-password',
    toggleLabel: 'Have an account?',
  },
};

interface LoginScreenProps {
  errorMessage: string | null;
  isSubmitting: boolean;
  onSignInWithPassword: (credentials: PasswordCredentials) => Promise<void>;
  onSignUpWithPassword: (credentials: PasswordCredentials) => Promise<void>;
  onSignInWithGoogle: () => Promise<void>;
  onClearError: () => void;
}

export function LoginScreen({
  errorMessage,
  isSubmitting,
  onSignInWithPassword,
  onSignUpWithPassword,
  onSignInWithGoogle,
  onClearError,
}: LoginScreenProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<AuthMode>('sign_in');
  const modeCopy = AUTH_MODE_COPY[mode];

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onClearError();

    const credentials: PasswordCredentials = {
      email: email.trim(),
      password,
    };

    if (mode === 'sign_in') {
      await onSignInWithPassword(credentials);
      return;
    }
    await onSignUpWithPassword(credentials);
  };

  const handleGoogleSignIn = async () => {
    onClearError();
    await onSignInWithGoogle();
  };

  return (
    <main className="auth-shell">
      <section className="auth-card panel">
        <header className="panel-header">
          <h1 className="panel-title auth-title">{modeCopy.title}</h1>
          <p className="panel-description auth-subtitle">
            Use email/password credentials or Google sign-in to access your saved report history.
          </p>
          <p className="auth-mode-description">{modeCopy.modeDescription}</p>
        </header>

        {errorMessage ? (
          <div className="error-banner" role="alert">
            <span>{errorMessage}</span>
            <button type="button" className="button-link" onClick={onClearError}>
              Dismiss
            </button>
          </div>
        ) : null}

        <form className="form-grid auth-form-grid" onSubmit={handleSubmit}>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
            />
          </label>

          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={modeCopy.passwordAutocomplete}
              required
            />
          </label>
          {mode === 'sign_up' ? (
            <p className="field-help auth-field-help">Use at least 8 characters for stronger security.</p>
          ) : null}

          <div className="actions auth-actions">
            <button type="submit" className="button-primary auth-submit-button" disabled={isSubmitting}>
              {modeCopy.submitLabel}
            </button>
            <button
              type="button"
              className="button-link auth-mode-toggle"
              disabled={isSubmitting}
              onClick={() => setMode((previous) => (previous === 'sign_in' ? 'sign_up' : 'sign_in'))}
            >
              {modeCopy.toggleLabel}
            </button>
          </div>
        </form>

        <section className="auth-provider-section">
          <div className="auth-divider" aria-hidden>
            <span>or</span>
          </div>
          <button
            type="button"
            className="button-secondary auth-google-button"
            onClick={() => {
              void handleGoogleSignIn();
            }}
            disabled={isSubmitting}
          >
            Continue with Google
          </button>
        </section>
      </section>
    </main>
  );
}
