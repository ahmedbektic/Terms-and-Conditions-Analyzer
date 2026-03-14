import { FormEvent, useState } from 'react';

import type { PasswordCredentials } from '../../../lib/auth/contracts';

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
  const [mode, setMode] = useState<'sign_in' | 'sign_up'>('sign_in');

  const submitLabel = mode === 'sign_in' ? 'Sign in' : 'Create account';

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
        <h1 className="panel-title">Sign in to Terms and Conditions Analyzer</h1>
        <p className="muted auth-subtitle">
          Use email/password credentials or Google sign-in to access your saved report history.
        </p>

        {errorMessage ? (
          <div className="error-banner" role="alert">
            <span>{errorMessage}</span>
            <button type="button" onClick={onClearError}>
              Dismiss
            </button>
          </div>
        ) : null}

        <form className="form-grid" onSubmit={handleSubmit}>
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
              autoComplete="current-password"
              required
            />
          </label>

          <div className="actions auth-actions">
            <button type="submit" disabled={isSubmitting}>
              {submitLabel}
            </button>
            <button
              type="button"
              className="button-secondary"
              disabled={isSubmitting}
              onClick={() => setMode((previous) => (previous === 'sign_in' ? 'sign_up' : 'sign_in'))}
            >
              {mode === 'sign_in' ? 'Need an account?' : 'Have an account?'}
            </button>
          </div>
        </form>

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
    </main>
  );
}
