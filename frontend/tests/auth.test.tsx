import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Mock } from 'vitest';

import { AuthEntryPoint } from '../src/features/auth/AuthEntryPoint';
import { AuthProvider } from '../src/features/auth/AuthProvider';
import type {
  AuthClient,
  AuthStateChange,
  AuthenticatedSession,
  PasswordCredentials,
} from '../src/lib/auth/contracts';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

function buildSession(overrides?: Partial<AuthenticatedSession>): AuthenticatedSession {
  return {
    userId: 'auth-user-1',
    accessToken: 'access-token-1',
    email: 'auth-user@example.com',
    expiresAt: 4070908800,
    ...overrides,
  };
}

interface AuthClientHarness {
  client: AuthClient;
  emit: (change: AuthStateChange) => void;
  signInWithPasswordMock: Mock<(credentials: PasswordCredentials) => Promise<void>>;
  signUpWithPasswordMock: Mock<(credentials: PasswordCredentials) => Promise<void>>;
  signInWithGoogleMock: Mock<() => Promise<void>>;
  signOutMock: Mock<() => Promise<void>>;
}

/**
 * Test-only auth adapter that mirrors the real contract used by AuthProvider.
 * This keeps tests focused on auth flow behavior rather than SDK internals.
 */
function createAuthClientHarness(
  initialSession: AuthenticatedSession | null,
): AuthClientHarness {
  let listener: ((change: AuthStateChange) => void) | null = null;

  const signInWithPasswordMock = vi.fn<(credentials: PasswordCredentials) => Promise<void>>(
    async () => {},
  );
  const signUpWithPasswordMock = vi.fn<(credentials: PasswordCredentials) => Promise<void>>(
    async () => {},
  );
  const signInWithGoogleMock = vi.fn<() => Promise<void>>(async () => {});
  const signOutMock = vi.fn<() => Promise<void>>(async () => {});

  const client: AuthClient = {
    getSession: vi.fn(async () => initialSession),
    onAuthStateChange: (nextListener) => {
      listener = nextListener;
      return () => {
        listener = null;
      };
    },
    signInWithPassword: signInWithPasswordMock,
    signUpWithPassword: signUpWithPasswordMock,
    signInWithGoogle: signInWithGoogleMock,
    signOut: signOutMock,
  };

  return {
    client,
    emit: (change) => {
      listener?.(change);
    },
    signInWithPasswordMock,
    signUpWithPasswordMock,
    signInWithGoogleMock,
    signOutMock,
  };
}

function renderAuthEntryPoint(harness: AuthClientHarness) {
  return render(
    <AuthProvider authClient={harness.client}>
      <AuthEntryPoint />
    </AuthProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  window.localStorage.clear();
});

describe('AuthEntryPoint', () => {
  it('renders login screen when no active session exists', async () => {
    const harness = createAuthClientHarness(null);

    renderAuthEntryPoint(harness);

    await waitFor(() =>
      expect(screen.getByText('Sign in to Terms and Conditions Analyzer')).toBeTruthy(),
    );
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy();
  });

  it('supports sign-up and Google sign-in initiation actions', async () => {
    const harness = createAuthClientHarness(null);
    const user = userEvent.setup();

    renderAuthEntryPoint(harness);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy());

    await user.click(screen.getByRole('button', { name: 'Need an account?' }));
    await user.type(screen.getByLabelText('Email'), '  new-user@example.com  ');
    await user.type(screen.getByLabelText('Password'), 'strong-password');
    await user.click(screen.getByRole('button', { name: 'Create account' }));

    expect(harness.signUpWithPasswordMock).toHaveBeenCalledTimes(1);
    expect(harness.signUpWithPasswordMock).toHaveBeenCalledWith({
      email: 'new-user@example.com',
      password: 'strong-password',
    });

    await user.click(screen.getByRole('button', { name: 'Continue with Google' }));
    expect(harness.signInWithGoogleMock).toHaveBeenCalledTimes(1);
  });

  it('handles sign-in happy path and renders dashboard with authenticated identity', async () => {
    const harness = createAuthClientHarness(null);
    const user = userEvent.setup();

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/reports')) {
        return jsonResponse([]);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    renderAuthEntryPoint(harness);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy());

    await user.type(screen.getByLabelText('Email'), 'auth-user@example.com');
    await user.type(screen.getByLabelText('Password'), 'password123');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(harness.signInWithPasswordMock).toHaveBeenCalledTimes(1);
    expect(harness.signInWithPasswordMock).toHaveBeenCalledWith({
      email: 'auth-user@example.com',
      password: 'password123',
    });

    harness.emit({
      reason: 'signed_in',
      session: buildSession({
        userId: 'signed-in-user',
        email: 'auth-user@example.com',
        accessToken: 'signed-in-access-token',
      }),
    });

    await waitFor(() => expect(screen.getByText('Terms and Conditions Dashboard')).toBeTruthy());
    expect(screen.getByText('Signed in as auth-user@example.com')).toBeTruthy();
  });

  it('surfaces denied access errors on the login screen', async () => {
    const harness = createAuthClientHarness(null);
    const user = userEvent.setup();

    harness.signInWithPasswordMock.mockRejectedValueOnce(new Error('Invalid login credentials.'));

    renderAuthEntryPoint(harness);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy());

    await user.type(screen.getByLabelText('Email'), 'denied-user@example.com');
    await user.type(screen.getByLabelText('Password'), 'wrong-password');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByText('Invalid login credentials.')).toBeTruthy();
  });

  it('loads report history for authenticated sessions and forwards bearer token only', async () => {
    const harness = createAuthClientHarness(
      buildSession({
        userId: 'persisted-user',
        accessToken: 'persisted-session-token',
        email: 'persisted@example.com',
      }),
    );

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/reports')) {
        return jsonResponse([
          {
            id: 'report-1',
            agreement_id: 'agreement-1',
            source_type: 'url',
            source_value: 'https://persisted.example/terms',
            status: 'completed',
            trust_score: 67,
            model_name: 'deterministic-keyword-v1',
            created_at: '2026-03-14T10:00:00Z',
          },
        ]);
      }
      throw new Error(`Unexpected request: ${String(input)} ${init?.method ?? 'GET'}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    renderAuthEntryPoint(harness);

    await waitFor(() => expect(screen.getByText('Signed in as persisted@example.com')).toBeTruthy());
    await waitFor(() => expect(screen.getByText('https://persisted.example/terms')).toBeTruthy());

    const reportsCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith('/reports'));
    expect(reportsCall).toBeTruthy();

    const init = reportsCall?.[1] as RequestInit | undefined;
    const headers = (init?.headers ?? {}) as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer persisted-session-token');
    expect(headers['X-Session-Id']).toBeUndefined();
  });

  it('returns to login with a clear message when an active session later expires', async () => {
    const harness = createAuthClientHarness(buildSession());

    const fetchMock = vi.fn(async () => jsonResponse([]));
    vi.stubGlobal('fetch', fetchMock);

    renderAuthEntryPoint(harness);
    await waitFor(() => expect(screen.getByText('Terms and Conditions Dashboard')).toBeTruthy());

    harness.emit({
      reason: 'signed_out',
      session: null,
    });

    await waitFor(() =>
      expect(screen.getByText('Sign in to Terms and Conditions Analyzer')).toBeTruthy(),
    );
    expect(screen.getByText('Your session has ended. Please sign in again.')).toBeTruthy();
  });
});
