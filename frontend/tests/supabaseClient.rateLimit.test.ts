import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
  const signInWithPasswordMock = vi.fn();
  const signUpMock = vi.fn();
  const createClientMock = vi.fn(() => ({
    auth: {
      getSession: vi.fn(async () => ({ data: { session: null }, error: null })),
      onAuthStateChange: vi.fn(() => ({
        data: {
          subscription: {
            unsubscribe: vi.fn(),
          },
        },
      })),
      signInWithPassword: signInWithPasswordMock,
      signUp: signUpMock,
      signInWithOAuth: vi.fn(async () => ({ data: null, error: null })),
      signOut: vi.fn(async () => ({ error: null })),
    },
  }));

  return {
    createClientMock,
    signInWithPasswordMock,
    signUpMock,
  };
});

vi.mock('@supabase/supabase-js', () => ({
  createClient: mocks.createClientMock,
}));

describe('supabase auth adapter rate limiting', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.resetModules();
    window.localStorage.clear();

    vi.stubEnv('VITE_SUPABASE_URL', 'https://project-ref.supabase.co');
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'anon-key');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    window.localStorage.clear();
  });

  it('blocks repeated password sign-in attempts before calling Supabase again', async () => {
    mocks.signInWithPasswordMock.mockResolvedValue({
      data: { session: null, user: null },
      error: { message: 'Invalid login credentials.' },
    });

    const { getAuthClient } = await import('../src/lib/auth/supabaseClient');
    const authClient = getAuthClient();
    const credentials = {
      email: 'locked-user@example.com',
      password: 'wrong-password',
    };

    for (let attempt = 0; attempt < 5; attempt += 1) {
      await expect(authClient.signInWithPassword(credentials)).rejects.toThrow(
        'Invalid login credentials.',
      );
    }

    await expect(authClient.signInWithPassword(credentials)).rejects.toThrow(
      'Too many sign-in attempts.',
    );
    expect(mocks.signInWithPasswordMock).toHaveBeenCalledTimes(5);
  });

  it('blocks repeated account-creation attempts before calling Supabase again', async () => {
    mocks.signUpMock.mockResolvedValue({
      data: { session: null, user: null },
      error: { message: 'User already registered.' },
    });

    const { getAuthClient } = await import('../src/lib/auth/supabaseClient');
    const authClient = getAuthClient();
    const credentials = {
      email: 'existing-user@example.com',
      password: 'strong-password',
    };

    for (let attempt = 0; attempt < 3; attempt += 1) {
      await expect(authClient.signUpWithPassword(credentials)).rejects.toThrow(
        'User already registered.',
      );
    }

    await expect(authClient.signUpWithPassword(credentials)).rejects.toThrow(
      'Too many account creation attempts.',
    );
    expect(mocks.signUpMock).toHaveBeenCalledTimes(3);
  });

  it('rejects invalid credentials before calling Supabase', async () => {
    const { getAuthClient } = await import('../src/lib/auth/supabaseClient');
    const authClient = getAuthClient();

    await expect(
      authClient.signInWithPassword({
        email: 'not-an-email',
        password: 'short',
      }),
    ).rejects.toThrow('Email address is invalid.');
    await expect(
      authClient.signUpWithPassword({
        email: 'valid-user@example.com',
        password: 'short',
      }),
    ).rejects.toThrow('Password must be at least 8 characters.');

    expect(mocks.signInWithPasswordMock).not.toHaveBeenCalled();
    expect(mocks.signUpMock).not.toHaveBeenCalled();
  });
});
