/* Architecture note:
 * Shared provider constants and auth-error normalization used by both web and
 * extension runtime adapters. Keeping this mapping in one place ensures both
 * clients surface the same actionable auth failures.
 */

export const AUTH_PROVIDER_GOOGLE = 'google' as const;

export type SupportedAuthProvider = typeof AUTH_PROVIDER_GOOGLE;

export type NormalizedAuthErrorCode =
  | 'provider_disabled'
  | 'redirect_misconfigured'
  | 'auth_failed';

export interface NormalizedAuthError {
  code: NormalizedAuthErrorCode;
  message: string;
  rawMessage: string;
}

export function normalizeProviderSignInError(
  error: unknown,
  provider: SupportedAuthProvider,
): NormalizedAuthError {
  const rawMessage = readAuthErrorMessage(error);
  const providerLabel = toProviderLabel(provider);

  if (looksLikeProviderDisabledError(rawMessage)) {
    return {
      code: 'provider_disabled',
      message: `${providerLabel} sign-in is not enabled for this environment. Enable the provider in Supabase Auth settings.`,
      rawMessage,
    };
  }

  if (looksLikeRedirectConfigurationError(rawMessage)) {
    return {
      code: 'redirect_misconfigured',
      message: `${providerLabel} sign-in redirect is not configured for this client. Add the callback URL to the Supabase redirect allow list and Google OAuth credentials.`,
      rawMessage,
    };
  }

  return {
    code: 'auth_failed',
    message: `${providerLabel} sign-in failed. ${rawMessage || 'Try again after confirming auth configuration.'}`,
    rawMessage,
  };
}

function readAuthErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message.trim();
  }
  if (typeof error === 'string') {
    return error.trim();
  }

  if (typeof error === 'object' && error !== null) {
    const payload = error as {
      error_description?: unknown;
      msg?: unknown;
      message?: unknown;
      error?: unknown;
    };

    const candidate =
      payload.error_description ?? payload.msg ?? payload.message ?? payload.error;
    if (typeof candidate === 'string') {
      return candidate.trim();
    }
  }

  return '';
}

function looksLikeProviderDisabledError(message: string): boolean {
  if (!message) {
    return false;
  }

  return (
    /unsupported provider/i.test(message) ||
    /provider is not enabled/i.test(message) ||
    /provider.+disabled/i.test(message)
  );
}

function looksLikeRedirectConfigurationError(message: string): boolean {
  if (!message) {
    return false;
  }

  if (/redirect uri mismatch/i.test(message)) {
    return true;
  }

  const hasRedirectToken = /redirect|redirect_to|callback|chromiumapp/i.test(message);
  const hasConfigurationToken = /not allowed|allow list|allowed|invalid|mismatch|missing/i.test(
    message,
  );

  return hasRedirectToken && hasConfigurationToken;
}

function toProviderLabel(provider: SupportedAuthProvider): string {
  switch (provider) {
    case AUTH_PROVIDER_GOOGLE:
      return 'Google';
    default:
      return provider;
  }
}
