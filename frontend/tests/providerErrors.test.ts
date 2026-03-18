import { describe, expect, it } from 'vitest';

import {
  AUTH_PROVIDER_GOOGLE,
  normalizeProviderSignInError,
} from '../src/lib/auth/providerErrors';

describe('provider auth error normalization', () => {
  it('maps provider-disabled errors to actionable message', () => {
    const normalized = normalizeProviderSignInError(
      new Error('Unsupported provider: provider is not enabled'),
      AUTH_PROVIDER_GOOGLE,
    );

    expect(normalized.code).toBe('provider_disabled');
    expect(normalized.message).toBe(
      'Google sign-in is not enabled for this environment. Enable the provider in Supabase Auth settings.',
    );
  });

  it('maps redirect configuration errors to actionable message', () => {
    const normalized = normalizeProviderSignInError(
      new Error('Invalid redirect URL: redirect_to is not allowed'),
      AUTH_PROVIDER_GOOGLE,
    );

    expect(normalized.code).toBe('redirect_misconfigured');
    expect(normalized.message).toBe(
      'Google sign-in redirect is not configured for this client. Add the callback URL to the Supabase redirect allow list and Google OAuth credentials.',
    );
  });
});
