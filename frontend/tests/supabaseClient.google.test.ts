import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  AUTH_PROVIDER_GOOGLE,
  normalizeProviderSignInError,
} from '../src/lib/auth/providerErrors';

const mocks = vi.hoisted(() => {
  const signInWithOAuthMock = vi.fn();
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
      signInWithPassword: vi.fn(async () => ({ error: null })),
      signUp: vi.fn(async () => ({ error: null })),
      signInWithOAuth: signInWithOAuthMock,
      signOut: vi.fn(async () => ({ error: null })),
    },
  }));

  return {
    createClientMock,
    signInWithOAuthMock,
  };
});

vi.mock('@supabase/supabase-js', () => ({
  createClient: mocks.createClientMock,
}));

describe('supabase auth adapter google sign-in', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.resetModules();

    vi.stubEnv('VITE_SUPABASE_URL', 'https://project-ref.supabase.co');
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'anon-key');

    mocks.signInWithOAuthMock.mockResolvedValue({
      data: { provider: AUTH_PROVIDER_GOOGLE },
      error: null,
    });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('initiates google oauth through Supabase client', async () => {
    const { getAuthClient } = await import('../src/lib/auth/supabaseClient');
    await getAuthClient().signInWithGoogle();

    expect(mocks.signInWithOAuthMock).toHaveBeenCalledTimes(1);
    expect(mocks.signInWithOAuthMock).toHaveBeenCalledWith({
      provider: AUTH_PROVIDER_GOOGLE,
      options: { redirectTo: window.location.origin },
    });
  });

  it('maps provider-disabled Supabase errors to normalized message', async () => {
    const providerDisabledMessage = 'Unsupported provider: provider is not enabled';
    mocks.signInWithOAuthMock.mockResolvedValue({
      data: { provider: AUTH_PROVIDER_GOOGLE },
      error: { message: providerDisabledMessage },
    });

    const { getAuthClient } = await import('../src/lib/auth/supabaseClient');
    const expectedMessage = normalizeProviderSignInError(
      new Error(providerDisabledMessage),
      AUTH_PROVIDER_GOOGLE,
    ).message;

    await expect(getAuthClient().signInWithGoogle()).rejects.toThrow(expectedMessage);
  });
});
